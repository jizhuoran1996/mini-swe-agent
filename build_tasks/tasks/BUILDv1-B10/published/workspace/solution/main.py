#!/usr/bin/env python3
# BUILDv1-B10: Build an OpenJDK 21 server image from the frozen source release,
# run the official jdk_lang jtreg group with the hydrated jtreg 7.3.1+1
# harness, and independently consume the freshly built JDK outside the source
# tree (javac/java/jar plus a JNI shared library).
#
# FIX (previous failure): upstream configure aborts with
#   "You have _JAVA_OPTIONS or JAVA_TOOL_OPTIONS set. ... configure: error:
#    Cannot continue"
# so JAVA_TOOL_OPTIONS/_JAVA_OPTIONS are now explicitly REMOVED from every
# child environment (`env -u JAVA_TOOL_OPTIONS -u _JAVA_OPTIONS ...`).  JVM
# thread bounding is instead done the way upstream supports it:
#   --with-boot-jdk-jvmargs, --with-jobs=2, --with-num-cores=2, make JOBS=2,
#   JTREG="JOBS=2;JAVA_OPTIONS=...", and explicit -XX flags on our consumers.
#
# Every build/configure/install/test/consumer command runs through
# buildkit.Session so argument lists, exit codes and full logs are preserved.

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import tarfile
from pathlib import Path

import buildkit
from buildkit import Session


JTREG_MIN_VERSION = (7, 3, 1)
BOOT_JDK_MIN = (20, 0, 0)
BOOT_JDK_MAX_EXCLUSIVE = (23, 0, 0)

# PID-bounded parallelism for this 1024-PID cgroup.
BUILD_JOBS = 2
TEST_JOBS = 2
JVM_THREAD_OPTS = ['-XX:ActiveProcessorCount=2', '-XX:ParallelGCThreads=2',
                   '-XX:ConcGCThreads=1']
JVM_THREAD_OPTS_STR = ' '.join(JVM_THREAD_OPTS)

# Upstream configure refuses to run when these exist in the environment.
TOOL_ENV_VARS = ('JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS')
ENV_BIN = shutil.which('env') or '/usr/bin/env'

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
BUILD_TOOLS = ['bash', 'gcc', 'g++', 'make', 'autoconf', 'unzip', 'zip',
               'file', 'diff', 'ld', 'awk', 'sed', 'tar', 'patch', 'readelf']
CACHE_ROOTS = ['/workspace/cache', '/workspace/input/deps',
               '/workspace/input', '/opt', '/usr/local', '/usr/share']


def cmd(*argv):
    """Explicit argv with JAVA_TOOL_OPTIONS/_JAVA_OPTIONS removed from child."""
    prefix = [ENV_BIN]
    for name in TOOL_ENV_VARS:
        prefix += ['-u', name]
    return prefix + [str(a) for a in argv]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _probe(argv, timeout=60):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or '') + (r.stderr or '')
    except Exception as exc:  # pragma: no cover - defensive
        return 'probe-failed: ' + str(exc)


def _resolve_java(boot_jdk=None):
    if boot_jdk:
        j = Path(boot_jdk) / 'bin' / 'java'
        if j.is_file():
            return str(j)
    return shutil.which('java')


def _jdk_ok(path):
    if not path:
        return False
    p = Path(path)
    return (p / 'bin' / 'javac').is_file() and (p / 'bin' / 'java').is_file()


def _parse_jdk_version(text):
    m = re.search(r'version\s+"?(\d+)(?:\.(\d+))?(?:\.(\d+))?', text)
    if not m:
        m = re.search(r'\b(\d+)\.(\d+)\.(\d+)', text)
    if not m:
        return None
    return (int(m.group(1) or 0), int(m.group(2) or 0), int(m.group(3) or 0))


def find_boot_jdk():
    cands = [c for c in BOOT_JDK_CANDIDATES if c]
    w = shutil.which('javac')
    if w:
        cands.append(str(Path(w).resolve().parent.parent))
    cands.extend(sorted(glob.glob('/usr/lib/jvm/*')))
    seen = set()
    for c in cands:
        if not c:
            continue
        try:
            key = str(Path(c).resolve())
        except Exception:
            key = c
        if key in seen:
            continue
        seen.add(key)
        if _jdk_ok(key):
            return key
    return None


def boot_jdk_version(boot_jdk):
    java = _resolve_java(boot_jdk)
    if not java:
        return None
    return _parse_jdk_version(_probe([java, '-version']))


