#!/usr/bin/env python3
"""BUILDv1-B03: build GNU binutils 2.44 core (binutils/gas/ld) from source and validate ELF toolkit."""
import argparse
import json
import shutil
import sys
from pathlib import Path

import buildkit


REQUIRED_TOOLS = ('as', 'ld', 'ar', 'nm', 'objcopy', 'objdump', 'readelf')


def doctor(input_dir):
    input_dir = Path(input_dir).resolve()
    missing = []
    manifest_path = input_dir / 'manifest.json'
    manifest = None
    if not manifest_path.is_file():
        missing.append(str(manifest_path))
    else:
        try:
            manifest = json.loads(manifest_path.read_text())
        except Exception as exc:
            missing.append(f'{manifest_path}: invalid JSON: {exc}')
    if manifest:
        source = manifest.get('source', {})
        archive = input_dir / source.get('filename', '')
        if not archive.is_file():
            missing.append(str(archive))
        else:
            actual = buildkit.digest(archive)
            if actual != source.get('sha256'):
                missing.append(f'{archive}: sha256 mismatch (expected {source.get("sha256")}, got {actual})')
    for tool in ('gcc', 'make', 'sed', 'awk', 'grep', 'ar', 'ranlib', 'runtest', 'expect', 'tclsh'):
        if not shutil.which(tool):
            missing.append(f'tool: {tool}')
    if missing:
        print(json.dumps({'status': 'missing', 'items': missing}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 78
    print(json.dumps({'status': 'ready'}, ensure_ascii=False))
    return 0


def find_tool(install, target, name):
    """Locate a newly installed tool; handle optional ${target}- program prefix."""
    bindir = install / 'bin'
    candidates = [bindir / name, bindir / f'{target}-{name}']
    for candidate in candidates:
        if candidate.is_file() and not candidate.is_symlink():
            return candidate
    # Fall back to any prefixed match, still under the install prefix.
    for candidate in sorted(bindir.glob(f'*-{name}')):
        if candidate.is_file() and not candidate.is_symlink():
            return candidate
    return None


def gcc_query(sessions, cwd, name, *args):
    log = sessions.run(['gcc', *args], cwd=cwd, phase='consumer', name=name, timeout=120)
    return log.read_text().strip()


def consumer(sessions, target, expected_version):
    install = sessions.install
    consumer_dir = sessions.consumer
    consumer_dir.mkdir(parents=True, exist_ok=True)
    (consumer_dir / 'main.c').write_text(
        '#include <stdio.h>\n'
        'int add(int a, int b);\n'
        'int main(void) { int r = add(2, 3); printf("hello add=%d\\n", r); return r == 5 ? 0 : 1; }\n'
    )
    (consumer_dir / 'math.c').write_text('int add(int a, int b) { return a + b; }\n')

    tools = {}
    for name in REQUIRED_TOOLS:
        path = find_tool(install, target, name)
        if path is None:
            raise RuntimeError(f'missing installed tool: {name} under {install}/bin')
        tools[name] = str(path)

    def run_consumer(argv, name, timeout=300):
        return sessions.run(argv, cwd=consumer_dir, phase='consumer', name=name, timeout=timeout)

    versions = {}
    for tool, path in tools.items():
        text = run_consumer([path, '--version'], f'{tool}_version').read_text()
        if 'GNU' not in text:
            raise RuntimeError(f'{tool} --version did not look like GNU output: {text[:200]}')
        first = text.splitlines()[0] if text.splitlines() else ''
        if expected_version and expected_version not in text:
            raise RuntimeError(f'{tool} is not {expected_version}: {first}')
        versions[tool] = {'path': path, 'first_line': first}

    as_path = tools['as']
    ar_path = tools['ar']
    ld_path = tools['ld']
    nm_path = tools['nm']
    readelf_path = tools['readelf']
    objdump_path = tools['objdump']
    objcopy_path = tools['objcopy']

    run_consumer(['gcc', '-S', '-o', 'main.s', 'main.c'], 'gcc_main_s')
    run_consumer(['gcc', '-S', '-o', 'math.s', 'math.c'], 'gcc_math_s')
    run_consumer([as_path, '-o', 'main.o', 'main.s'], 'as_main_o')
    run_consumer([as_path, '-o', 'math.o', 'math.s'], 'as_math_o')
    run_consumer([ar_path, 'rcs', 'libmath.a', 'math.o'], 'ar_libmath')

    crt1 = gcc_query(sessions, consumer_dir, 'gcc_print_crt1', '-print-file-name=crt1.o')
    crti = gcc_query(sessions, consumer_dir, 'gcc_print_crti', '-print-file-name=crti.o')
    crtn = gcc_query(sessions, consumer_dir, 'gcc_print_crtn', '-print-file-name=crtn.o')
    libc = gcc_query(sessions, consumer_dir, 'gcc_print_libc', '-print-file-name=libc.so')
    dyn = gcc_query(sessions, consumer_dir, 'gcc_print_dyn', '-print-file-name=ld-linux-x86-64.so.2')
    if not Path(dyn).is_file():
        dyn = '/lib64/ld-linux-x86-64.so.2'
    libdirs = []
    for path in (crt1, crti, crtn, libc):
        parent = str(Path(path).parent)
        if parent not in libdirs:
            libdirs.append(parent)

    link_cmd = [ld_path, '-o', 'hello', '-dynamic-linker', dyn,
                crt1, crti, 'main.o', 'libmath.a',
                *[f'-L{d}' for d in libdirs], '-lc', crtn]
    run_consumer(link_cmd, 'ld_link')

    out = run_consumer(['./hello'], 'run_hello').read_text()
    if 'hello add=5' not in out:
        raise RuntimeError(f'unexpected hello output: {out!r}')

    elf = run_consumer([readelf_path, '-h', 'hello'], 'readelf_hello').read_text()
    for token in ('ELF64', 'X86-64'):
        if token not in elf:
            raise RuntimeError(f'readelf missing {token}: {elf[:500]}')
    if 'EXEC' not in elf and 'DYN' not in elf:
        raise RuntimeError(f'readelf missing EXEC/DYN: {elf[:500]}')

    dis = run_consumer([objdump_path, '-d', 'hello'], 'objdump_hello').read_text()
    if 'call' not in dis:
        raise RuntimeError('objdump did not show call instruction')

    syms = run_consumer([nm_path, 'hello'], 'nm_hello').read_text()
    if ' add' not in syms and 'T add' not in syms:
        raise RuntimeError(f'nm did not show add symbol: {syms[:500]}')

    run_consumer([objcopy_path, '--only-keep-debug', 'hello', 'hello.debug'], 'objcopy_debug')
    run_consumer([objcopy_path, '--strip-debug', 'hello', 'hello.stripped'], 'objcopy_strip')
    run_consumer(['chmod', '+x', 'hello.stripped'], 'chmod_stripped')
    stripped_out = run_consumer(['./hello.stripped'], 'run_stripped').read_text()
    if 'hello add=5' not in stripped_out:
        raise RuntimeError(f'stripped hello failed: {stripped_out!r}')
    run_consumer([objcopy_path, '--add-gnu-debuglink=hello.debug', 'hello.stripped'], 'objcopy_debuglink')

    sessions.write('tool_versions.json', versions)
    sessions.write('consumer.json', {
        'install_prefix': str(install),
        'program_prefix': str(Path(tools['as']).name)[:-len('as')] or '',
        'tools': tools,
        'dynamic_linker': dyn,
        'runtime_objects': [crt1, crti, crtn, libc],
        'ran': 'hello add=5',
    })


def run(input_dir, output_dir, jobs):
    sessions = buildkit.Session(input_dir, output_dir, jobs)
    manifest = sessions.manifest
    sessions.prepare()
    src = sessions.src
    build = sessions.build
    install = sessions.install
    target = 'x86_64-linux-gnu'
    expected_version = (manifest.get('source', {}).get('release_ref') or '').replace('binutils-', '') or '2.44'

    inventory = {}
    for pattern in ['binutils/testsuite/**/*.exp', 'gas/testsuite/**/*.exp',
                    'ld/testsuite/**/*.exp', 'ld/testsuite/ld-shared/*.exp']:
        inventory[pattern] = sorted(str(p.relative_to(src)) for p in src.glob(pattern))
    sessions.write('test_inventory.json', inventory)

    configure_args = [
        str(src / 'configure'),
        f'--target={target}',
        f'--prefix={install}',
        '--program-prefix=',
        '--disable-gdb',
        '--disable-gdbserver',
        '--disable-gold',
        '--disable-gprofng',
        '--disable-werror',
    ]
    sessions.run(configure_args, cwd=build, phase='configure', name='configure', timeout=1800)
    sessions.run(['make', f'-j{jobs}', 'all'], cwd=build, phase='build', name='make_all', timeout=10800)

    test_jobs = min(jobs, 2)
    sessions.test('check-binutils', ['make', f'-j{test_jobs}', 'check-binutils'], cwd=build,
                  parser='dejagnu_pass', timeout=3600)
    sessions.test('check-gas', ['make', f'-j{test_jobs}', 'check-gas'], cwd=build,
                  parser='dejagnu_pass', timeout=3600)
    sessions.test('ld-shared', ['make', f'-j{test_jobs}', '-C', 'ld', 'check',
                                'RUNTESTFLAGS=ld-shared/shared.exp'], cwd=build,
                  parser='dejagnu_pass', timeout=1800)

    sessions.run(['make', 'install'], cwd=build, phase='install', name='make_install', timeout=1800)

    # Record the actual installed layout before consuming it.
    bin_files = sorted(str(p.relative_to(install)) for p in (install / 'bin').rglob('*') if p.is_file())
    sessions.write('installed_bin.json', bin_files)

    consumer(sessions, target, expected_version)

    features = {
        'profile': 'core',
        'configure_flags': configure_args[1:],
        'target': target,
        'tools_built': ['as', 'ld', 'ar', 'nm', 'objcopy', 'objdump', 'readelf'],
        'official_tests': [t['selector'] for t in sessions.tests],
        'consumer': 'archive+link+strip verified with newly built tools',
        'independent_consumer_dir': str(sessions.consumer),
    }
    sessions.finish(features)


def main(argv):
    if len(argv) < 2 or argv[1] in ('--help', '-h'):
        print("""Usage:
  python3 solution/main.py run --input DIR --output DIR [--jobs N]
  python3 solution/main.py doctor --input DIR

Commands:
  run     configure, build, test, install GNU binutils core, then validate consumer.
  doctor  check source archive and required host tools; exit 78 if any are missing.

Options:
  --input DIR   directory containing manifest.json and source archive
  --output DIR  writable output directory for logs, install tree and evidence
  --jobs N      build parallelism (default: 4)
""")
        return 0
    cmd = argv[1]
    if cmd == 'doctor':
        parser = argparse.ArgumentParser(prog='main.py doctor')
        parser.add_argument('--input', required=True)
        args = parser.parse_args(argv[2:])
        return doctor(args.input)
    if cmd == 'run':
        parser = argparse.ArgumentParser(prog='main.py run')
        parser.add_argument('--input', required=True)
        parser.add_argument('--output', required=True)
        parser.add_argument('--jobs', type=int, default=4)
        args = parser.parse_args(argv[2:])
        run(args.input, args.output, args.jobs)
        return 0
    print(f'unknown command: {cmd}', file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
