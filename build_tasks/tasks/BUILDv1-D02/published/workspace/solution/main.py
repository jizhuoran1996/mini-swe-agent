#!/usr/bin/env python3
"""BUILDv1-D02: build and qualify MariaDB from source (core profile).

Modes:
  main.py doctor --input <dir>            report missing source/tool/dependency items, exit 78 if any
  main.py run --input <dir> --output <dir> [--jobs N]

The build uses the trusted buildkit.Session helper for all build / configure /
official-test / install / consumer commands, so every invocation, exit status
and log digest is preserved in <output>/commands.json, <output>/tests.json and
<output>/run.json.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

sys.path.insert(0, os.environ.get('PYTHONPATH', ''))
import buildkit  # noqa: E402


CRITICAL_TOOLS = [
    'cmake', 'ninja', 'gcc', 'g++', 'bison', 'perl', 'python3', 'pkg-config', 'make',
]

# Files whose presence inside the source archive is required to configure/build.
# libmariadb/CMakeLists.txt is the bundled Connector/C submodule; the upstream
# codeload archive only carries it for real release tarballs, so a missing entry
# is reported as a genuine dependency gap (never silently skipped).
CRITICAL_TAR = [
    'CMakeLists.txt',
    'sql/CMakeLists.txt',
    'client/CMakeLists.txt',
    'mysql-test/mysql-test-run.pl',
    'libmariadb/CMakeLists.txt',
]


def parse_args():
    p = argparse.ArgumentParser(prog='main.py', description='MariaDB source build driver (BUILDv1-D02)')
    sub = p.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    r.add_argument('--input', required=True)
    r.add_argument('--output', required=True)
    r.add_argument('--jobs', type=int, default=4)
    d = sub.add_parser('doctor')
    d.add_argument('--input', required=True)
    return p.parse_args()


# --- doctor ---------------------------------------------------------------

def _tar_names(archive):
    names = set()
    with tarfile.open(archive) as tf:
        for m in tf.getmembers():
            parts = Path(m.name).parts
            if len(parts) > 1:
                names.add('/'.join(parts[1:]))
    return names


def doctor(input_dir):
    inp = Path(input_dir)
    mp = inp / 'manifest.json'
    if not mp.exists():
        return ['source:manifest.json']
    try:
        manifest = json.loads(mp.read_text())
    except Exception as e:  # noqa: BLE001
        return ['source:manifest.json unreadable: %s' % e]

    missing = []
    archive = inp / manifest['source']['filename']
    if not archive.exists():
        missing.append('source:%s' % manifest['source']['filename'])
    for tool in CRITICAL_TOOLS:
        if shutil.which(tool) is None:
            missing.append('tool:%s' % tool)
    if archive.exists():
        try:
            names = _tar_names(archive)
        except Exception as e:  # noqa: BLE001
            missing.append('source:archive-unreadable:%s' % e)
            names = set()
        for f in CRITICAL_TAR:
            if f not in names:
                missing.append('source-file:%s' % f)
    return missing


def cmd_doctor(args):
    missing = doctor(args.input)
    if missing:
        print('MISSING:')
        for m in missing:
            print('  - ' + m)
        return 78
    print('READY: source archive, toolchain and required submodule stubs present')
    return 0


# --- consumer helpers -----------------------------------------------------

def _installed(install):
    return {
        'server': install / 'bin' / 'mariadbd',
        'client': install / 'bin' / 'mariadb',
        'install_db': install / 'bin' / 'mariadb-install-db',
        'dump': install / 'bin' / 'mariadb-dump',
    }


def _wait_socket(path, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        if Path(path).exists():
            return True
        time.sleep(0.5)
    return False


def _server_proc(session, binary, argv, log_name):
    log = session.output / 'logs' / log_name
    stream = log.open('ab')
    proc = subprocess.Popen(
        [str(binary)] + [str(a) for a in argv],
        stdout=stream, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, start_new_session=True,
    )
    return proc, stream


def _terminate(proc, stream):
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=10)
            except Exception:  # noqa: BLE001
                pass
    try:
        stream.close()
    except Exception:  # noqa: BLE001
        pass


def _consumer(session):
    """Local-transaction consumer against the freshly installed server."""
    install = session.install
    bins = _installed(install)
    for name, path in bins.items():
        if not path.exists():
            raise RuntimeError('consumer precondition: missing %s at %s' % (name, path))

    croot = session.consumer
    d1 = croot / 'data1'
    d2 = croot / 'data2'
    for d in (d1, d2):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)

    for tag, dd in (('d1', d1), ('d2', d2)):
        session.run(
            [str(bins['install_db']), '--basedir=%s' % install, '--datadir=%s' % dd,
             '--auth-root-authentication-method=normal', '--skip-test-db'],
            phase='consumer', name='install_db_%s' % tag, timeout=900)

    sock1 = croot / 'm1.sock'
    sock2 = croot / 'm2.sock'
    cli1 = [str(bins['client']), '--socket=%s' % sock1, '-u', 'root']
    cli2 = [str(bins['client']), '--socket=%s' % sock2, '-u', 'root']
    expected_prefix = '3\t6\t'

    proc1, st1 = _server_proc(session, bins['server'], [
        '--basedir=%s' % install, '--datadir=%s' % d1, '--socket=%s' % sock1,
        '--skip-networking', '--skip-grant-tables',
        '--log-error=%s' % (croot / 'm1.err'),
    ], 'consumer_server1.log')
    try:
        if not _wait_socket(sock1):
            raise RuntimeError('server1 socket not ready')
        session.run(cli1 + ['-e',
            'CREATE DATABASE shop; '
            'CREATE TABLE shop.orders(id INT PRIMARY KEY, qty INT NOT NULL, '
            'amount DECIMAL(10,2) NOT NULL) ENGINE=InnoDB;'],
            phase='consumer', name='create_db', timeout=180)
        session.run(cli1 + ['-e',
            'START TRANSACTION;'
            'INSERT INTO shop.orders VALUES(1,2,10.00),(2,3,15.50);'
            'COMMIT;'
            'START TRANSACTION;INSERT INTO shop.orders VALUES(99,1,0.01);ROLLBACK;'
            'INSERT INTO shop.orders VALUES(3,1,5.00);'],
            phase='consumer', name='txn_ops', timeout=180)
        agg_log = session.run(cli1 + ['-N', '-B', '-e',
            'SELECT COUNT(*), SUM(qty), SUM(amount) FROM shop.orders;'],
            phase='consumer', name='aggregate', timeout=120)
        rows = [ln for ln in agg_log.read_text(errors='replace').splitlines() if ln.strip()]
        got = rows[-1].strip() if rows else ''
        if not got.startswith(expected_prefix):
            raise RuntimeError('aggregate mismatch: %r' % got)
        engines_log = session.run(cli1 + ['-e', 'SHOW ENGINES;'],
                                 phase='consumer', name='show_engines', timeout=120)
        engines_txt = engines_log.read_text(errors='replace').lower()
        if 'innodb' not in engines_txt or 'aria' not in engines_txt:
            raise RuntimeError('expected InnoDB and Aria engines in installed server')
        dump = croot / 'shop.sql'
        session.run([str(bins['dump']), '--socket=%s' % sock1, '-u', 'root',
                     '--databases', 'shop', '-r', str(dump)],
                    phase='consumer', name='dump_shop', timeout=180)
        if not dump.exists() or dump.stat().st_size == 0:
            raise RuntimeError('dump file is empty')
    finally:
        _terminate(proc1, st1)

    proc2, st2 = _server_proc(session, bins['server'], [
        '--basedir=%s' % install, '--datadir=%s' % d2, '--socket=%s' % sock2,
        '--skip-networking', '--skip-grant-tables',
        '--log-error=%s' % (croot / 'm2.err'),
    ], 'consumer_server2.log')
    try:
        if not _wait_socket(sock2):
            raise RuntimeError('server2 socket not ready')
        session.run(cli2 + ['-e', 'SOURCE %s' % (croot / 'shop.sql')],
                    phase='consumer', name='restore_shop', timeout=180)
        agg_log = session.run(cli2 + ['-N', '-B', '-e',
            'SELECT COUNT(*), SUM(qty), SUM(amount) FROM shop.orders;'],
            phase='consumer', name='restore_aggregate', timeout=120)
        rows = [ln for ln in agg_log.read_text(errors='replace').splitlines() if ln.strip()]
        got = rows[-1].strip() if rows else ''
        if not got.startswith(expected_prefix):
            raise RuntimeError('restored aggregate mismatch: %r' % got)
    finally:
        _terminate(proc2, st2)


# --- run ------------------------------------------------------------------

def run(args):
    missing = doctor(args.input)
    if missing:
        sys.stderr.write('MISSING (doctor):\n')
        for m in missing:
            sys.stderr.write('  - %s\n' % m)
        return 78

    session = buildkit.Session(args.input, args.output, args.jobs)
    session.prepare()
    src = session.src
    build = session.build
    install = session.install

    session.run([
        'cmake', '-S', str(src), '-B', str(build), '-G', 'Ninja',
        '-DCMAKE_BUILD_TYPE=RelWithDebInfo',
        '-DCMAKE_INSTALL_PREFIX=%s' % install,
        '-DWITH_UNIT_TESTS=ON',
        '-DWITH_SSL=system',
        '-DPLUGIN_COLUMNSTORE=NO', '-DPLUGIN_TOKUDB=NO', '-DPLUGIN_ROCKSDB=NO',
        '-DPLUGIN_MROONGA=NO', '-DPLUGIN_SPIDER=NO', '-DPLUGIN_CONNECT=NO',
        '-DPLUGIN_OQGRAPH=NO', '-DWITH_WSREP=OFF', '-DPLUGIN_WSREP=NO',
    ], phase='configure', name='cmake_configure', timeout=1800)

    session.run(['cmake', '--build', str(build), '--parallel', str(session.jobs)],
                phase='build', name='cmake_build', timeout=10800)

    session.test('ctest_unit',
                 ['ctest', '--test-dir', str(build), '--output-on-failure', '-j', '2'],
                 cwd=build, timeout=3600)

    mtr = src / 'mysql-test' / 'mysql-test-run.pl'
    session.test('mtr_main_insert_select',
                 ['perl', str(mtr), '--parallel=2', '--force',
                  '--vardir=%s' % (build / 'mtr-var'),
                  'main.insert', 'main.select'],
                 cwd=src / 'mysql-test', timeout=3600)

    session.run(['cmake', '--install', str(build)],
                phase='install', name='cmake_install', timeout=1800)

    _consumer(session)

    features = {
        'installed_binaries': {k: v.exists() for k, v in _installed(install).items()},
        'engines_must_include': ['InnoDB', 'Aria'],
        'consumer_scope': 'local_transactions',
    }
    session.finish(features=features)
    return 0


def main():
    args = parse_args()
    if args.cmd == 'doctor':
        return cmd_doctor(args)
    return run(args)


if __name__ == '__main__':
    sys.exit(main())