# ---------------------------------------------------------------------------
# jtreg discovery / version probe
# ---------------------------------------------------------------------------
def _manifest_jtreg_paths(input_dir):
    if not input_dir:
        return []
    man = Path(input_dir) / 'manifest.json'
    if not man.is_file():
        return []
    try:
        m = json.loads(man.read_text())
    except Exception:
        return []
    out = []
    if (m.get('jtreg_harness') or {}).get('path'):
        out.append(str(m['jtreg_harness']['path']))
    for cache in m.get('dependency_caches') or []:
        if cache.get('destination'):
            out.append(str(cache['destination']))
    return out


def _collect_jtreg_dirs(input_dir=None):
    cands = []
    for name in ('JTREG_HOME', 'JT_HOME'):
        v = os.environ.get(name)
        if v:
            cands.append(v)
    w = shutil.which('jtreg')
    if w:
        cands.append(str(Path(w).resolve().parent.parent))
    cands = _manifest_jtreg_paths(input_dir) + cands
    for base in CACHE_ROOTS:
        bp = Path(base)
        if not bp.is_dir():
            continue
        if (bp / 'jtreg').is_dir():
            cands.append(str(bp / 'jtreg'))
        try:
            for child in bp.iterdir():
                if child.is_dir() and 'jtreg' in child.name.lower():
                    cands.append(str(child))
        except Exception:
            pass
    return cands


def _jtreg_version(jtreg_home, boot_jdk=None):
    jtreg_home = Path(jtreg_home)
    java = _resolve_java(boot_jdk) or 'java'
    out = ''
    jar = None
    for candidate in (jtreg_home / 'lib' / 'jtreg.jar', jtreg_home / 'jtreg.jar'):
        if candidate.is_file():
            jar = candidate
            break
    if jar is not None:
        out = _probe([str(java), '-jar', str(jar), '-version'])
    if not out.strip() or out.startswith('probe-failed'):
        script = jtreg_home / 'bin' / 'jtreg'
        if script.is_file():
            out = _probe([str(script), '-version'])
    if not out.strip() or out.startswith('probe-failed'):
        return None
    m = re.search(r'jtreg[^0-9]{0,20}(\d+)\.(\d+)(?:\.(\d+))?', out, re.I)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))
    for line in out.splitlines():
        for tok in line.split():
            m = re.match(r'^(\d+)\.(\d+)(?:\.(\d+))?(?:[+\-].*)?$', tok)
            if m:
                return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))
    return None


def _has_jtreg(jtreg_home):
    p = Path(jtreg_home)
    return (p / 'bin' / 'jtreg').is_file() or (p / 'lib' / 'jtreg.jar').is_file()


def find_jtreg(boot_jdk=None, input_dir=None):
    known, unknown, seen = [], [], set()
    for c in _collect_jtreg_dirs(input_dir):
        if not c or not _has_jtreg(c):
            continue
        try:
            key = str(Path(c).resolve())
        except Exception:
            key = c
        if key in seen:
            continue
        seen.add(key)
        v = _jtreg_version(key, boot_jdk)
        (unknown if v is None else known).append(key if v is None else (v, key))
    known.sort(reverse=True)
    for v, key in known:
        if v >= JTREG_MIN_VERSION:
            return key, v
    if known:
        return known[0][1], known[0][0]
    if unknown:
        return unknown[0], None
    return None, None


# ---------------------------------------------------------------------------
# Dependency report (doctor)
# ---------------------------------------------------------------------------
def _load_manifest(input_dir):
    man = Path(input_dir) / 'manifest.json'
    if not man.is_file():
        return None
    try:
        return json.loads(man.read_text())
    except Exception:
        return None


