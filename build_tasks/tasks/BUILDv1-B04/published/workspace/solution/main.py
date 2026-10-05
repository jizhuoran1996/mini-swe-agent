#!/usr/bin/env python3
"""BUILDv1-B04: source-build CPython with database/encoding extensions."""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, '/workspace')
import buildkit  # noqa: E402  (trusted helper provided on PYTHONPATH)


CONSUMER_SRC = r'''
import asyncio, json, os, sqlite3, subprocess, sys, threading, pathlib

def check(cond, msg):
    if not cond:
        raise SystemExit("CONSUMER FAIL: " + msg)

exe = sys.executable
check(os.path.isabs(exe), "interpreter path must be absolute: " + exe)
check("consumer" in exe and "venv" in exe, "must be the consumer venv interpreter: " + exe)
check("src" not in pathlib.Path(exe).parts, "venv interpreter must not live in the source tree")
check(sys.prefix != sys.base_prefix, "venv must not fall back to the base installation")

import json as _json
check("src" not in pathlib.Path(_json.__file__).parts, "stdlib json must come from the installed tree")
check("build" not in pathlib.Path(_json.__file__).parts, "stdlib json must not come from the build tree")

payload = {"title": "cpython", "items": [1, 2, 3], "unicode": "\u4e2d\u6587"}
data = json.dumps(payload, ensure_ascii=False)
check(json.loads(data) == payload, "json roundtrip")

check(sqlite3.sqlite_version_info >= (3, 7), "sqlite runtime too old")
db = pathlib.Path(__file__).with_name("consumer.db")
if db.exists():
    db.unlink()
con = sqlite3.connect(str(db))
con.execute("CREATE TABLE t(k TEXT PRIMARY KEY, v TEXT)")
con.execute("INSERT INTO t VALUES (?,?)", ("payload", data))
con.commit()
row = con.execute("SELECT v FROM t WHERE k='payload'").fetchone()
check(row is not None and json.loads(row[0]) == payload, "json->sqlite->json roundtrip")
con.close()

out = subprocess.check_output([exe, "-c", "import sqlite3,json;print(sqlite3.sqlite_version)"], text=True)
check(out.strip(), "subprocess produced no output")

results = []
def worker():
    results.append(sum(json.loads(data)["items"]))
threads = [threading.Thread(target=worker) for _ in range(4)]
for t in threads:
    t.start()
for t in threads:
    t.join()
check(results == [6, 6, 6, 6], "threading results wrong: %r" % results)

async def amain():
    await asyncio.sleep(0.01)
    return sum(json.loads(data)["items"])
check(asyncio.run(amain()) == 6, "asyncio workflow failed")

print("CONSUMER_OK", exe)
'''


EXT_CHECK = (
    "import importlib, sys;"
    "mods=['json','sqlite3','zlib','_ssl','ctypes','lzma','bz2','hashlib','select','socket',"
    "'threading','asyncio','subprocess','ssl','_sqlite3','_bz2','_lzma'];"
    "bad=[m for m in mods if not importlib.import_module(m)];"
    "print('core extensions ok')"
)

DEV_HEADERS = ('sqlite3.h', 'zlib.h', 'openssl/ssl.h', 'lzma.h', 'bzlib.h')

# Variables that must not reach the interpreter under test.  The controller
# exports PYTHONPATH=/opt/controller (so that buildkit is importable) and
# PYTHONDONTWRITEBYTECODE=1.  Both break the official suites:
#
#  * PYTHONPATH injects /opt/controller into sys.path.  test_importlib's
#    helper support.import_helper.forget() walks every sys.path entry and
#    unlinks <dir>/<module>.pyc; on /opt/controller that syscall returns
#    EROFS (the root filesystem is mounted read-only), which is not caught
#    as FileNotFoundError and aborts test_threaded_import with 5 errors.
#  * PYTHONDONTWRITEBYTECODE=1 suppresses the __pycache__/*.pyc writes that
#    several importlib tests exercise.
#
# buildkit merges the caller's os.environ before applying explicit overrides,
# so simply omitting a variable is not enough: it has to be removed at exec
# time with `env -u`.  This touches only the ambient environment of the test
# process, never upstream tests or fixtures.
RUNTIME_ENV_UNSET = (
    'PYTHONPATH',
    'PYTHONDONTWRITEBYTECODE',
    'PYTHONPYCACHEPREFIX',
    'PYTHONHOME',
    'PYTHONSTARTUP',
    'PYTHONUSERBASE',
)


def hermetic(argv):
    """Prefix an interpreter invocation with `env -u <var>...`."""
    env_bin = shutil.which('env') or '/usr/bin/env'
    prefix = [env_bin]
    for var in RUNTIME_ENV_UNSET:
        prefix += ['-u', var]
    return prefix + [str(a) for a in argv]


def _header_ok(header):
    gcc = shutil.which('gcc')
    if not gcc:
        return False
    probe = subprocess.run(
        [gcc, '-E', '-xc', '-'],
        input='#include <%s>\n' % header,
        text=True,
        capture_output=True,
    )
    return probe.returncode == 0


