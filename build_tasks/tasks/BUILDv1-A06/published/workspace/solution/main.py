#!/usr/bin/env python3
import argparse, hashlib, json, shutil, sys
from pathlib import Path
import buildkit

TESTS = ['timer', 'spawn_exit_code', 'threadpool_queue_work_simple']

def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()

def doctor(input_dir):
    missing = []
    mp = input_dir / 'manifest.json'
    if not mp.exists():
        missing.append('manifest.json at ' + str(mp))
    else:
        try:
            manifest = json.loads(mp.read_text())
        except Exception as exc:
            manifest = None
            missing.append('manifest.json unreadable: ' + str(exc))
        if manifest:
            src = manifest.get('source', {})
            arch = input_dir / src.get('filename', '')
            if not arch.exists():
                missing.append('source archive ' + str(arch))
            elif sha256(arch) != src.get('sha256'):
                missing.append('source archive checksum mismatch for ' + str(arch))
    for tool in ['cmake', 'cc', 'make']:
        if shutil.which(tool) is None:
            missing.append('tool ' + tool)
    if missing:
        print('doctor: missing prerequisites:')
        for item in missing:
            print(' - ' + item)
        return 78
    print('doctor: ready')
    return 0

def run(input_dir, output_dir, jobs):
    session = buildkit.Session(input_dir, output_dir, jobs=jobs)
    session.prepare()
    src = str(session.src)
    build = str(session.build)
    install = str(session.install)
    session.run(['cmake', '-S', src, '-B', build,
                 '-DCMAKE_BUILD_TYPE=Release',
                 '-DCMAKE_INSTALL_PREFIX=' + install,
                 '-DBUILD_TESTING=ON'], phase='configure', name='configure', timeout=900)
    session.run(['cmake', '--build', build, '--parallel', str(session.jobs)],
                phase='build', name='build', timeout=3600)
    runner = session.build / 'uv_run_tests_a'
    if not runner.exists():
        raise RuntimeError('uv_run_tests_a not built')
    session.run([str(runner), '--list'], cwd=build, phase='discovery', name='test_list',
                check=False, timeout=120)
    for name in TESTS:
        session.test(name, [str(runner), name], cwd=build, timeout=300)
    session.run(['cmake', '--install', build], phase='install', name='install', timeout=900)
    inc = None
    libdir = None
    for p in session.install.rglob('uv.h'):
        inc = p.parent
        break
    for p in session.install.rglob('libuv.*'):
        if p.is_file() and not p.is_symlink() and (p.name.endswith('.so') or p.name.endswith('.a')):
            libdir = p.parent
            break
    if inc is None or libdir is None:
        raise RuntimeError('installed uv.h or libuv library missing')
    shutil.copyfile(Path(__file__).resolve().parent / 'consumer.c', session.consumer / 'consumer.c')
    data = session.consumer / 'data.txt'
    data.write_text('alpha\nbeta\ngamma\n')
    binary = session.consumer / 'consumer'
    # gnu11 exposes the real POSIX/GNU feature surface (pthread_rwlock_t,
    # addrinfo, sockaddr_in) that libuv's public headers reference.
    session.run(['cc', '-std=gnu11', '-Wall', '-Wextra',
                 '-D_GNU_SOURCE', '-D_POSIX_C_SOURCE=200809L',
                 '-o', str(binary), str(session.consumer / 'consumer.c'),
                 '-I' + str(inc), '-L' + str(libdir),
                 '-Wl,-rpath,' + str(libdir), '-luv', '-pthread'],
                cwd=str(session.consumer), phase='consumer_build', name='consumer_build', timeout=300)
    ldd_log = session.run(['ldd', str(binary)], cwd=str(session.consumer), phase='consumer_link',
                          name='consumer_ldd', timeout=60)
    ldd_text = ldd_log.read_text()
    if 'libuv' not in ldd_text or str(libdir) not in ldd_text:
        raise RuntimeError('consumer did not resolve the freshly installed libuv: ' + ldd_text)
    session.run([str(binary), str(data)], cwd=str(session.consumer), phase='consumer_run',
                name='consumer_run', timeout=120)
    session.finish(features={'official_tests': TESTS, 'install_prefix': install,
                             'consumer': 'C async fs/spawn/work/timer/tcp echo'})
    return 0

def main():
    parser = argparse.ArgumentParser(prog='solution/main.py')
    sub = parser.add_subparsers(dest='command')
    p_run = sub.add_parser('run')
    p_run.add_argument('--input', default='input')
    p_run.add_argument('--output', default='output')
    p_run.add_argument('--jobs', type=int, default=4)
    p_doctor = sub.add_parser('doctor')
    p_doctor.add_argument('--input', default='input')
    args = parser.parse_args()
    if args.command == 'doctor':
        return doctor(Path(args.input).resolve())
    if args.command == 'run':
        return run(Path(args.input).resolve(), Path(args.output).resolve(), args.jobs)
    parser.print_help()
    return 2

if __name__ == '__main__':
    sys.exit(main())
