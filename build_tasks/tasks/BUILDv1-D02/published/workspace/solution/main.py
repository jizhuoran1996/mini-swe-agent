#!/usr/bin/env python3
"""BUILDv1-D02: build and qualify MariaDB from source (core profile).

Modes
=====
``main.py doctor --input <dir>``
    Readiness probe.  Lists every missing source file, tool or offline
    dependency and exits 78 when anything is missing, 0 when the build can
    start.  Never touches the build tree.

``main.py run --input <dir> --output <dir> [--jobs N]``
    Extract, configure, build, run the official tests, install into a private
    prefix and verify the freshly installed server with a local-transaction
    consumer (create / commit / rollback / aggregate / export / restore).

Every configure/build/official-test/install/consumer command is executed
through ``buildkit.Session`` so argv, exit code, wall time and log digest are
preserved.  The private ``mariadbd`` processes used by the consumer are
ordinary children of this process and are always terminated before the run
returns.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path

import buildkit

BUILD_JOBS_CAP = 4
TEST_JOBS = 2

CRITICAL_TOOLS = ['cmake', 'ninja', 'gcc', 'g++', 'bison', 'perl', 'python3',
                  'pkg-config', 'make']

# Official runner in 11.4.x is ``mariadb-test-run.pl``; the other two are
# legacy alternates that other branches ship under different names.
MTR_SCRIPTS = ('mariadb-test-run.pl', 'mysql-test-run.pl', 'mtr')

CRITICAL_FILES = [
    'CMakeLists.txt',
    'sql/CMakeLists.txt',
    'client/CMakeLists.txt',
    'storage/innobase/CMakeLists.txt',
    'storage/maria/CMakeLists.txt',
    'libmariadb/CMakeLists.txt',
    'mysql-test/mariadb-test-run.pl',
]

LIBFMT_STAMPS = ('libfmt-download', 'libfmt-verify', 'libfmt-extract',
                 'libfmt-patch', 'libfmt-update')

# Installed-tool lookup order.  The default STANDALONE layout puts startup
# scripts under ``scripts/`` and executables under ``bin/``; other layouts may
# publish them elsewhere, so probe several directories then fall back to a
# recursive search by known leaf name.  Both the modern ``mariadb-*`` names and
# legacy ``mysql_*`` aliases are accepted.
INSTALL_DB_CANDIDATES = [
    ('scripts', 'mariadb-install-db'),
    ('scripts', 'mariadb-install-db.pl'),
    ('scripts', 'mysql_install_db'),
    ('scripts', 'mysql_install_db.pl'),
    ('bin', 'mariadb-install-db'),
    ('bin', 'mariadb-install-db.pl'),
    ('bin', 'mysql_install_db'),
    ('bin', 'mysql_install_db.pl'),
    ('share/mariadb', 'mariadb-install-db'),
    ('share/mysql', 'mysql_install_db'),
]
DUMP_CANDIDATES = [
    ('bin', 'mariadb-dump'),
    ('bin', 'mysqldump'),
    ('client', 'mariadb-dump'),
    ('scripts', 'mariadb-dump'),
]


# --------------------------------------------------------------------------
# readiness probe helpers
# --------------------------------------------------------------------------

def _tar_names(archive):
    names = set()
    with tarfile.open(archive) as archive_file:
        for member in archive_file.getmembers():
            parts = Path(member.name).parts
            if len(parts) > 1:
                names.add('/'.join(parts[1:]))
    return names


def _pkgconfig_version(package):
    executable = shutil.which('pkg-config')
    if not executable:
        return None
    try:
        proc = subprocess.run([executable, '--modversion', package],
                              capture_output=True, text=True, timeout=60)
    except Exception:  # noqa: BLE001
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def system_libfmt():
    """Describe a usable *system* libfmt, or return None."""
    version = _pkgconfig_version('fmt')
    if version:
        return 'pkg-config fmt %s' % version
    for base in ('/usr/include', '/usr/local/include', '/opt/include'):
        if (Path(base) / 'fmt' / 'format.h').is_file():
            return 'headers in %s' % base
    return None


def local_libfmt_source(input_dir):
    """Look for an offline fmt source tree/archive shipped with the task."""
    roots = [Path(input_dir), Path('/workspace/cache'), Path('/opt'),
             Path('/usr/local/src')]
    for root in roots:
        if not root.is_dir():
            continue
        for pattern in ('fmt-*.zip', 'fmt-*.tar.gz', 'fmt-*.tar.xz',
                        'fmt-*.tgz', 'fmt-*'):
            for hit in sorted(root.glob(pattern)):
                if hit.is_dir() and (hit / 'CMakeLists.txt').is_file():
                    return hit
                if hit.is_file() and hit.suffix in ('.zip', '.gz', '.xz', '.tgz'):
                    return hit
    return None


def doctor(input_dir):
    missing = []
    input_dir = Path(input_dir)
    manifest_path = input_dir / 'manifest.json'
    if not manifest_path.is_file():
        return ['source:manifest.json']
    try:
        manifest = json.loads(manifest_path.read_text())
    except Exception as exc:  # noqa: BLE001
        return ['source:manifest.json unreadable (%s)' % exc]

    archive = input_dir / manifest['source']['filename']
    if not archive.is_file():
        missing.append('source:%s' % manifest['source']['filename'])
    for tool in CRITICAL_TOOLS:
        if shutil.which(tool) is None:
            missing.append('tool:%s' % tool)

    if archive.is_file():
        try:
            names = _tar_names(archive)
        except Exception as exc:  # noqa: BLE001
            names = set()
            missing.append('source:archive unreadable (%s)' % exc)
        for entry in CRITICAL_FILES:
            if entry == 'mysql-test/mariadb-test-run.pl':
                if not any('mysql-test/%s' % name in names
                           for name in MTR_SCRIPTS):
                    missing.append('source-file:%s' % entry)
            elif entry not in names:
                missing.append('source-file:%s' % entry)

    if system_libfmt() is None and local_libfmt_source(input_dir) is None:
        missing.append('dependency:libfmt (no system libfmt and no local fmt '
                       'source archive; the build must not download it)')
    return missing


def cmd_doctor(args):
    missing = doctor(args.input)
    if missing:
        print('MISSING:')
        for item in missing:
            print('  - ' + item)
        return 78
    print('READY: source archive, toolchain and offline dependencies present')
    return 0


# --------------------------------------------------------------------------
# build helpers
# --------------------------------------------------------------------------

def _stage_libfmt(session, source):
    """Install an offline fmt source tree so the bundled ExternalProject
    build skips its download step entirely."""
    src_root = session.build / 'extra' / 'libfmt' / 'src'
    stamp = src_root / 'libfmt-stamp'
    target = src_root / 'libfmt'
    staging = src_root / '_unpack'
    if target.exists():
        shutil.rmtree(target)
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    source = Path(source)
    if source.is_dir():
        shutil.copytree(source, staging / 'fmt')
    elif source.suffix == '.zip':
        with zipfile.ZipFile(source) as archive:
            archive.extractall(staging)
    else:
        with tarfile.open(source) as archive:
            archive.extractall(staging, filter='data')
    entries = [entry for entry in sorted(staging.iterdir())
               if entry.name != '__MACOSX']
    root = entries[0] if len(entries) == 1 and entries[0].is_dir() else staging
    shutil.move(str(root), str(target))
    shutil.rmtree(staging, ignore_errors=True)
    stamp.mkdir(parents=True, exist_ok=True)
    for name in LIBFMT_STAMPS:
        (stamp / name).write_text('')


def _known_downloaders(session):
    return sorted(str(path.relative_to(session.build))
                  for path in session.build.glob('**/download-*.cmake'))


def _find_mtr(session):
    for root in (session.build / 'mysql-test', session.src / 'mysql-test'):
        for name in MTR_SCRIPTS:
            candidate = root / name
            if candidate.is_file():
                return candidate
    raise RuntimeError('official MariaDB test runner was not found')


# --------------------------------------------------------------------------
# installed-layout resolution
# --------------------------------------------------------------------------

def _first_existing(install, candidates):
    for directory, filename in candidates:
        path = install / directory / filename
        if path.is_file():
            return path
    leaves = set(filename for _, filename in candidates)
    for hit in sorted(install.rglob('*')):
        if hit.is_file() and hit.name in leaves:
            return hit
    return None


def _resolve_install_db(install):
    return _first_existing(install, INSTALL_DB_CANDIDATES)


def _resolve_dump(install):
    return _first_existing(install, DUMP_CANDIDATES)


def _installed_binaries(install):
    return {
        'server': install / 'bin' / 'mariadbd',
        'client': install / 'bin' / 'mariadb',
        'install_db': _resolve_install_db(install),
        'dump': _resolve_dump(install),
    }


def _invoke_script(script, args):
    """Run an installed helper script, choosing the correct interpreter so a
    non-executable ``*.pl`` variant is never silently skipped."""
    script = Path(script)
    if script.suffix == '.pl':
        return ['perl', str(script)] + list(args)
    if script.is_file() and os.access(script, os.X_OK):
        return [str(script)] + list(args)
    return ['sh', str(script)] + list(args)


# --------------------------------------------------------------------------
# consumer helpers (freshly installed server, local transactions only)
# --------------------------------------------------------------------------

def _spawn_server(session, binary, arguments, tag):
    log = session.output / 'logs' / ('server_%s.log' % tag)
    stream = log.open('ab')
    process = subprocess.Popen([str(binary)] + [str(arg) for arg in arguments],
                               stdout=stream, stderr=subprocess.STDOUT,
                               stdin=subprocess.DEVNULL, start_new_session=True)
    return process, stream


def _stop_server(process, stream):
    if process is not None and process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
    stream.close()


def _wait_socket(path, timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if Path(path).exists():
            return True
        time.sleep(0.5)
    return False


def _sql_text(session, client, statement, name):
    log = session.run(client + ['-e', statement],
                      phase='consumer', name=name, timeout=180)
    return log.read_text(errors='replace')


def _aggregate_row(text):
    for line in reversed([line.strip() for line in text.splitlines()
                          if line.strip()]):
        parts = line.split()
        if len(parts) == 3:
            return parts
    return None


def _consumer(session):
    install = session.install
    binaries = _installed_binaries(install)
    for label, path in binaries.items():
        if path is None or not Path(path).is_file():
            raise RuntimeError('consumer precondition: missing %s at %s'
                               % (label, path))

    root = session.consumer
    data1 = root / 'data1'
    data2 = root / 'data2'
    for directory in (data1, data2):
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True)

    for tag, datadir in (('1', data1), ('2', data2)):
        argv = _invoke_script(binaries['install_db'],
                              ['--no-defaults',
                               '--basedir=%s' % install,
                               '--datadir=%s' % datadir,
                               '--auth-root-authentication-method=normal',
                               '--skip-test-db'])
        session.run(argv, phase='consumer', name='install_db_%s' % tag,
                    timeout=900)

    socket1 = root / 'server1.sock'
    socket2 = root / 'server2.sock'
    client1 = [str(binaries['client']), '--no-defaults',
               '--socket=%s' % socket1, '-u', 'root', '-N', '-B']
    client2 = [str(binaries['client']), '--no-defaults',
               '--socket=%s' % socket2, '-u', 'root', '-N', '-B']
    dump_file = root / 'shop.sql'
    expected = ['3', '6', '30.50']

    process, stream = _spawn_server(session, binaries['server'], [
        '--no-defaults', '--basedir=%s' % install, '--datadir=%s' % data1,
        '--socket=%s' % socket1, '--skip-networking', '--skip-grant-tables',
        '--log-error=%s' % (root / 'server1.err')], '1')
    try:
        if not _wait_socket(socket1):
            raise RuntimeError('private server 1 never opened %s' % socket1)
        session.run(client1 + ['-e',
            'CREATE DATABASE shop; CREATE TABLE shop.orders(id INT PRIMARY KEY, '
            'qty INT NOT NULL, amount DECIMAL(10,2) NOT NULL) ENGINE=InnoDB'],
            phase='consumer', name='create_orders', timeout=180)
        session.run(client1 + ['-e',
            'START TRANSACTION; INSERT INTO shop.orders VALUES (1,2,10.00),(2,3,15.50); COMMIT; '
            'START TRANSACTION; INSERT INTO shop.orders VALUES (99,1,0.01); ROLLBACK; '
            'INSERT INTO shop.orders VALUES (3,1,5.00)'],
            phase='consumer', name='transaction_commit_rollback', timeout=180)
        row = _aggregate_row(_sql_text(session, client1,
            'SELECT COUNT(*), SUM(qty), SUM(amount) FROM shop.orders', 'aggregate'))
        if row != expected:
            raise RuntimeError('transaction aggregate mismatch: %r' % (row,))
        engines = _sql_text(session, client1, 'SHOW ENGINES',
                            'show_engines').lower()
        for engine in ('innodb', 'aria'):
            if engine not in engines:
                raise RuntimeError('installed server lacks the %s engine' % engine)
        session.run([str(binaries['dump']), '--no-defaults',
                     '--socket=%s' % socket1, '-u', 'root',
                     '--databases', 'shop', '-r', str(dump_file)],
                    phase='consumer', name='export_shop', timeout=180)
        if not dump_file.is_file() or dump_file.stat().st_size == 0:
            raise RuntimeError('exported dump file is empty')
    finally:
        _stop_server(process, stream)

    process, stream = _spawn_server(session, binaries['server'], [
        '--no-defaults', '--basedir=%s' % install, '--datadir=%s' % data2,
        '--socket=%s' % socket2, '--skip-networking', '--skip-grant-tables',
        '--log-error=%s' % (root / 'server2.err')], '2')
    try:
        if not _wait_socket(socket2):
            raise RuntimeError('private server 2 never opened %s' % socket2)
        session.run(client2 + ['-e', 'source %s' % dump_file],
                    phase='consumer', name='restore_shop', timeout=180)
        row = _aggregate_row(_sql_text(session, client2,
            'SELECT COUNT(*), SUM(qty), SUM(amount) FROM shop.orders',
            'restore_aggregate'))
        if row != expected:
            raise RuntimeError('restored aggregate mismatch: %r' % (row,))
    finally:
        _stop_server(process, stream)


# --------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------

def run(args):
    missing = doctor(args.input)
    if missing:
        print('MISSING:')
        for item in missing:
            print('  - ' + item)
        return 78

    session = buildkit.Session(args.input, args.output,
                               min(int(args.jobs), BUILD_JOBS_CAP))
    session.prepare()

    fmt = system_libfmt()
    fmt_source = local_libfmt_source(Path(args.input))

    configure = [
        'cmake', '-S', str(session.src), '-B', str(session.build),
        '-G', 'Ninja',
        '-DCMAKE_BUILD_TYPE=RelWithDebInfo',
        '-DCMAKE_INSTALL_PREFIX=%s' % session.install,
        '-DWITH_UNIT_TESTS=ON',
        '-DWITH_SSL=system',
        '-DWITH_LIBFMT=system' if fmt else '-DWITH_LIBFMT=bundled',
        '-DPLUGIN_COLUMNSTORE=NO', '-DPLUGIN_ROCKSDB=NO', '-DPLUGIN_TOKUDB=NO',
        '-DPLUGIN_MROONGA=NO', '-DPLUGIN_SPIDER=NO', '-DPLUGIN_CONNECT=NO',
        '-DPLUGIN_OQGRAPH=NO', '-DWITH_WSREP=OFF', '-DPLUGIN_WSREP=NO',
        '-DWITH_AWS_SDK=OFF', '-DWITH_S3=OFF', '-DPLUGIN_S3=NO',
    ]
    session.run(configure, phase='configure', name='cmake_configure',
                timeout=1800)

    if fmt is None and fmt_source is not None:
        _stage_libfmt(session, fmt_source)
    downloaders = _known_downloaders(session)

    session.run(['cmake', '--build', str(session.build),
                 '--parallel', str(session.jobs)],
                phase='build', name='cmake_build', timeout=9000)

    session.test('ctest_unit',
                 ['ctest', '--test-dir', str(session.build),
                  '--output-on-failure', '-j', str(TEST_JOBS)],
                 cwd=session.build, timeout=3600)

    mtr = _find_mtr(session)
    session.test('mtr_main_insert_select',
                 ['perl', str(mtr), '--parallel=%d' % TEST_JOBS, '--force',
                  '--vardir=%s' % (session.build / 'mtr-var'),
                  'main.insert', 'main.select'],
                 cwd=mtr.parent, timeout=3600)

    session.run(['cmake', '--install', str(session.build)],
                phase='install', name='cmake_install', timeout=1800)

    _consumer(session)

    session.finish(features={
        'installed_binaries': {name: (str(path) if path else None)
                               for name, path in _installed_binaries(session.install).items()},
        'installed_layout': 'STANDALONE (bin/, scripts/, lib/, share/)',
        'libfmt': fmt or ('staged from %s' % fmt_source),
        'external_download_rules_after_configure': downloaders,
        'required_engines': ['InnoDB', 'Aria'],
        'official_harness': mtr.name,
        'consumer_scope': 'local transactions + export/restore',
    })
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog='main.py', description='MariaDB source build driver (BUILDv1-D02)')
    sub = parser.add_subparsers(dest='cmd', required=True)
    run_parser = sub.add_parser('run')
    run_parser.add_argument('--input', required=True)
    run_parser.add_argument('--output', required=True)
    run_parser.add_argument('--jobs', type=int, default=4)
    doctor_parser = sub.add_parser('doctor')
    doctor_parser.add_argument('--input', required=True)
    args = parser.parse_args()
    if args.cmd == 'doctor':
        return cmd_doctor(args)
    return run(args)


if __name__ == '__main__':
    sys.exit(main())
