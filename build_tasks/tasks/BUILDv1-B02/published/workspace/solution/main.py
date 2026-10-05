#!/usr/bin/env python3
"""BUILDv1-B02 core: single-source (--disable-bootstrap) GCC 14.2.0 C/C++ build,
installation and official DejaGnu regression subset, plus independent consumers.

All build/configure/install/test/consumer commands go through buildkit.Session so
exit codes, working directories and logs are preserved. Evidence JSON is mirrored
into /artifacts when that directory is writable, because the grading harness reads
run.json from there while the build tree itself lives under /workspace.
"""
import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

import buildkit

TASK_ID = 'BUILDv1-B02'
DEFAULT_OUTPUT = '/workspace/output/install'
ARTIFACTS = Path('/artifacts')

REQUIRED_TOOLS = ['gcc', 'g++', 'make', 'ld', 'ar', 'sed', 'awk', 'perl',
                  'flex', 'bison', 'expect', 'runtest', 'tclsh']
HEADER_DIRS = ['/usr/include', '/usr/include/x86_64-linux-gnu', '/usr/local/include']
LIB_DIRS = ['/usr/lib/x86_64-linux-gnu', '/usr/lib64', '/usr/lib', '/usr/local/lib']
HEADERS = ['gmp.h', 'mpfr.h', 'mpc.h', 'zstd.h']
LIBSTEMS = ['gmp', 'mpfr', 'mpc', 'zstd']

EVIDENCE_FILES = ['run.json', 'tests.json', 'commands.json', 'consumer_report.json',
                  'install_manifest.json', 'install.tar.gz']

HELP = f"""{TASK_ID}: GCC 14.2.0 non-bootstrap C/C++ toolchain build (core profile)

usage:
  main.py --help
  main.py doctor --input INPUT_DIR
  main.py run --input INPUT_DIR [--output OUTPUT_DIR] [--jobs 4]

doctor   verify source archive checksum and the tools/dependencies needed.
         exit 0 when ready to build, exit 78 when anything is missing.
run      configure, --disable-bootstrap build, install, run the official
         DejaGnu subsets (C execute.exp, G++ old-deja.exp), then build and run
         independent consumers against the freshly installed toolchain.
         Evidence is written under OUTPUT_DIR and mirrored into /artifacts.
"""


def find_first(dirs, names):
    for d in dirs:
        for n in names:
            p = Path(d) / n
            if p.exists():
                return p
    return None


def find_lib(stem):
    for d in LIB_DIRS:
        hit = find_first([d], [f'lib{stem}.so', f'lib{stem}.a'])
        if hit:
            return hit
        matches = sorted(Path(d).glob(f'lib{stem}.so.*'))
        if matches:
            return matches[0]
    return None


def doctor_items(input_dir):
    missing = []
    inp = Path(input_dir)
    manifest_path = inp / 'manifest.json'
    if not manifest_path.is_file():
        missing.append('source: manifest not found at ' + str(manifest_path))
    else:
        try:
            manifest = json.loads(manifest_path.read_text())
            spec = manifest['source']
            archive = inp / spec['filename']
            if not archive.is_file():
                missing.append('source: archive not found at ' + str(archive))
            elif buildkit.digest(archive) != spec['sha256']:
                missing.append('source: sha256 mismatch for ' + str(archive))
        except Exception as exc:  # noqa: BLE001 - report the reason, never crash
            missing.append(f'source: unusable manifest.json ({exc})')
    for tool in REQUIRED_TOOLS:
        if shutil.which(tool) is None:
            missing.append('tool: ' + tool)
    for header in HEADERS:
        if find_first(HEADER_DIRS, [header]) is None:
            missing.append('dependency header: ' + header)
    for stem in LIBSTEMS:
        if find_lib(stem) is None:
            missing.append(f'dependency library: lib{stem}.so / lib{stem}.a')
    return missing


def cmd_doctor(args):
    missing = doctor_items(args.input)
    for item in missing:
        print('MISSING ' + item)
    if missing:
        print(f'doctor: {len(missing)} item(s) missing; build cannot start')
        return 78
    print('doctor: source, tools and dependencies present')
    return 0


def write_status(out_dir, payload):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'run.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')


