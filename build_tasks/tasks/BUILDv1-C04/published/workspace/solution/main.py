#!/usr/bin/env python3
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
import buildkit

REQUIRED_DEPS = [
    'glib-2.0', 'gio-2.0', 'gobject-2.0', 'gmodule-no-export-2.0',
    'expat', 'libjpeg', 'libpng', 'libtiff-4',
]
REQUIRED_TOOLS = ['meson', 'ninja', 'pkg-config', 'gcc', 'g++']
SELECTORS = [
    'cli', 'formats', 'seq', 'stall', 'threading',
    'keep', 'token', 'connections', 'descriptors',
]

def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()

def doctor(input_dir):
    input_dir = Path(input_dir)
    missing = []
    manifest_path = input_dir / 'manifest.json'
    if not manifest_path.exists():
        missing.append(f'manifest.json at {manifest_path}')
    else:
        manifest = json.loads(manifest_path.read_text())
        src = manifest.get('source', {})
        archive = input_dir / src.get('filename', '')
        if not archive.exists():
            missing.append(f'source archive {archive}')
        else:
            expected = src.get('sha256')
            if expected and sha256(archive) != expected:
                missing.append(f'source archive checksum mismatch for {archive}')
    for tool in REQUIRED_TOOLS:
        if not shutil.which(tool):
            missing.append(f'tool {tool}')
    for dep in REQUIRED_DEPS:
        try:
            subprocess.run(['pkg-config', '--exists', dep], check=True,
                           capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            missing.append(f'dependency {dep}')
    if missing:
        for item in missing:
            print(f'MISSING: {item}', file=sys.stderr)
        return 78
    print('doctor: ready')
    return 0

def run(input_dir, output_dir, jobs):
    session = buildkit.Session(input_dir, output_dir, jobs)
    session.prepare()
    src = session.src
    build = session.build
    install = session.install

    # v8.16.1 has no -Dtests / -Dtools options: CLI and official tests are
    # built by default whenever we build the project. Only override the core
    # options that actually exist.
    session.run([
        'meson', 'setup', str(build), str(src),
        '--prefix', str(install),
        '--libdir', 'lib',
        '--wrap-mode=nodownload',
        '-Dcplusplus=true',
        '-Dintrospection=disabled',
        '-Dmagick=disabled',
        '-Djpeg=enabled', '-Dpng=enabled', '-Dtiff=enabled',
    ], cwd=src, phase='configure', name='meson_setup', timeout=1800)

    session.run(['meson', 'compile', '-C', str(build), '-j', str(session.jobs)],
                cwd=src, phase='build', name='meson_compile', timeout=7200)

    log = session.run(['meson', 'test', '-C', str(build), '--list'],
                      cwd=src, phase='test_discovery', name='meson_test_list', timeout=300)
    inventory = [line.strip() for line in log.read_text().splitlines() if line.strip()]
    session.write('test_inventory.json', inventory)
    missing = [s for s in SELECTORS if s not in inventory]
    if missing:
        raise RuntimeError(f'required test selectors missing from inventory: {missing}')

    test_jobs = min(2, session.jobs)
    session.test('meson_tests', [
        'meson', 'test', '-C', str(build), '-j', str(test_jobs), '--print-errorlogs'
    ] + SELECTORS, cwd=src, parser='auto', timeout=3600)

    session.run(['meson', 'install', '-C', str(build)],
                cwd=src, phase='install', name='meson_install', timeout=900)

    vips_bin = install / 'bin' / 'vips'
    libvips = install / 'lib' / 'libvips.so'
    header = install / 'include' / 'vips' / 'vips.h'
    pc = install / 'lib' / 'pkgconfig' / 'vips.pc'
    pc_cpp = install / 'lib' / 'pkgconfig' / 'vips-cpp.pc'
    for p in [vips_bin, libvips, header, pc, pc_cpp]:
        if not p.exists():
            raise RuntimeError(f'expected installed artifact missing: {p}')

    consumer = session.consumer
    consume_src = Path(__file__).parent / 'consumer' / 'consume.cpp'
    if not consume_src.exists():
        raise RuntimeError(f'consumer source missing: {consume_src}')
    shutil.copy(str(consume_src), str(consumer / 'consume.cpp'))
    env = {
        'PKG_CONFIG_PATH': str(install / 'lib' / 'pkgconfig'),
        'LD_LIBRARY_PATH': str(install / 'lib'),
    }

    session.run([str(vips_bin), '--version'],
                cwd=consumer, phase='consumer', name='vips_version', env=env, timeout=30)

    pkg_log = session.run(['pkg-config', '--cflags', '--libs', 'vips-cpp'],
                          cwd=consumer, phase='consumer', name='pkgconfig_vips_cpp',
                          env=env, timeout=60)
    flags = pkg_log.read_text().strip().split()
    session.run(['g++', '-std=c++11', 'consume.cpp', '-o', 'consume'] + flags,
                cwd=consumer, phase='consumer', name='compile_consumer', env=env, timeout=300)
    session.run([str(consumer / 'consume')],
                cwd=consumer, phase='consumer', name='run_consumer', env=env, timeout=120)

    out_png = consumer / 'out.png'
    if not out_png.exists() or out_png.stat().st_size == 0:
        raise RuntimeError('consumer did not produce out.png')

    features = {
        'formats': ['png', 'jpeg', 'tiff'],
        'cplusplus': True,
        'cli': True,
        'tests': SELECTORS,
    }
    session.finish(features=features)

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('--help', '-h'):
        print('Usage: main.py {run,doctor} --input INPUT [--output OUTPUT] [--jobs N]')
        print('  run    : build, test, install libvips and run external consumer')
        print('  doctor : check source, tools, and dependencies without building')
        sys.exit(0)
    cmd = sys.argv[1]
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', default='output')
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args(sys.argv[2:])
    if cmd == 'doctor':
        sys.exit(doctor(args.input))
    elif cmd == 'run':
        run(args.input, args.output, args.jobs)
    else:
        print(f'unknown command: {cmd}', file=sys.stderr)
        sys.exit(2)

if __name__ == '__main__':
    main()
