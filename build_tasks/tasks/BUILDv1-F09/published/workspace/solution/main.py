#!/usr/bin/env python3
"""BUILDv1-F09: build LightGBM CPU CLI + native SDK from the frozen source release.

Phases: cmake configure -> ninja build (CLI, shared lib, cpp tests) -> install ->
run official testlightgbm suite -> compile an independent C-API consumer against
the freshly installed prefix -> diff CLI predictions vs consumer predictions.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from buildkit import Session, digest

HERE = Path(__file__).resolve().parent

# Order matters: prefer the upstream source tree shipped with the image. CMake's
# find_package(GTest CONFIG) does not search the multiarch layout on this box, so
# LightGBM falls back to FetchContent; pointing it at a local source dir avoids
# the offline network clone.
GTEST_SOURCE_DIRS = [
    '/usr/src/googletest',
    '/usr/src/gtest',
]

GTEST_CONFIG_CANDIDATES = [
    '/usr/lib/x86_64-linux-gnu/cmake/GTest/GTestConfig.cmake',
    '/usr/lib/cmake/GTest/GTestConfig.cmake',
    '/usr/lib64/cmake/GTest/GTestConfig.cmake',
    '/usr/local/lib/cmake/GTest/GTestConfig.cmake',
    '/usr/local/lib64/cmake/GTest/GTestConfig.cmake',
]


def find_gtest_source():
    for cand in GTEST_SOURCE_DIRS:
        root = Path(cand)
        if (root / 'CMakeLists.txt').exists():
            return str(root)
    return None


def find_gtest_config():
    for cand in GTEST_CONFIG_CANDIDATES:
        if Path(cand).exists():
            return cand
    return None


def _omp_ok():
    hello = Path('/tmp/_lgb_omp_probe.cpp')
    hello.write_text('#include <omp.h>\nint main(){return omp_get_num_threads()<=0;}\n')
    out = Path('/tmp/_lgb_omp_probe')
    r = subprocess.run(['g++', '-fopenmp', str(hello), '-o', str(out)],
                       capture_output=True)
    return r.returncode == 0


def doctor(input_dir):
    missing = []
    inp = Path(input_dir).resolve()
    mpath = inp / 'manifest.json'
    if not mpath.exists():
        print('MISSING manifest: %s' % mpath)
        return 78
    manifest = json.loads(mpath.read_text())
    src_spec = manifest['source']
    arch = inp / src_spec['filename']
    if not arch.exists():
        missing.append('source archive: %s' % arch)
    else:
        try:
            got = digest(arch)
        except OSError as exc:
            missing.append('source archive unreadable: %s' % exc)
        else:
            if got != src_spec['sha256']:
                missing.append('source archive sha256 mismatch (%s)' % got)
    for tool in ['cmake', 'ninja', 'gcc', 'g++', 'python3', 'ldd']:
        if shutil.which(tool) is None:
            missing.append('tool not on PATH: %s' % tool)
    if not _omp_ok():
        missing.append('OpenMP (g++ -fopenmp compile probe failed)')
    gtest_src = find_gtest_source()
    gtest_cfg = find_gtest_config()
    if gtest_src is None and gtest_cfg is None:
        missing.append('GoogleTest (need upstream source CMakeLists.txt under %s '
                       'or a GTestConfig.cmake in a standard prefix)' % GTEST_SOURCE_DIRS)
    if missing:
        for item in missing:
            print('MISSING %s' % item)
        return 78
    print('READY: all prerequisites present')
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
    parts = first.replace(',', '\t').split('\t')
    try:
        for p in parts:
            if p.strip():
                float(p)
        return False
    except ValueError:
        return True


def _load_preds(path):
    out = []
    with open(path) as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            out.append(float(line.split()[0]))
    return out


def _compare(a_path, b_path, tol=1e-6):
    a = _load_preds(a_path)
    b = _load_preds(b_path)
    if not a or not b:
        raise AssertionError('empty prediction output (%d vs %d)' % (len(a), len(b)))
    if len(a) != len(b):
        raise AssertionError('prediction length mismatch: %d vs %d' % (len(a), len(b)))
    max_diff = 0.0
    for x, y in zip(a, b):
        d = abs(x - y)
        if d > max_diff:
            max_diff = d
    if max_diff > tol:
        raise AssertionError('prediction mismatch max_abs_diff=%g > tol=%g' % (max_diff, tol))
    return len(a), max_diff


def pipeline(input_dir, output_dir, jobs):
    s = Session(input_dir, output_dir, jobs=jobs)
    src = s.prepare()
    n = s.jobs

    configure = ['cmake', '-S', str(src), '-B', str(s.build), '-G', 'Ninja',
                 '-DBUILD_CLI=ON', '-DBUILD_CPP_TEST=ON',
                 '-DUSE_GPU=OFF', '-DUSE_CUDA=OFF', '-DUSE_MPI=OFF', '-DUSE_OPENMP=ON',
                 '-DINSTALL_HEADERS=ON',
                 '-DCMAKE_INSTALL_PREFIX=' + str(s.install),
                 '-DCMAKE_BUILD_TYPE=Release']

    # Make sure the offline build can satisfy the GTest dependency: prefer the
    # system source tree (honoured by FetchContent), then a real config package.
    gtest_src = find_gtest_source()
    gtest_cfg = find_gtest_config()
    if gtest_src:
        configure.append('-DFETCHCONTENT_SOURCE_DIR_GOOGLETEST=' + gtest_src)
    elif gtest_cfg:
        configure.append('-DGTEST_ROOT=' + str(Path(gtest_cfg).parent.parent.parent.parent))
    else:
        raise RuntimeError(
            'GoogleTest is required for BUILD_CPP_TEST but no source tree or '
            'config package was found; run doctor to see prerequisites')

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

    s.run([str(testbin), '--gtest_list_tests'],
          cwd=str(src), phase='test_discovery', name='gtest_list_tests', timeout=300)

    xml = s.output / 'cpp_tests.xml'
    s.test('testlightgbm', [str(testbin), '--gtest_output=xml:%s' % xml],
           cwd=str(src), parser='gtest_cases', timeout=7200)

    cons = s.consumer
    cons.mkdir(parents=True, exist_ok=True)
    shutil.copy(src / 'examples' / 'regression' / 'regression.train', cons / 'regression.train')
    shutil.copy(src / 'examples' / 'regression' / 'regression.test', cons / 'regression.test')
    shutil.copy(HERE / 'consumer.c', cons / 'consumer.c')

    inst_bin = s.install / 'bin' / 'lightgbm'
    if not inst_bin.exists():
        raise RuntimeError('installed CLI not found: %s' % inst_bin)
    libdir = None
    for p in s.install.rglob('lib_lightgbm.so'):
        libdir = p.parent
        break
    if libdir is None:
        for p in s.install.rglob('lib_lightgbm.*'):
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

    s.run([str(inst_bin), 'task=train',
           'data=%s' % (cons / 'regression.train'),
           'objective=regression', 'metric=l2',
           'num_iterations=20', 'num_leaves=15', 'learning_rate=0.1',
           'min_data_in_leaf=5', 'verbose=-1', 'seed=42',
           header_arg,
           'output_model=%s' % model],
          cwd=str(cons), phase='cli_train', name='cli_train', env=env, timeout=900)

    s.run([str(inst_bin), 'task=predict',
           'data=%s' % (cons / 'regression.test'),
           'input_model=%s' % model,
           'output_result=%s' % cli_preds,
           'verbose=-1', header_arg],
          cwd=str(cons), phase='cli_predict', name='cli_predict', env=env, timeout=900)

    consumer_bin = cons / 'consumer'
    s.run(['gcc', '-O2', '-Wall', '-I', str(incdir), str(cons / 'consumer.c'),
           '-L', str(libdir), '-l_lightgbm',
           '-Wl,-rpath,' + str(libdir),
           '-o', str(consumer_bin)],
          cwd=str(cons), phase='consumer_build', name='gcc_consumer', timeout=300)

    c_api_preds = cons / 'c_api_preds.txt'
    s.run([str(consumer_bin), str(model), str(cons / 'regression.test'),
           str(c_api_preds), '0', '1' if header else '0'],
          cwd=str(cons), phase='consumer_run', name='consumer_run', env=env, timeout=900)

    s.run(['ldd', str(consumer_bin)], cwd=str(cons), phase='evidence',
          name='ldd_consumer', check=False, timeout=120)

    rows, maxd = _compare(cli_preds, c_api_preds)

    s.write('consumer_verification.json', {
        'cli_binary': str(inst_bin),
        'library': str(libdir / 'lib_lightgbm.so'),
        'install_include': str(incdir),
        'consumer_binary': str(consumer_bin),
        'consumer_source': str(cons / 'consumer.c'),
        'rows_compared': rows,
        'max_abs_diff': maxd,
        'tolerance': 1e-6,
        'header_detected': header,
        'cli_predictions': str(cli_preds),
        'c_api_predictions': str(c_api_preds),
        'model': str(model),
        'gtest_source': gtest_src,
    })

    s.finish(features={
        'cli': True,
        'shared_library': True,
        'headers_installed': True,
        'cpp_tests': True,
        'c_api_consumer': True,
        'prediction_match_rows': rows,
        'prediction_max_diff': maxd,
    })

    run = json.loads((s.output / 'run.json').read_text())
    run['independent_verified'] = True
    s.write('run.json', run)
    return s


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='BUILDv1-F09 LightGBM CPU CLI + native SDK builder')
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