def mirror_evidence(src_dir, max_log_bytes=16 << 20):
    """Copy the small evidence set into /artifacts when it is writable."""
    src_dir = Path(src_dir)
    try:
        if not ARTIFACTS.is_dir() or not os.access(ARTIFACTS, os.W_OK):
            return
    except OSError:
        return
    if ARTIFACTS.resolve() == src_dir.resolve():
        return
    for name in EVIDENCE_FILES:
        path = src_dir / name
        if path.is_file():
            try:
                shutil.copy2(path, ARTIFACTS / name)
            except OSError:
                pass
    logs = src_dir / 'logs'
    if logs.is_dir():
        try:
            (ARTIFACTS / 'logs').mkdir(parents=True, exist_ok=True)
        except OSError:
            return
        for item in logs.iterdir():
            try:
                if item.is_file() and item.stat().st_size <= max_log_bytes:
                    shutil.copy2(item, ARTIFACTS / 'logs' / item.name)
            except OSError:
                pass


def write_consumers(root):
    root.mkdir(parents=True, exist_ok=True)
    (root / 'plain.c').write_text(
        '#include <stdio.h>\n'
        'int main(void) {\n'
        '  unsigned long acc = 0;\n'
        '  for (unsigned long i = 1; i <= 100000UL; ++i) acc += i * i;\n'
        '  printf("C_OK %lu\\n", acc);\n'
        '  return acc == 333338333350000UL ? 0 : 1;\n'
        '}\n')
    (root / 'widget.h').write_text(
        '#pragma once\n#include <stdexcept>\n#include <string>\n'
        'class widget_error : public std::runtime_error {\n'
        ' public: explicit widget_error(const std::string &m) : std::runtime_error(m) {}\n'
        '};\n'
        'std::string widget_format(unsigned long n);\n')
    (root / 'widget.cpp').write_text(
        '#include "widget.h"\n#include <sstream>\n#include <vector>\n'
        'std::string widget_format(unsigned long n) {\n'
        '  if (n == 0) throw widget_error("zero not accepted");\n'
        '  std::vector<unsigned long> digits;\n'
        '  while (n) { digits.push_back(n % 10); n /= 10; }\n'
        '  std::ostringstream out;\n'
        '  for (auto it = digits.rbegin(); it != digits.rend(); ++it) out << *it;\n'
        '  return out.str();\n'
        '}\n')
    (root / 'consumer.cpp').write_text(
        '#include "widget.h"\n#include <cstdio>\n#include <fstream>\n'
        '#include <stdexcept>\n#include <string>\n#include <thread>\n'
        '#include <vector>\n'
        'static std::string loaded_cxx_runtime() {\n'
        '  std::ifstream maps("/proc/self/maps");\n'
        '  std::string line;\n'
        '  while (std::getline(maps, line))\n'
        '    if (line.find("libstdc++") != std::string::npos) return line;\n'
        '  return "libstdc++ NOT MAPPED";\n'
        '}\n'
        'int main() {\n'
        '  std::thread worker([]{\n'
        '    std::vector<std::string> parts;\n'
        '    for (unsigned long i = 1; i <= 32; ++i) parts.push_back(widget_format(i * 131));\n'
        '    if (parts.size() != 32) throw std::runtime_error("bad vector size");\n'
        '  });\n'
        '  worker.join();\n'
        '  bool threw = false;\n'
        '  try { widget_format(0); } catch (const widget_error &) { threw = true; }\n'
        '  if (!threw) { std::fprintf(stderr, "exception did not cross library boundary\\n"); return 2; }\n'
        '  std::string maps = loaded_cxx_runtime();\n'
        '  std::printf("CXX_OK %s\\n", widget_format(4242).c_str());\n'
        '  std::printf("CXX_RUNTIME %s\\n", maps.c_str());\n'
        '  return maps.find("libstdc++") == std::string::npos ? 3 : 0;\n'
        '}\n')
    return root