def collect_missing(input_dir):
    missing = []
    inp = Path(input_dir)
    man_path = inp / 'manifest.json'
    if not man_path.is_file():
        missing.append({'kind': 'source', 'item': 'manifest.json',
                        'path': str(man_path)})
        return missing
    m = _load_manifest(input_dir)
    if m is None:
        missing.append({'kind': 'source', 'item': 'manifest.json unparsable',
                        'path': str(man_path)})
        return missing
    src = m.get('source') or {}
    archive = inp / src.get('filename', 'source.tar.gz')
    if not archive.is_file():
        missing.append({'kind': 'source', 'item': 'source archive',
                        'path': str(archive)})
    elif src.get('sha256'):
        try:
            if buildkit.digest(archive) != src['sha256']:
                missing.append({'kind': 'source',
                                'item': 'source archive sha256 mismatch',
                                'path': str(archive)})
        except Exception as exc:
            missing.append({'kind': 'source',
                            'item': 'source archive unreadable',
                            'path': str(archive), 'detail': str(exc)})

    boot = find_boot_jdk()
    if not boot:
        missing.append({'kind': 'dependency',
                        'item': 'boot JDK (directory with bin/javac)',
                        'searched': [c for c in BOOT_JDK_CANDIDATES if c]
                                    + ['$PATH', '/usr/lib/jvm/*']})
    else:
        bv = boot_jdk_version(boot)
        if bv is None:
            missing.append({'kind': 'dependency',
                            'item': 'cannot determine boot JDK version',
                            'path': boot})
        elif not (BOOT_JDK_MIN <= bv < BOOT_JDK_MAX_EXCLUSIVE):
            missing.append({'kind': 'dependency',
                            'item': 'boot JDK version out of range (need 20.x-22.x)',
                            'path': boot,
                            'version': '.'.join(map(str, bv))})

    jtreg_home, jtreg_ver = find_jtreg(boot, input_dir)
    if jtreg_home is None:
        missing.append({'kind': 'dependency',
                        'item': 'jtreg >= 7.3.1 (directory with bin/jtreg)',
                        'searched': _collect_jtreg_dirs(input_dir)
                                    + ['$PATH', '/workspace/cache/jtreg']})
    elif jtreg_ver is None:
        missing.append({'kind': 'dependency',
                        'item': 'cannot determine jtreg version (need >= 7.3.1)',
                        'path': jtreg_home})
    elif jtreg_ver < JTREG_MIN_VERSION:
        missing.append({'kind': 'dependency',
                        'item': 'jtreg >= 7.3.1 required (installed version too old)',
                        'path': jtreg_home,
                        'version': '.'.join(map(str, jtreg_ver)),
                        'required': '.'.join(map(str, JTREG_MIN_VERSION))})

    for tool in BUILD_TOOLS:
        if not shutil.which(tool):
            missing.append({'kind': 'tool', 'item': tool, 'searched': ['$PATH']})
    return missing


# ---------------------------------------------------------------------------
# Embedded consumer sources (compiled/run only with the newly built JDK)
# ---------------------------------------------------------------------------
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
    javac_opts = ['-J' + opt for opt in JVM_THREAD_OPTS]

    def run(argv, name):
        sess.run(cmd(*argv), cwd=work, phase='consumer', name=name, timeout=600)

    # The delivered image must be the freshly built one, not the boot JDK.
    log = sess.run(cmd(java, *JVM_THREAD_OPTS, '-version'), cwd=work,
                   phase='consumer', name='built_java_version', timeout=300)
    text = log.read_text(errors='replace')
    if '21.0.7' not in text:
        raise RuntimeError('delivered image is not the freshly built JDK 21.0.7: '
                           + text.strip())
    run([javac, *javac_opts, '-d', 'classes', 'App.java'], 'compile_app')
    run([jar, 'cfe', 'app.jar', 'App', '-C', 'classes', '.'], 'package_app')
    run([java, *JVM_THREAD_OPTS, '-jar', 'app.jar', 'out.txt'], 'run_app')
    run([javac, *javac_opts, '-h', '.', '-d', 'classes', 'NativeDemo.java'],
        'javac_jni_header')
    run(['gcc', '-shared', '-fPIC',
         '-I', str(jdk / 'include'),
         '-I', str(jdk / 'include' / 'linux'),
         'NativeDemo.c', '-o', 'libnativedemo.so'], 'build_jni_lib')
    run([java, *JVM_THREAD_OPTS, '-Djava.library.path=.', '-cp', 'classes',
         'NativeDemo'], 'run_jni')


def parse_jtreg_summary(text):
    m = re.search(r'^Test results:\s*(.+)$', text, re.M)
    if not m:
        return None
    counts = {}
    for item in m.group(1).split(';'):
        mm = re.match(r'\s*([A-Za-z_ ]+):\s*([\d,]+)', item)
        if mm:
            counts[mm.group(1).strip().replace(' ', '_')] = \
                int(mm.group(2).replace(',', ''))
    return counts or None


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------
def cmd_doctor(args):
    missing = collect_missing(args.input)
    boot = find_boot_jdk()
    bv = boot_jdk_version(boot) if boot else None
    jtreg, jtreg_ver = find_jtreg(boot, args.input)
    report = {
        'task_id': 'BUILDv1-B10',
        'input': str(Path(args.input).resolve()),
        'boot_jdk': boot,
        'boot_jdk_version': '.'.join(map(str, bv)) if bv else None,
        'jtreg': jtreg,
        'jtreg_version': '.'.join(map(str, jtreg_ver)) if jtreg_ver else None,
        'jtreg_min_version': '.'.join(map(str, JTREG_MIN_VERSION)),
        'build_jobs': BUILD_JOBS,
        'test_jobs': TEST_JOBS,
        'jvm_thread_options': JVM_THREAD_OPTS_STR,
        'tool_env_vars_removed': list(TOOL_ENV_VARS),
        'missing': missing,
        'ready': not missing,
    }
    print(json.dumps(report, indent=2))
    return 0 if not missing else 78


