#!/usr/bin/env python3
"""BUILDv1-C09 (core profile): build the GDAL raster/vector distribution from
source, install it, run the frozen official C++/Python test selections, and
consume the freshly built SDK/CLI/Python bindings from outside the source tree."""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import buildkit
from buildkit import Session

WS = Path('/workspace')
WHEELHOUSE = Path('/opt/wheelhouse')
TEST_JOBS = 2

# Packages installed into the build/consumer venv from the offline wheelhouse.
# Upstream GDAL's autotest/conftest.py imports `filelock` (proj search-path
# locking) and its pytest.ini declares an `env =` section handled by pytest-env
# (which itself needs python-dotenv). All of these are hard requirements now.
# Names are *distribution* names; on disk wheel filenames normalize both '-' and
# '.' to '_' (PEP 503 / wheel spec), which is why matching is normalized too.
REQUIRED_DISTS = ['numpy', 'pytest', 'pytest-xdist', 'pytest-env',
                  'setuptools', 'wheel', 'packaging', 'filelock',
                  'python-dotenv', 'execnet']

# Inline header probe.  Imports sys explicitly (calling sys.exit without
# importing sys raises NameError, which subprocess silently drops and would
# masquerade as a missing Python.h).  The build-tool venv prefix is *not*
# required to ship headers; the real Ubuntu python3.12-dev headers under
# /usr/include/python3.12 are accepted.
HEADER_PROBE = (
    "import os, sys, sysconfig, glob, subprocess\n"
    "cands = []\n"
    "try:\n"
    "    v = sysconfig.get_config_var('INCLUDEPY')\n"
    "    if v: cands.append(v)\n"
    "except Exception: pass\n"
    "try:\n"
    "    p = sysconfig.get_paths()\n"
    "    for key in ('include', 'platinclude'):\n"
    "        v = p.get(key)\n"
    "        if v: cands.append(v)\n"
    "except Exception: pass\n"
    "for tool in (['pkg-config', '--variable=includedir', 'python-3.12'],\n"
    "             ['python3-config', '--includes']):\n"
    "    try:\n"
    "        r = subprocess.run(tool, capture_output=True, text=True, timeout=10)\n"
    "        out = r.stdout or ''\n"
    "    except Exception:\n"
    "        out = ''\n"
    "    for tok in out.split():\n"
    "        cands.append(tok[2:] if tok.startswith('-I') else tok)\n"
    "cands += sorted(glob.glob('/usr/include/python3.*'))\n"
    "cands += ['/usr/include/python3.12', '/usr/include']\n"
    "seen = set()\n"
    "for c in cands:\n"
    "    if not c or c in seen: continue\n"
    "    seen.add(c)\n"
    "    if os.path.exists(os.path.join(c, 'Python.h')):\n"
    "        print(c); sys.exit(0)\n"
    "print(''); sys.exit(1)\n"
)

CPP_CMAKE = '''
cmake_minimum_required(VERSION 3.20)
project(gdal_consumer CXX)
find_package(GDAL REQUIRED CONFIG)
add_executable(consumer main.cpp)
target_link_libraries(consumer PRIVATE GDAL::GDAL)
'''

CPP_MAIN = r'''
#include "gdal_priv.h"
#include <cstdio>
int main(int argc, char** argv) {
    GDALAllRegister();
    const char* path = argc > 1 ? argv[1] : "out.tif";
    GDALDriver* drv = GetGDALDriverManager()->GetDriverByName("GTiff");
    if (!drv) { fprintf(stderr, "GTiff missing\n"); return 1; }
    GDALDataset* ds = drv->Create(path, 16, 16, 1, GDT_Byte, nullptr);
    if (!ds) { fprintf(stderr, "create failed\n"); return 2; }
    double gt[6] = {440720.0, 60.0, 0.0, 3751320.0, 0.0, -60.0};
    if (ds->SetGeoTransform(gt) != CE_None) return 3;
    unsigned char buf[256];
    for (int i = 0; i < 256; i++) buf[i] = (unsigned char)((i * 7) % 251);
    if (ds->GetRasterBand(1)->RasterIO(GF_Write, 0, 0, 16, 16, buf, 16, 16,
                                       GDT_Byte, 0, 0, nullptr) != CE_None) return 4;
    GDALClose(ds);
    GDALDataset* rd = (GDALDataset*)GDALOpen(path, GA_ReadOnly);
    if (!rd) { fprintf(stderr, "reopen failed\n"); return 5; }
    GDALRasterBand* band = rd->GetRasterBand(1);
    unsigned char out[256];
    if (band->RasterIO(GF_Read, 0, 0, 16, 16, out, 16, 16,
                       GDT_Byte, 0, 0, nullptr) != CE_None) return 6;
    for (int i = 0; i < 256; i++) if (out[i] != buf[i]) return 7;
    double gt2[6];
    if (rd->GetGeoTransform(gt2) != CE_None) return 8;
    if (gt2[0] != gt[0] || gt2[1] != gt[1]) return 9;
    printf("CPP_CONSUMER_OK dims=%dx%d gt=%.1f,%.1f\n", rd->GetRasterXSize(),
           rd->GetRasterYSize(), gt2[0], gt2[1]);
    band = nullptr;
    GDALClose(rd);
    return 0;
}
'''