def do_run(args):
    out = Path(args.output)
    missing = doctor_items(args.input)
    if missing:
        for item in missing:
            print('MISSING ' + item)
        print('run: refusing to build; run doctor for the full list', file=sys.stderr)
        return 78

    write_status(out, {'task_id': TASK_ID, 'profile': 'core', 'status': 'started',
                       'bootstrap': False, 'execution_complete': False,
                       'started_unix': time.time()})
    mirror_evidence(out)

    session = buildkit.Session(args.input, out, args.jobs)
    source = session.prepare()
    build = session.build
    install = session.install
    env = {'MAKEINFO': 'true', 'LC_ALL': 'C'}

    session.run([str(source / 'configure'), f'--prefix={install}',
                 '--enable-languages=c,c++', '--disable-bootstrap',
                 '--disable-multilib', '--disable-nls', '--disable-libstdcxx-pch',
                 '--enable-checking=release', '--with-system-zlib'],
                cwd=build, phase='configure', name='configure', env=env, timeout=3600)
    session.run(['make', f'-j{session.jobs}'], cwd=build, phase='build',
                name='make_all', env=env, timeout=21600)
    session.run(['make', f'-j{session.jobs}', 'install'], cwd=build, phase='install',
                name='make_install', env=env, timeout=7200)

    for rel in ('bin/gcc', 'bin/g++', 'bin/cpp'):
        if not (install / rel).exists():
            raise RuntimeError(f'installed toolchain incomplete: {install / rel} missing')

    gcc_dir = build / 'gcc'
    session.test('c_execute', ['make', '-j2', 'check-gcc', 'RUNTESTFLAGS=execute.exp'],
                 cwd=gcc_dir, env=env, timeout=14400)
    session.test('cpp_old_deja', ['make', '-j2', 'check-g++', 'RUNTESTFLAGS=old-deja.exp'],
                 cwd=gcc_dir, env=env, timeout=14400)

    consumer = write_consumers(session.consumer)
    libpath = ':'.join(str(p) for p in (install / 'lib64', install / 'lib', install / 'lib32')
                       if p.exists()) or str(install / 'lib')
    cenv = {'LD_LIBRARY_PATH': libpath,
            'PATH': str(install / 'bin') + ':' + os.environ.get('PATH', '')}

    gcc = str(install / 'bin' / 'gcc')
    gpp = str(install / 'bin' / 'g++')
    session.run([gcc, '-dumpmachine'], cwd=consumer, phase='consumer', name='dumpmachine', env=cenv)
    session.run([gcc, '-O2', '-Wall', '-o', 'plain', 'plain.c'], cwd=consumer,
                phase='consumer', name='build_c', env=cenv)
    session.run(['./plain'], cwd=consumer, phase='consumer', name='run_c', env=cenv)
    session.run([gpp, '-O2', '-std=c++17', '-Wall', '-fPIC', '-shared',
                 '-o', 'libwidget.so', 'widget.cpp'], cwd=consumer,
                phase='consumer', name='build_widget', env=cenv)
    session.run([gpp, '-O2', '-std=c++17', '-Wall', '-o', 'consumer', 'consumer.cpp',
                 '-L.', '-lwidget', '-Wl,-rpath,$ORIGIN', '-pthread'],
                cwd=consumer, phase='consumer', name='build_consumer', env=cenv)
    out_log = session.run(['./consumer'], cwd=consumer, phase='consumer',
                          name='run_consumer', env=cenv)

    text = out_log.read_text(errors='replace')
    if 'CXX_OK 4242' not in text:
        raise RuntimeError('consumer semantics failed; see ' + str(out_log))
    if str(install) not in text:
        raise RuntimeError('new libstdc++ not loaded from install prefix; see ' + str(out_log))

    session.write('consumer_report.json', {
        'compiler': gcc, 'cxx': gpp, 'libstdcxx_search_path': libpath,
        'runtime_map_line': next((ln for ln in text.splitlines() if 'libstdc++' in ln), ''),
        'bootstrap': False, 'profile': 'core'})
    session.finish(features={'task_id': TASK_ID, 'profile': 'core', 'disable_bootstrap': True,
                             'languages': ['c', 'c++'], 'multilib': False,
                             'official_tests': ['execute.exp', 'old-deja.exp']})
    mirror_evidence(out)
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(add_help=False, prog='main.py')
    parser.add_argument('command', nargs='?', default=None)
    parser.add_argument('--help', '-h', action='store_true')
    parser.add_argument('--input', default='/workspace/input')
    parser.add_argument('--output', default=None)
    parser.add_argument('--jobs', type=int, default=4)
    args, _extra = parser.parse_known_args(argv)

    if args.help or args.command is None:
        print(HELP)
        return 0

    if args.output is None:
        try:
            artifact_ok = ARTIFACTS.is_dir() and os.access(ARTIFACTS, os.W_OK)
        except OSError:
            artifact_ok = False
        args.output = str(ARTIFACTS) if artifact_ok else DEFAULT_OUTPUT

    if args.command == 'doctor':
        return cmd_doctor(args)
    if args.command != 'run':
        print(f'unknown command: {args.command}', file=sys.stderr)
        print(HELP, file=sys.stderr)
        return 2

    try:
        return do_run(args)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - persist evidence before failing
        write_status(args.output, {'task_id': TASK_ID, 'profile': 'core',
                                   'status': 'failed', 'bootstrap': False,
                                   'execution_complete': False,
                                   'error': f'{type(exc).__name__}: {exc}'})
        mirror_evidence(Path(args.output))
        raise


if __name__ == '__main__':
    sys.exit(main())
