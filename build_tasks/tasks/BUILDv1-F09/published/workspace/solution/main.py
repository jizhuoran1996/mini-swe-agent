#!/usr/bin/env python3
"""BUILDv1-F09: build LightGBM CPU CLI + native SDK from the frozen source release.

Phases: clang toolchain probe -> cmake configure -> ninja build (CLI, shared
library, cpp tests) -> install -> official testlightgbm suite -> independent
C-API consumer compiled against the freshly installed prefix -> CLI vs C-API
prediction comparison.

Toolchain note: the frozen tests/cpp_tests/test_arrow.cpp uses explicit
template specialisation at class scope, which GCC 13 rejects but Clang accepts,
so the whole project is configured with clang/clang++ (the supported toolchain
for this suite). OpenMP is kept genuinely enabled by probing the real clang
OpenMP flags before configure.

Consumer note: LightGBM's c_api.h transitively includes LightGBM/arrow.h,
which is C++ (it pulls in <algorithm>), so the C-API consumer is compiled as
C++ by the same clang++ toolchain.  LightGBM's C API is a C ABI but its public
header set is only consumable from C++; that is upstream behaviour, not a
workaround.
"""
import argparse
import glob
import json
import shutil
import subprocess
import sys
from pathlib import Path

from buildkit import Session, digest

HERE = Path(__file__).resolve().parent

CLANG_BASES = ['clang-18', 'clang-19', 'clang-17', 'clang']
GTEST_SOURCE_DIRS = ['/usr/src/googletest', '/usr/src/gtest']
GTEST_CONFIG_GLOBS = [
    '/usr/lib/*-linux-gnu/cmake/GTest/GTestConfig.cmake',
    '/usr/lib/cmake/GTest/GTestConfig.cmake',
    '/usr/lib64/cmake/GTest/GTestConfig.cmake',
    '/usr/local/lib/cmake/GTest/GTestConfig.cmake',
]
LIBOMP_GLOBS = [
    '/usr/lib/x86_64-linux-gnu/libomp.so',
    '/usr/lib/x86_64-linux-gnu/libomp.so.*',
    '/usr/lib/llvm-*/lib/libomp.so',
    '/usr/lib64/libomp.so*',
    '/usr/lib/libomp.so*',
]
LIBGOMP_GLOBS = [
    '/usr/lib/gcc/x86_64-linux-gnu/*/libgomp.so',
    '/usr/lib/x86_64-linux-gnu/libgomp.so',
    '/usr/lib/x86_64-linux-gnu/libgomp.so.*',
    '/usr/lib/gcc/x86_64-linux-gnu/*/libgomp.so.*',
    '/usr/lib64/libgomp.so*',
    '/usr/lib/libgomp.so*',
]
OMP_PROBE_SRC = Path('/tmp/_lgbm_omp_probe.cpp')
OMP_PROBE_BIN = Path('/tmp/_lgbm_omp_probe')
OMP_PROBE_CODE = (
    '#include <omp.h>\n'
    '#include <stdio.h>\n'
    'int main(void) {\n'
    '  int threads = omp_get_max_threads();\n'
    '  printf("%d\\n", threads);\n'
    '  return threads > 0 ? 0 : 1;\n'
    '}\n'
)


def find_toolchain():
    """Return (clang, clang++) paths from the first usable pair, else (None, None)."""
    for base in CLANG_BASES:
        cc = shutil.which(base)
        cxx = shutil.which('clang++' + base[len('clang'):])
        if cc and cxx:
            return cc, cxx
    return None, None


def first_glob(patterns):
    for pattern in patterns:
        hits = sorted(glob.glob(pattern))
        if hits:
            return hits[0]
    return None


def find_gtest_source():
    for cand in GTEST_SOURCE_DIRS:
        if (Path(cand) / 'CMakeLists.txt').exists():
            return cand
    return None


def find_gtest_config():
    return first_glob(GTEST_CONFIG_GLOBS)


def omp_probe(cxx, flags):
    OMP_PROBE_SRC.write_text(OMP_PROBE_CODE)
    proc = subprocess.run([cxx] + list(flags) + [str(OMP_PROBE_SRC), '-o', str(OMP_PROBE_BIN)],
                          capture_output=True)
    return proc.returncode == 0


