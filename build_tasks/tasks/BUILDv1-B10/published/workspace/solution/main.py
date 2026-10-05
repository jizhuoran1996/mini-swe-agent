#!/usr/bin/env python3
# BUILDv1-B10: Build an OpenJDK 21 server image from the frozen source release,
# run the official jdk_lang jtreg group and independently consume the freshly
# built JDK outside the source tree (javac/java/jar + JNI shared library).
#
# All build/configure/install/test/consumer commands go through buildkit.Session
# so command lines, exit codes and full logs are preserved under output/logs.

import argparse
import glob
import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import buildkit
from buildkit import Session


# --------------------------------------------------------------------------
# Dependency discovery (boot JDK / jtreg / host tools)
# --------------------------------------------------------------------------
BOOT_JDK_CANDIDATES = [
    os.environ.get('BOOT_JDK'),
    os.environ.get('JDK21_BOOT'),
    os.environ.get('JAVA_HOME'),
    '/workspace/input/boot-jdk',
    '/workspace/input/deps/boot-jdk',
    '/workspace/input/deps/jdk',
    '/workspace/input/jdk',
    '/opt/boot-jdk',
    '/opt/jdk-21',
    '/opt/jdk21',
]
JTREG_CANDIDATES = [
    os.environ.get('JTREG_HOME'),
    '/workspace/input/jtreg',
    '/workspace/input/deps/jtreg',
    '/workspace/input/deps/jtreg-bin',
    '/opt/jtreg',
    '/opt/jtreg-7',
]
BUILD_TOOLS = ['bash', 'gcc', 'g++', 'make', 'autoconf', 'unzip', 'zip',
               'file', 'diff', 'ld', 'awk', 'sed', 'tar']


def _jdk_ok(path):
    p = Path(path)
    return (p / 'bin' / 'javac').is_file() and (p / 'bin' / 'java').is_file()


def find_boot_jdk():
    cands = [c for c in BOOT_JDK_CANDIDATES if c]
    w = shutil.which('javac')
    if w:
        cands.append(str(Path(w).resolve().parent.parent))
    cands.extend(sorted(glob.glob('/usr/lib/jvm/*')))
    seen = set()
    for c in cands:
        if not c or c in seen:
            continue
        seen.add(c)
        if _jdk_ok(c):
            return str(Path(c).resolve())
    return None


def find_jtreg():
    cands = [c for c in JTREG_CANDIDATES if c]
    w = shutil.which('jtreg')
    if w:
        cands.append(str(Path(w).resolve().parent.parent))
    cands.extend(sorted(glob.glob('/opt/*jtreg*')))
    cands.extend(sorted(glob.glob('/opt/*/jtreg*')))
    seen = set()
    for c in cands:
        if not c or c in seen:
            continue
        seen.add(c)
        if (Path(c) / 'bin' / 'jtreg').is_file():
            return str(Path(c).resolve())
    return None


def _probe(argv):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        return (r.stdout + r.stderr).strip()
    except Exception as exc:  # pragma: no cover - defensive
        return 'probe-failed: ' + str(exc)


def collect_missing(input_dir):
    """Return the exact list of missing source/tool/dependency items."""
    missing = []
    inp = Path(input_dir)
    man = inp / 'manifest.json'
    if not man.is_file():
        missing.append({'kind': 'source', 'item': 'manifest.json', 'path': str(man)})
        return missing
    try:
        m = json.loads(man.read_text())
    except Exception as exc:
        missing.append({'kind': 'source', 'item': 'manifest.json unparsable',
                        'path': str(man), 'detail': str(exc)})
        return missing
    src = m.get('source', {}) or {}
    arch = inp / src.get('filename', 'source.tar.gz')
    if not arch.is_file():
        missing.append({'kind': 'source', 'item': 'source archive', 'path': str(arch)})
    elif src.get('sha256'):
        try:
            if buildkit.digest(arch) != src['sha256']:
                missing.append({'kind': 'source', 'item': 'source archive sha256 mismatch',
                                'path': str(arch)})
        except Exception as exc:
            missing.append({'kind': 'source', 'item': 'source archive unreadable',
                            'path': str(arch), 'detail': str(exc)})

    boot = find_boot_jdk()
    if not boot:
        missing.append({'kind': 'dependency', 'item': 'boot JDK (directory with bin/javac)',
                        'searched': [c for c in BOOT_JDK_CANDIDATES if c] + ['$PATH', '/usr/lib/jvm/*']})
    else:
        ver = _probe([str(Path(boot) / 'bin' / 'javac'), '-version'])
        if not any((' %s' % v) in ver for v in ('20', '21', '22')):
            missing.append({'kind': 'dependency',
                            'item': 'boot JDK version out of 20..22 range',
                            'path': boot, 'detail': ver})

    if not find_jtreg():
        missing.append({'kind': 'dependency', 'item': 'jtreg (directory with bin/jtreg)',
                        'searched': [c for c in JTREG_CANDIDATES if c] + ['$PATH', '/opt/*jtreg*']})

    for tool in BUILD_TOOLS:
        if not shutil.which(tool):
            missing.append({'kind': 'tool', 'item': tool, 'searched': ['$PATH']})
    return missing