def cmd_doctor(args):
    missing = []
    inp = Path(args.input).resolve()
    manifest_path = inp / 'manifest.json'
    if not manifest_path.is_file():
        missing.append('manifest.json missing at %s' % manifest_path)
    else:
        try:
            manifest = json.loads(manifest_path.read_text())
        except ValueError as exc:
            missing.append('manifest.json unreadable: %s' % exc)
            manifest = None
        if manifest:
            archive = inp / manifest['source']['filename']
            if not archive.is_file():
                missing.append('source archive missing at %s' % archive)
            elif archive.stat().st_size != manifest['source'].get('bytes'):
                missing.append(
                    'source archive size mismatch at %s (%d != %s)'
                    % (archive, archive.stat().st_size, manifest['source'].get('bytes'))
                )
            elif buildkit.digest(archive) != manifest['source']['sha256']:
                missing.append('source archive sha256 mismatch at %s' % archive)
    for tool in ('gcc', 'make', 'ld', 'ar', 'env'):
        if not shutil.which(tool):
            missing.append('build tool missing from PATH: %s' % tool)
    for header in DEV_HEADERS:
        if not _header_ok(header):
            missing.append('development header not compilable: %s' % header)
    if missing:
        for item in missing:
            print('MISSING: %s' % item)
        print('doctor: %d missing item(s)' % len(missing))
        return 78
    print('doctor: ready (source archive, toolchain and extension headers present)')
    return 0


def cmd_run(args):
    session = buildkit.Session(args.input, args.output, args.jobs)
    build_jobs = min(int(args.jobs), 4)
    test_jobs = min(int(args.test_jobs), 2)

    session.prepare()
    src = session.src
    build = session.build
    install = session.install
    python = build / 'python'

    session.run(
        [str(src / 'configure'), '--prefix=%s' % install],
        cwd=build, phase='configure', name='configure', timeout=3600,
    )
    session.run(
        ['make', '-j%d' % build_jobs],
        cwd=build, phase='build', name='make', timeout=9000,
    )
    session.run(
        hermetic([str(python), '-c', EXT_CHECK]),
        cwd=build, phase='build', name='extension_check', timeout=600,
    )
    session.run(
        ['make', 'install'],
        cwd=build, phase='install', name='make_install', timeout=3600,
    )

    installed_python = install / 'bin' / 'python3'
    if not installed_python.exists():
        raise RuntimeError('installed interpreter missing at %s' % installed_python)

    # Official regression modules, verbose so that every failure keeps its
    # full traceback in the preserved log.
    for name in ('test_json', 'test_sqlite3', 'test_importlib'):
        session.test(
            name,
            hermetic([str(python), '-m', 'test', '-v', '-j%d' % test_jobs, name]),
            cwd=build, timeout=3600,
        )

    consumer_dir = session.consumer
    venv_dir = consumer_dir / 'venv'
    if venv_dir.exists():
        shutil.rmtree(venv_dir)
    session.run(
        hermetic([str(installed_python), '-m', 'venv', '--without-pip', str(venv_dir)]),
        cwd=consumer_dir, phase='consumer', name='create_venv', timeout=900,
    )
    venv_python = venv_dir / 'bin' / 'python'
    if not venv_python.exists():
        raise RuntimeError('consumer venv interpreter missing at %s' % venv_python)

    script = consumer_dir / 'consumer.py'
    script.write_text(CONSUMER_SRC)

    session.run(
        hermetic([str(venv_python), '-c',
                  'import sys,json; assert "consumer" in sys.executable; '
                  'assert "src" not in json.__file__; '
                  'print(sys.executable, sys.prefix, json.__file__)']),
        cwd=consumer_dir, phase='consumer', name='venv_paths', timeout=600,
    )
    session.run(
        hermetic([str(venv_python), str(script)]),
        cwd=consumer_dir, phase='consumer', name='consumer_workflow', timeout=900,
    )

    # Continuation: a second independent environment reusing the same install tree.
    second = consumer_dir / 'venv2'
    if second.exists():
        shutil.rmtree(second)
    session.run(
        hermetic([str(installed_python), '-m', 'venv', '--without-pip', str(second)]),
        cwd=consumer_dir, phase='consumer', name='create_venv2', timeout=900,
    )
    session.run(
        hermetic([str(second / 'bin' / 'python'), str(script)]),
        cwd=consumer_dir, phase='consumer', name='consumer_workflow_2', timeout=900,
    )

    session.finish(features={
        'source_build': True,
        'install_prefix': str(install),
        'interpreter': str(installed_python),
        'extensions_checked': ['json', 'sqlite3', 'zlib', '_ssl', 'ctypes', 'lzma', 'bz2'],
        'official_tests': ['test_json', 'test_sqlite3', 'test_importlib'],
        'official_test_mode': 'regrtest -v, env -u PYTHONPATH -u PYTHONDONTWRITEBYTECODE',
        'consumer_envs': [str(venv_dir), str(second)],
        'build_jobs': build_jobs,
        'test_jobs': test_jobs,
    })
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog='main.py', description=__doc__)
    subs = parser.add_subparsers(dest='cmd', required=True)
    doctor = subs.add_parser('doctor', help='report missing source/tool/dependency items')
    doctor.add_argument('--input', required=True)
    doctor.add_argument('--output', default='output')
    doctor.add_argument('--jobs', type=int, default=4)
    doctor.set_defaults(fn=cmd_doctor)
    run = subs.add_parser('run', help='build, test, install and verify a consumer')
    run.add_argument('--input', required=True)
    run.add_argument('--output', required=True)
    run.add_argument('--jobs', type=int, default=4)
    run.add_argument('--test-jobs', type=int, default=2)
    run.set_defaults(fn=cmd_run)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == '__main__':
    sys.exit(main())