def omp_cmake_args(impl):
    """CMake cache overrides that make find_package(OpenMP REQUIRED) work with clang."""
    if impl == 'libomp':
        args = ['-DOpenMP_C_FLAGS=-fopenmp', '-DOpenMP_CXX_FLAGS=-fopenmp',
                '-DOpenMP_C_LIB_NAMES=omp', '-DOpenMP_CXX_LIB_NAMES=omp']
        lib = first_glob(LIBOMP_GLOBS)
        if lib:
            args.append('-DOpenMP_omp_LIBRARY=' + lib)
        return args
    args = ['-DOpenMP_C_FLAGS=-fopenmp=libgomp', '-DOpenMP_CXX_FLAGS=-fopenmp=libgomp',
            '-DOpenMP_C_LIB_NAMES=gomp', '-DOpenMP_CXX_LIB_NAMES=gomp']
    lib = first_glob(LIBGOMP_GLOBS)
    if lib:
        args.append('-DOpenMP_gomp_LIBRARY=' + lib)
    return args


def doctor(input_dir):
    missing = []
    inp = Path(input_dir).resolve()
    mpath = inp / 'manifest.json'
    if not mpath.exists():
        print('MISSING manifest: %s' % mpath)
        return 78
    manifest = json.loads(mpath.read_text())
    spec = manifest['source']
    archive = inp / spec['filename']
    if not archive.exists():
        missing.append('source archive: %s' % archive)
    else:
        try:
            got = digest(archive)
        except OSError as exc:
            missing.append('source archive unreadable: %s' % exc)
        else:
            if got != spec['sha256']:
                missing.append('source archive sha256 mismatch (%s)' % got)
    for tool in ['cmake', 'ninja', 'gcc', 'g++', 'python3', 'ldd']:
        if shutil.which(tool) is None:
            missing.append('tool not on PATH: %s' % tool)
    cc, cxx = find_toolchain()
    omp_impl = None
    if cc is None:
        missing.append('Clang toolchain (need a clang/clang++ pair such as clang-18/clang++-18)')
    else:
        for label, flags in (('libomp', ['-fopenmp']), ('libgomp', ['-fopenmp=libgomp'])):
            if omp_probe(cxx, flags):
                omp_impl = label
                break
        if omp_impl is None:
            missing.append('OpenMP runtime usable by %s (both -fopenmp and -fopenmp=libgomp probes failed)' % cxx)
    gtest_src = find_gtest_source()
    gtest_cfg = find_gtest_config()
    if gtest_src is None and gtest_cfg is None:
        missing.append('GoogleTest (need an upstream source tree with CMakeLists.txt under %s, '
                       'or a GTestConfig.cmake in a standard prefix)' % GTEST_SOURCE_DIRS)
    if missing:
        for item in missing:
            print('MISSING %s' % item)
        return 78
    print('READY: all prerequisites present')
    print('  clang: %s / %s' % (cc, cxx))
    print('  openmp via: %s' % omp_impl)
    if gtest_src:
        print('  gtest source: %s' % gtest_src)
    if gtest_cfg:
        print('  gtest config: %s' % gtest_cfg)
    return 0


def _has_header(path):
    with open(path) as stream:
        first = stream.readline().strip()
    if not first:
        return False
    for part in first.replace(',', '\t').split('\t'):
        if part.strip():
            try:
                float(part)
            except ValueError:
                return True
            return False
    return False


def _load_preds(path):
    out = []
    with open(path) as stream:
        for line in stream:
            line = line.strip()
            if line:
                out.append(float(line.split()[0]))
    return out


def _compare(a_path, b_path, tol=1e-6):
    a = _load_preds(a_path)
    b = _load_preds(b_path)
    if not a or not b:
        raise AssertionError('empty prediction output (%d vs %d)' % (len(a), len(b)))
    if len(a) != len(b):
        raise AssertionError('prediction length mismatch: %d vs %d' % (len(a), len(b)))
    max_diff = max(abs(x - y) for x, y in zip(a, b))
    if max_diff > tol:
        raise AssertionError('prediction mismatch max_abs_diff=%g > tol=%g' % (max_diff, tol))
    return len(a), max_diff