# --------------------------------------------------------------------------
# Consumer sources (embedded so they are delivered with the solution)
# --------------------------------------------------------------------------
APP_JAVA = '''import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;

public class App {
    public static void main(String[] args) throws Exception {
        List<Integer> xs = new ArrayList<>();
        for (int i = 1; i <= 1000; i++) xs.add(i);
        int sum = xs.stream().mapToInt(Integer::intValue).sum();
        ExecutorService ex = Executors.newFixedThreadPool(2);
        Future<Integer> f = ex.submit(() -> 21 * 2);
        int v = f.get();
        ex.shutdown();
        Path p = Paths.get(args[0]);
        Files.writeString(p, "sum=" + sum + "\n");
        String back = Files.readString(p).trim();
        if (sum != 500500 || v != 42 || !back.equals("sum=500500")) {
            System.err.println("APP FAILED sum=" + sum + " v=" + v + " back=" + back);
            System.exit(1);
        }
        System.out.println("APP OK sum=" + sum + " v=" + v
            + " java.home=" + System.getProperty("java.home")
            + " version=" + System.getProperty("java.version"));
    }
}
'''

NATIVE_JAVA = '''public class NativeDemo {
    static { System.loadLibrary("nativedemo"); }
    public static native int add(int a, int b);
    public static void main(String[] args) {
        int r = add(19, 23);
        if (r != 42) {
            System.err.println("JNI FAILED result=" + r);
            System.exit(1);
        }
        System.out.println("JNI OK result=" + r
            + " java.home=" + System.getProperty("java.home"));
    }
}
'''

NATIVE_C = '''#include <jni.h>
#include "NativeDemo.h"

JNIEXPORT jint JNICALL Java_NativeDemo_add(JNIEnv *env, jclass cls, jint a, jint b) {
    (void) env; (void) cls;
    return a + b;
}
'''


def run_consumers(sess):
    """Compile/package/run a Java app and a JNI library with the new JDK only."""
    jdk = sess.install
    javac = str(jdk / 'bin' / 'javac')
    java = str(jdk / 'bin' / 'java')
    jar = str(jdk / 'bin' / 'jar')
    work = sess.consumer
    if work.exists():
        shutil.rmtree(work)
    (work / 'classes').mkdir(parents=True)
    (work / 'App.java').write_text(APP_JAVA)
    (work / 'NativeDemo.java').write_text(NATIVE_JAVA)
    (work / 'NativeDemo.c').write_text(NATIVE_C)

    # record runtime identity of the freshly built image
    sess.run([java, '-version'], cwd=work, phase='consumer', name='java_version', timeout=300)
    sess.run([javac, '-d', 'classes', 'App.java'], cwd=work, phase='consumer',
             name='compile_app', timeout=600)
    sess.run([jar, 'cfe', 'app.jar', 'App', '-C', 'classes', '.'], cwd=work,
             phase='consumer', name='package_app', timeout=600)
    sess.run([java, '-jar', 'app.jar', 'out.txt'], cwd=work, phase='consumer',
             name='run_app', timeout=600)

    # JNI path: let the new javac emit the header, then build and load the .so
    sess.run([javac, '-h', '.', '-d', 'classes', 'NativeDemo.java'], cwd=work,
             phase='consumer', name='javac_jni_header', timeout=600)
    sess.run(['gcc', '-shared', '-fPIC',
              '-I', str(jdk / 'include'),
              '-I', str(jdk / 'include' / 'linux'),
              'NativeDemo.c', '-o', 'libnativedemo.so'],
             cwd=work, phase='consumer', name='build_jni_lib', timeout=600)
    sess.run([java, '-Djava.library.path=.', '-cp', 'classes', 'NativeDemo'],
             cwd=work, phase='consumer', name='run_jni', timeout=600)