# Lifetime discipline: every object whose methods are used must be kept in a
# named Python variable for the whole duration of the Layer/Feature/Geometry
# operations (OGR layers are owned by their datasource; a temporary datasource
# is collected mid-expression and then GetFeatureCount raises TypeError).
PY_CONSUMER = r'''
import os
import numpy as np
from osgeo import gdal, ogr, osr

gdal.UseExceptions()
base = os.path.dirname(os.path.abspath(__file__))

# ---- raster round-trip ---------------------------------------------------
tif = os.path.join(base, 'out2.tif')
ds = gdal.GetDriverByName('GTiff').Create(tif, 8, 8, 1, gdal.GDT_Int16)
srs = osr.SpatialReference()
srs.ImportFromEPSG(4326)
ds.SetProjection(srs.ExportToWkt())
ds.SetGeoTransform([1.0, 0.1, 0.0, 2.0, 0.0, -0.1])
arr = np.arange(64, dtype=np.int16).reshape(8, 8)
ds.GetRasterBand(1).WriteArray(arr)
ds = None

ds = gdal.Open(tif)
assert ds.RasterXSize == 8 and ds.RasterYSize == 8, 'dims'
assert abs(ds.GetGeoTransform()[1] - 0.1) < 1e-12, 'geotransform'
band = ds.GetRasterBand(1)
back = band.ReadAsArray()
assert int(back.sum()) == int(arr.sum()), 'checksum'
proj = ds.GetProjection()
assert osr.SpatialReference(wkt=proj).GetAuthorityCode(None) == '4326'
band = None
ds = None

# ---- vector round-trip (Shapefile) --------------------------------------
shp = os.path.join(base, 'points.shp')
drv = ogr.GetDriverByName('ESRI Shapefile')
vds = drv.CreateDataSource(shp)
lyr = vds.CreateLayer('points', srs, ogr.wkbPoint)
lyr.CreateField(ogr.FieldDefn('id', ogr.OFTInteger))
ldefn = lyr.GetLayerDefn()
for i in range(5):
    f = ogr.Feature(ldefn)
    f.SetField('id', i)
    g = ogr.Geometry(ogr.wkbPoint)
    g.AddPoint_2D(float(i), float(i * 2))
    f.SetGeometry(g)
    lyr.CreateFeature(f)
    f = None
    g = None
lyr = None
vds = None

src = ogr.Open(shp)
shp_lyr = src.GetLayer(0)
shp_count = shp_lyr.GetFeatureCount()
assert shp_count == 5, 'shapefile'
shp_lyr = None
src = None

# ---- GeoPackage translation (datasource held for full lifetime) ---------
gpkg = os.path.join(base, 'points.gpkg')
translated = gdal.VectorTranslate(gpkg, shp, format='GPKG')
translated = None
gpkg_ds = ogr.Open(gpkg)
gpkg_lyr = gpkg_ds.GetLayer(0)
gpkg_count = gpkg_lyr.GetFeatureCount()
assert gpkg_count == 5, 'gpkg'
gpkg_lyr = None
gpkg_ds = None

print('PY_CONSUMER_OK raster_sum=%d vector=%d gpkg=%d gdal=%s'
      % (int(arr.sum()), shp_count, gpkg_count, gdal.VersionInfo()))
'''