def pipeline(input_dir, output_dir, jobs):
    s = Session(input_dir, output_dir, jobs=jobs)
    src = s.prepare()
    n = s.jobs

    cc, cxx = find_toolchain()
    if cc is None:
        raise RuntimeError('no clang/clang++ toolchain found; run doctor')

    gtest_src = find_gtest_source()
    gtest_cfg = find_gtest_config()
    if gtest_src is None and gtest_cfg is None:
        raise RuntimeError('GoogleTest required by BUILD_CPP_TEST is unavailable offline; run doctor')

    # Real OpenMP probe: pick flags that actually compile+link with this clang.
    OMP_PROBE_SRC.write_text(OMP_PROBE_CODE)
    omp_impl = None
    for label, flags in (('libomp', ['-fopenmp']), ('libgomp', ['-fopenmp=libgomp'])):
        s.run([cxx] + flags + [str(OMP_PROBE_SRC), '-o', str(OMP_PROBE_BIN)],
              cwd='/tmp', phase='probe', name='omp_probe_' + label, check=False, timeout=180)
        if s.commands[-1]['exit_code'] == 0:
            omp_impl = label
            break
    if omp_impl is None:
        raise RuntimeError('OpenMP is required by this profile but neither -fopenmp nor '
                           '-fopenmp=libgomp works with %s; run doctor' % cxx)

    configure = ['cmake', '-S', str(src), '-B', str(s.build), '-G', 'Ninja',
                 '-DBUILD_CLI=ON', '-DBUILD_CPP_TEST=ON',
                 '-DUSE_GPU=OFF', '-DUSE_CUDA=OFF', '-DUSE_MPI=OFF', '-DUSE_OPENMP=ON',
                 '-DINSTALL_HEADERS=ON', '-DCMAKE_BUILD_TYPE=Release',
                 '-DCMAKE_C_COMPILER=' + cc, '-DCMAKE_CXX_COMPILER=' + cxx,
                 '-DCMAKE_INSTALL_PREFIX=' + str(s.install)]
    configure += omp_cmake_args(omp_impl)
    if gtest_src:
        # LightGBM's find_package(GTest CONFIG) misses the multiarch config here and
        # would otherwise clone from GitHub; resolve FetchContent from local sources.
        configure.append('-DFETCHCONTENT_SOURCE_DIR_GOOGLETEST=' + gtest_src)
    else:
        configure.append('-DGTEST_ROOT=' + str(Path(gtest_cfg).parents[4]))

    s.run(configure, cwd=str(src), phase='configure', name='cmake_configure', timeout=1800)
    s.run(['cmake', '--build', str(s.build), '--parallel', str(n)],
          cwd=str(src), phase='build', name='cmake_build', timeout=5400)
    s.run(['cmake', '--install', str(s.build), '--prefix', str(s.install)],
          cwd=str(src), phase='install', name='cmake_install', timeout=900)

    testbin = None
    for cand in (src / 'testlightgbm', s.build / 'testlightgbm',
                 src / 'Release' / 'testlightgbm', s.build / 'Release' / 'testlightgbm'):
        if cand.exists():
            testbin = cand
            break
    if testbin is None:
        raise RuntimeError('testlightgbm binary not found after build')

    test_env = {'OMP_NUM_THREADS': '2'}
    s.run([str(testbin), '--gtest_list_tests'], cwd=str(src), phase='test_discovery',
          name='gtest_list_tests', env=test_env, timeout=300)
    s.test('testlightgbm', [str(testbin), '--gtest_output=xml:%s' % (s.output / 'cpp_tests.xml')],
           cwd=str(src), parser='gtest_cases', env=test_env, timeout=7200)

    cons = s.consumer
    cons.mkdir(parents=True, exist_ok=True)
    shutil.copy(src / 'examples' / 'regression' / 'regression.train', cons / 'regression.train')
    shutil.copy(src / 'examples' / 'regression' / 'regression.test', cons / 'regression.test')
    # LightGBM's c_api.h transitively includes LightGBM/arrow.h, which is C++;
    # the consumer therefore uses the same clang++ toolchain as the build.
    shutil.copy(HERE / 'consumer.cpp', cons / 'consumer.cpp')

    inst_bin = s.install / 'bin' / 'lightgbm'
    if not inst_bin.exists():
        raise RuntimeError('installed CLI not found: %s' % inst_bin)
    libdir = None
    for p in sorted(s.install.rglob('lib_lightgbm.so*')):
        if p.is_file():
            libdir = p.parent
            break
    if libdir is None:
        raise RuntimeError('installed lib_lightgbm not found under %s' % s.install)
    incdir = s.install / 'include'
    if not (incdir / 'LightGBM' / 'c_api.h').exists():
        raise RuntimeError('installed LightGBM/c_api.h not found under %s' % incdir)

    env = {'OMP_NUM_THREADS': '2'}
    header = _has_header(cons / 'regression.train')
    header_arg = 'header=%s' % ('true' if header else 'false')
    model = cons / 'model.txt'
    cli_preds = cons / 'cli_preds.txt'

    s.run([str(inst_bin), 'task=train', 'data=%s' % (cons / 'regression.train'),
           'objective=regression', 'metric=l2', header_arg,
           'num_iterations=20', 'num_leaves=15', 'learning_rate=0.1',
           'min_data_in_leaf=5', 'verbose=-1', 'seed=42',
           'output_model=%s' % model],
          cwd=str(cons), phase='cli_train', name='cli_train', env=env, timeout=900)

    s.run([str(inst_bin), 'task=predict', 'data=%s' % (cons / 'regression.test'),
           'input_model=%s' % model, 'output_result=%s' % cli_preds,
           'verbose=-1', header_arg],
          cwd=str(cons), phase='cli_predict', name='cli_predict', env=env, timeout=900)

    consumer_bin = cons / 'consumer'
    s.run([cxx, '-O2', '-Wall', '-std=c++11', '-I', str(incdir), str(cons / 'consumer.cpp'),
           '-L', str(libdir), '-l_lightgbm', '-Wl,-rpath,' + str(libdir),
           '-o', str(consumer_bin)],
          cwd=str(cons), phase='consumer_build', name='clang_cpp_consumer', timeout=300)

    c_api_preds = cons / 'c_api_preds.txt'
    s.run([str(consumer_bin), str(model), str(cons / 'regression.test'),
           str(c_api_preds), '0', '1' if header else '0'],
          cwd=str(cons), phase='consumer_run', name='consumer_run', env=env, timeout=900)

    s.run(['ldd', str(consumer_bin)], cwd=str(cons), phase='evidence',
          name='ldd_consumer', check=False, timeout=120)

    rows, maxd = _compare(cli_preds, c_api_preds)

    s.write('consumer_verification.json', {
        'clang': cc, 'clangxx': cxx, 'openmp_impl': omp_impl,
        'cli_binary': str(inst_bin),
        'library_dir': str(libdir),
        'install_include': str(incdir),
        'consumer_binary': str(consumer_bin),
        'consumer_source': str(cons / 'consumer.cpp'),
        'consumer_language': 'c++',
        'rows_compared': rows, 'max_abs_diff': maxd, 'tolerance': 1e-6,
        'header_detected': header,
        'model': str(model), 'cli_predictions': str(cli_preds),
        'c_api_predictions': str(c_api_preds),
        'gtest_source': gtest_src, 'gtest_config': gtest_cfg,
    })

    s.finish(features={'cli': True, 'shared_library': True, 'headers_installed': True,
                       'cpp_tests': True, 'openmp': True, 'openmp_impl': omp_impl,
                       'toolchain': cc, 'c_api_consumer': True,
                       'prediction_match_rows': rows, 'prediction_max_diff': maxd})

    run = json.loads((s.output / 'run.json').read_text())
    run['independent_verified'] = True
    s.write('run.json', run)
    return s


def main(argv=None):
    parser = argparse.ArgumentParser(description='BUILDv1-F09 LightGBM CPU CLI + native SDK builder')
    sub = parser.add_subparsers(dest='cmd')
    run_p = sub.add_parser('run', help='configure/build/install/test/consume LightGBM')
    run_p.add_argument('--input', required=True)
    run_p.add_argument('--output', required=True)
    run_p.add_argument('--jobs', type=int, default=4)
    doc_p = sub.add_parser('doctor', help='report missing source/tool/dependency items')
    doc_p.add_argument('--input', required=True)
    args = parser.parse_args(argv)
    if args.cmd == 'run':
        pipeline(args.input, args.output, args.jobs)
        return 0
    if args.cmd == 'doctor':
        return doctor(args.input)
    parser.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