def run_guide_trace(sess, conf):
    """Save the exact jdk_lang test inventory before execution."""
    lang_root = sess.src / 'test' / 'jdk' / 'java' / 'lang'
    files = []
    if lang_root.is_dir():
        files = sorted(str(p.relative_to(sess.src)) for p in lang_root.rglob('*.java'))
    sess.write('jdk_lang_inventory.json', {
        'conf': conf,
        'root': str(lang_root),
        'discovered_java_tests': len(files),
        'files': files,
    })


# --------------------------------------------------------------------------
# Subcommands
# --------------------------------------------------------------------------
def cmd_doctor(args):
    missing = collect_missing(args.input)
    report = {
        'task_id': 'BUILDv1-B10',
        'input': str(Path(args.input).resolve()),
        'boot_jdk': find_boot_jdk(),
        'jtreg': find_jtreg(),
        'missing': missing,
        'ready': not missing,
    }
    print(json.dumps(report, indent=2))
    return 0 if not missing else 78


def cmd_run(args):
    missing = collect_missing(args.input)
    if missing:
        print(json.dumps({'task_id': 'BUILDv1-B10', 'status': 'missing_dependencies',
                          'missing': missing}, indent=2))
        return 78

    sess = Session(args.input, args.output, args.jobs)
    sess.prepare()
    boot = find_boot_jdk()
    jtreg = find_jtreg()
    conf = 'release'
    sess.write('dependencies.json', {'boot_jdk': boot, 'jtreg': jtreg,
                                     'jobs': sess.jobs, 'test_jobs': 2})

    cfg = ['bash', 'configure',
           '--with-boot-jdk=' + boot,
           '--with-conf-name=' + conf,
           '--with-debug-level=release',
           '--with-jvm-variants=server',
           '--enable-jtreg-failure-handler=no']
    if jtreg:
        cfg.append('--with-jtreg=' + jtreg)
    sess.run(cfg, cwd=sess.src, phase='configure', name='configure', timeout=1800)

    run_guide_trace(sess, conf)

    sess.run(['make', 'CONF=' + conf, 'JOBS=' + str(sess.jobs), 'images'],
             cwd=sess.src, phase='build', name='make_images', timeout=10800)

    images_jdk = sess.build / conf / 'images' / 'jdk'
    if not images_jdk.is_dir():
        raise RuntimeError('expected image directory missing: ' + str(images_jdk))
    if sess.install.exists():
        shutil.rmtree(sess.install)
    shutil.copytree(images_jdk, sess.install, symlinks=True)

    with tarfile.open(sess.output / 'openjdk-image.tar.gz', 'w:gz') as tf:
        tf.add(sess.install, arcname='jdk')

    run_consumers(sess)

    sess.test('jdk_lang',
              ['make', 'CONF=' + conf, 'test', 'TEST=jdk_lang', 'JTREG=JOBS=2'],
              cwd=sess.src, parser='auto', timeout=10800)

    sess.finish(features={'scope': 'full server JDK image',
                          'tests': 'jdk_lang',
                          'consumer_java': True,
                          'consumer_jni': True})
    print('BUILDv1-B10 complete')
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog='main.py', description=__doc__)
    sub = ap.add_subparsers(dest='cmd')
    for name in ('doctor', 'run'):
        p = sub.add_parser(name)
        p.add_argument('--input', default='input')
        p.add_argument('--output', default='output')
        p.add_argument('--jobs', type=int, default=4)
    args = ap.parse_args(argv)
    if args.cmd == 'doctor':
        return cmd_doctor(args)
    if args.cmd == 'run':
        return cmd_run(args)
    ap.print_help()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