def cmd_run(args):
    missing = collect_missing(args.input)
    if missing:
        print(json.dumps({'task_id': 'BUILDv1-B10',
                          'status': 'missing_dependencies',
                          'missing': missing}, indent=2))
        return 78

    sess = Session(args.input, args.output, args.jobs)
    sess.prepare()
    boot = find_boot_jdk()
    jtreg, jtreg_ver = find_jtreg(boot, args.input)
    conf = 'release'
    sess.write('dependencies.json', {
        'boot_jdk': boot,
        'jtreg': jtreg,
        'jtreg_version': '.'.join(map(str, jtreg_ver)) if jtreg_ver else None,
        'build_jobs': BUILD_JOBS,
        'test_jobs': TEST_JOBS,
        'jvm_thread_options': JVM_THREAD_OPTS_STR,
        'tool_env_vars_removed': list(TOOL_ENV_VARS),
        'note': ('JAVA_TOOL_OPTIONS/_JAVA_OPTIONS are stripped from every child '
                 'environment because upstream configure rejects them; thread '
                 'bounding uses --with-boot-jdk-jvmargs, --with-jobs/-num-cores, '
                 'make JOBS and JTREG JAVA_OPTIONS instead'),
    })

    cfg = ['bash', 'configure',
           '--with-boot-jdk=' + boot,
           '--with-conf-name=' + conf,
           '--with-debug-level=release',
           '--with-jvm-variants=server',
           '--with-jobs=' + str(BUILD_JOBS),
           '--with-num-cores=' + str(BUILD_JOBS),
           '--with-boot-jdk-jvmargs=' + JVM_THREAD_OPTS_STR,
           '--enable-jtreg-failure-handler=no']
    if jtreg:
        cfg.append('--with-jtreg=' + jtreg)
    sess.run(cmd(*cfg), cwd=sess.src, phase='configure', name='configure',
             timeout=1800)

    lang_root = sess.src / 'test' / 'jdk' / 'java' / 'lang'
    sess.write('jdk_lang_inventory.json', {
        'conf': conf,
        'root': str(lang_root),
        'discovered_java_tests': len(list(lang_root.rglob('*.java')))
        if lang_root.is_dir() else 0,
    })

    sess.run(cmd('make', 'CONF=' + conf, 'JOBS=' + str(BUILD_JOBS), 'images'),
             cwd=sess.src, phase='build', name='make_images', timeout=10800)

    images_jdk = sess.build / conf / 'images' / 'jdk'
    if not images_jdk.is_dir():
        raise RuntimeError('expected image directory missing: ' + str(images_jdk))
    if sess.install.exists():
        shutil.rmtree(sess.install)
    shutil.copytree(images_jdk, sess.install, symlinks=True)

    with tarfile.open(sess.output / 'openjdk-image.tar.gz', 'w:gz') as archive:
        archive.add(sess.install, arcname='jdk')

    run_consumers(sess)

    log = sess.test('jdk_lang',
                    cmd('make', 'CONF=' + conf, 'test', 'TEST=jdk_lang',
                        'JTREG=JOBS=%d;JAVA_OPTIONS=%s' % (TEST_JOBS,
                                                           JVM_THREAD_OPTS_STR)),
                    cwd=sess.src, parser='auto', timeout=10800)
    counts = parse_jtreg_summary(log.read_text(errors='replace'))
    sess.write('jtreg_summary.json', {
        'selector': 'jdk_lang',
        'raw_log': str(log.relative_to(sess.output)),
        'parsed': counts is not None,
        'counts': counts,
        'source': 'upstream jtreg "Test results:" summary line',
    })
    if counts and (counts.get('failed') or counts.get('error')):
        raise RuntimeError('jtreg reported failures: ' + json.dumps(counts))

    sess.finish(features={'scope': 'full server JDK image',
                          'tests': 'jdk_lang',
                          'consumer_java': True,
                          'consumer_jni': True,
                          'build_jobs': BUILD_JOBS,
                          'test_jobs': TEST_JOBS,
                          'jvm_thread_options': JVM_THREAD_OPTS_STR})
    print('BUILDv1-B10 complete')
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog='main.py', description=__doc__)
    sub = ap.add_subparsers(dest='cmd')
    for name in ('doctor', 'run'):
        p = sub.add_parser(name)
        p.add_argument('--input', default='input')
        p.add_argument('--output', default='output')
        p.add_argument('--jobs', type=int, default=BUILD_JOBS,
                       help='requested build jobs (clamped to %d to fit the '
                            '1024-PID cgroup)' % BUILD_JOBS)
    args = ap.parse_args(argv)
    if args.cmd == 'doctor':
        return cmd_doctor(args)
    if args.cmd == 'run':
        return cmd_run(args)
    ap.print_help()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