def _run_quiet(argv):
    return subprocess.run(argv, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode == 0


def _pkgconfig(name):
    if shutil.which('pkg-config') is None:
        return False
    return _run_quiet(['pkg-config', '--exists', name])


def python_include_dir(py=None):
    """Return the directory actually containing Python.h, or None.

    Probes sysconfig (INCLUDEPY / include / platinclude), pkg-config /
    python3-config --includes, a glob of /usr/include/python3.* and the explicit
    Ubuntu path.  Build-tool venvs are not required to ship headers; the real
    system headers under /usr/include are accepted."""
    py = py or sys.executable
    proc = subprocess.run([py, '-c', HEADER_PROBE], capture_output=True, text=True)
    return proc.stdout.strip() or None


def _norm(name):
    """PEP 503 normalisation: lowercase, runs of -, _ and . become single -."""
    return re.sub(r'[-_.]+', '-', name.strip().lower())


def _wheelhouse_index():
    """Map normalized distribution name -> list of wheel filenames."""
    index = {}
    if not WHEELHOUSE.is_dir():
        return index
    for whl in WHEELHOUSE.glob('*.whl'):
        # Wheel filename: {dist}-{version}(-{build})?-{python}-{abi}-{plat}.whl
        parts = whl.stem.split('-')
        if len(parts) < 5:
            continue
        index.setdefault(_norm(parts[0]), []).append(whl.name)
    return index


def wheel_missing(dists):
    """Return declared distribution names that have no wheel in the wheelhouse.

    Matching is normalised per PEP 503 / the wheel spec, so a genuine
    `python_dotenv-*.whl` (distribution `python-dotenv`) is recognised."""
    index = _wheelhouse_index()
    return ['wheelhouse wheel: %s' % d for d in dists if _norm(d) not in index]


def check_missing(input_dir):
    """Exact list of missing source/tool/dependency items (empty == ready)."""
    missing = []
    inp = Path(input_dir)
    man = inp / 'manifest.json'
    if not man.is_file():
        return ['source manifest: %s' % man]
    try:
        meta = json.loads(man.read_text())
        arch = inp / meta['source']['filename']
        if not arch.is_file():
            missing.append('source archive: %s' % arch)
        elif buildkit.digest(arch) != meta['source']['sha256']:
            missing.append('source archive checksum mismatch: %s' % arch)
    except Exception as exc:  # noqa: BLE001
        missing.append('unreadable source manifest %s: %s' % (man, exc))
    for tool in ('cmake', 'ninja', 'gcc', 'g++', 'swig', 'python3', 'pkg-config'):
        if shutil.which(tool) is None:
            missing.append('tool: %s' % tool)
    for pkg in ('proj', 'sqlite3'):
        if not _pkgconfig(pkg):
            missing.append('dependency: pkg-config %s' % pkg)
    if not Path('/usr/share/proj/proj.db').is_file():
        missing.append('dependency data: /usr/share/proj/proj.db')
    py = shutil.which('python3') or sys.executable
    if python_include_dir(py) is None:
        missing.append('python development headers: Python.h not found via '+
                       'sysconfig/pkg-config/python3-config/usr-include')
    if not WHEELHOUSE.is_dir():
        missing.append('dependency wheelhouse: %s' % WHEELHOUSE)
    else:
        missing.extend(wheel_missing(REQUIRED_DISTS))
    return missing


def py_site(root):
    hits = sorted(Path(root).glob('lib/python*/site-packages'))
    return hits[0] if hits else None


def build_env(session, extra_paths=()):
    paths = [str(p) for p in extra_paths if p and Path(p).exists()]
    for cand in (py_site(session.install), session.build / 'swig' / 'python',
                 session.src / 'autotest' / 'pymod'):
        if cand and Path(cand).exists():
            paths.append(str(cand))
    env = {
        'PYTHONPATH': os.pathsep.join(paths),
        'PATH': str(session.install / 'bin') + os.pathsep + os.environ.get('PATH', ''),
        'LD_LIBRARY_PATH': str(session.install / 'lib'),
        'GDAL_DATA': str(session.install / 'share' / 'gdal'),
        'GDAL_DOWNLOAD_TEST_DATA': 'NO',
        'GDAL_RUN_SLOW_TESTS': 'NO',
        'PIP_DISABLE_PIP_VERSION_CHECK': '1',
        'PIP_NO_INPUT': '1',
    }
    proj = session.install / 'share' / 'proj'
    env['PROJ_DATA'] = str(proj) if proj.exists() else '/usr/share/proj'
    return env


def cmd_doctor(args):
    missing = check_missing(args.input)
    print(json.dumps({'ready': not missing, 'input': str(Path(args.input).resolve()),
                      'python_include_dir': python_include_dir(),
                      'missing': missing}, indent=2))
    return 0 if not missing else 78


def make_venv(session, env):
    """Create the isolated build/consumer venv and its offline dependencies."""
    venv = session.consumer / 'venv'
    vpy = venv / 'bin' / 'python'
    if not vpy.exists():
        session.run([sys.executable, '-m', 'venv', str(venv)],
                    phase='prereq', name='venv_create', env=env)
    session.run([str(vpy), '-m', 'pip', 'install', '--no-index', '--find-links',
                 str(WHEELHOUSE)] + REQUIRED_DISTS,
                phase='prereq', name='venv_deps', env=env, timeout=1800)
    for mod in ('numpy', 'pytest', 'pytest_env', 'filelock', 'xdist', 'dotenv'):
        session.run([str(vpy), '-c', 'import %s' % mod],
                    phase='prereq', name='venv_check_' + mod, env=env)
    session.write('prereq.json', {
        'venv': str(venv),
        'required_dists': REQUIRED_DISTS,
        'pytest_env_plugin': True,
    })
    return venv, vpy


def configure(session, vpy, env):
    inc = python_include_dir(vpy) or python_include_dir()
    argv = [
        'cmake', '-S', str(session.src), '-B', str(session.build), '-G', 'Ninja',
        '-DCMAKE_INSTALL_PREFIX=%s' % session.install,
        '-DCMAKE_BUILD_TYPE=Release',
        '-DCMAKE_C_FLAGS=-O2', '-DCMAKE_CXX_FLAGS=-O2',
        '-DBUILD_TESTING=ON',
        '-DBUILD_PYTHON_BINDINGS=ON',
        '-DPython3_EXECUTABLE=%s' % vpy,
        '-DPython_EXECUTABLE=%s' % vpy,
        '-DGDAL_BUILD_OPTIONAL_DRIVERS=OFF',
        '-DOGR_BUILD_OPTIONAL_DRIVERS=OFF',
        '-DOGR_ENABLE_DRIVER_SQLITE=ON',
        '-DOGR_ENABLE_DRIVER_GPKG=ON',
        '-DGDAL_DOWNLOAD_TEST_DATA=OFF',
        '-DGDAL_SLOW_TESTS=OFF',
    ]
    if inc:
        argv.append('-DPython3_INCLUDE_DIR=%s' % inc)
        argv.append('-DPython_INCLUDE_DIR=%s' % inc)
    session.run(argv, cwd=session.build, phase='configure',
                name='cmake_configure', env=env, timeout=3600)


def run_tests(session, env, vpy):
    skw = dict(cwd=session.build, env=env, timeout=7200)
    for name, selector in (('ctest-test-unit', '^test-unit$'),
                           ('ctest-autotest-alg', '^autotest_alg$'),
                           ('ctest-autotest-osr', '^autotest_osr$')):
        session.test(name, ['ctest', '--test-dir', str(session.build), '-R', selector,
                            '--output-on-failure', '--parallel', str(TEST_JOBS)], **skw)
    # Full upstream VRT read module is executed, not a subset of cases.
    argv = [str(vpy), '-m', 'pytest', 'gcore/vrt_read.py', '-v', '-p', 'no:cacheprovider']
    session.test('pytest-vrt-read', argv, cwd=session.src / 'autotest',
                 env=env, timeout=3600)


def run_consumer(session, vpy, env):
    c = session.consumer
    for sub in ('cpp', 'py', 'wheels'):
        (c / sub).mkdir(parents=True, exist_ok=True)
    (c / 'cpp' / 'CMakeLists.txt').write_text(CPP_CMAKE)
    (c / 'cpp' / 'main.cpp').write_text(CPP_MAIN)
    (c / 'py' / 'consumer.py').write_text(PY_CONSUMER)
    cenv = dict(env)
    cenv['LD_LIBRARY_PATH'] = str(session.install / 'lib')

    session.run(['cmake', '-S', str(c / 'cpp'), '-B', str(c / 'cpp' / 'build'),
                 '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
                 '-DGDAL_DIR=%s' % (session.install / 'lib' / 'cmake' / 'gdal'),
                 '-DCMAKE_PREFIX_PATH=%s' % session.install],
                phase='consumer', name='cpp_configure', env=cenv)
    session.run(['cmake', '--build', str(c / 'cpp' / 'build'), '--parallel', str(TEST_JOBS)],
                phase='consumer', name='cpp_build', env=cenv)
    session.run([str(c / 'cpp' / 'build' / 'consumer'), str(c / 'cpp' / 'out.tif')],
                phase='consumer', name='cpp_run', env=cenv)

    venv_site = py_site(c / 'venv')
    pyenv = dict(cenv)
    # PYTHONPATH is intentionally restricted to the consumer venv for the
    # Python checks so no build-tree or system copy of osgeo can be imported.
    pyenv['PYTHONPATH'] = str(venv_site) if venv_site else ''
    wheel_env = dict(pyenv, GDAL_CONFIG=str(session.install / 'bin' / 'gdal-config'))
    session.run([str(vpy), '-m', 'pip', 'wheel', '--no-deps', '--no-build-isolation',
                 '--no-index', '--find-links', str(WHEELHOUSE),
                 '-w', str(c / 'wheels'), str(session.src / 'python')],
                phase='consumer', name='py_wheel', env=wheel_env,
                timeout=3600, check=False)
    wheels = sorted((c / 'wheels').glob('*.whl'))
    if wheels:
        session.run([str(vpy), '-m', 'pip', 'install', '--no-index',
                     '--find-links', str(c / 'wheels'), '--find-links', str(WHEELHOUSE),
                     '--force-reinstall', '--no-deps', wheels[-1].name],
                    phase='consumer', name='venv_install_wheel', env=pyenv)
        channel = 'source-wheel:%s' % wheels[-1].name
    else:
        site = py_site(session.install)
        if not site or not venv_site:
            raise RuntimeError('no installed Python bindings and no source-built wheel')
        (venv_site / 'gdal_cmake_install.pth').write_text(str(site) + '\n')
        channel = 'cmake-install-pth'
    session.run([str(vpy), '-c', 'import osgeo, sys; print(osgeo.__file__)'],
                phase='consumer', name='py_import_check', env=pyenv)
    session.run([str(vpy), str(c / 'py' / 'consumer.py')],
                phase='consumer', name='py_run', env=pyenv)
    return {'python_binding_channel': channel}


def cmd_run(args):
    missing = check_missing(args.input)
    if missing:
        print(json.dumps({'ready': False, 'missing': missing}, indent=2))
        return 78
    session = Session(args.input, args.output, args.jobs)
    session.prepare()
    env = build_env(session)
    venv, vpy = make_venv(session, env)
    env = build_env(session)
    configure(session, vpy, env)
    session.run(['cmake', '--build', str(session.build), '--parallel', str(session.jobs)],
                cwd=session.build, phase='build', name='cmake_build', env=env, timeout=10800)
    session.run(['cmake', '--build', str(session.build), '--target', 'install'],
                cwd=session.build, phase='install', name='cmake_install', env=env, timeout=3600)
    env = build_env(session)
    run_tests(session, env, vpy)
    consumer = run_consumer(session, vpy, env)
    session.finish(features={
        'profile': 'core',
        'drivers': ['GTiff', 'COG', 'VRT', 'MEM', 'GeoJSON', 'ESRI Shapefile', 'SQLite',
                    'GPKG'],
        'selectors': ['test-unit', 'autotest_alg', 'autotest_osr',
                      'autotest/gcore/vrt_read.py'],
        'build_jobs': session.jobs,
        'test_jobs': TEST_JOBS,
        'consumer': consumer,
    })
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='main.py',
        description='BUILDv1-C09: source-build the GDAL core raster/vector distribution.')
    sub = parser.add_subparsers(dest='command')
    for name in ('run', 'doctor'):
        p = sub.add_parser(name)
        p.add_argument('--input', default=str(WS / 'input'))
        p.add_argument('--output', default=str(WS / 'output'))
        if name == 'run':
            p.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args(argv)
    if args.command == 'doctor':
        return cmd_doctor(args)
    if args.command == 'run':
        args.jobs = max(1, min(int(args.jobs), 4))
        return cmd_run(args)
    parser.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
