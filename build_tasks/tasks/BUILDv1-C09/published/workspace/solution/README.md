# BUILDv1-C09 — source-built GDAL core raster/vector distribution

## What this driver does

`solution/main.py` performs a **clean, offline source build** of GDAL v3.10.3
(`ed29baf16d20bccbe331d809e0bafd7afde03360`) from the archive mounted at
`/workspace/input/source.tar.gz`, installs the SDK/CLI/Python bindings, runs the
frozen core official test selections, and then consumes the *newly built*
artifacts from outside the source tree.

Every configure/build/install/test/consumer command goes through the trusted
`buildkit.Session` helper, so exit codes and full logs are preserved under
`output/logs/` and summarised in `output/commands.json`, `output/tests.json`,
`output/install_manifest.json`, `output/install.tar.gz`, `output/prereq.json`
and `output/run.json`.

## Commands

```
python3 solution/main.py --help
python3 solution/main.py doctor --input input
python3 solution/main.py run --input input --output output --jobs 4
```

* `--help` never touches the source tree or runs a build.
* `doctor` checks — before any long build — the source archive and its SHA-256,
  the tools (cmake, ninja, gcc/g++, swig, python3, pkg-config), the PROJ/SQLite
  development dependencies plus `/usr/share/proj/proj.db`, Python development
  headers, and the `/opt/wheelhouse` wheelhouse with every required wheel.
  It prints the **exact** missing items and the resolved `python_include_dir`,
  exits `78` if any are missing and `0` when ready.
* `run` re-runs that check, extracts the checksum-verified archive, creates the
  build/consumer venv from the offline wheelhouse, configures with the frozen
  core driver set (`GDAL_BUILD_OPTIONAL_DRIVERS=OFF`,
  `OGR_BUILD_OPTIONAL_DRIVERS=OFF`, SQLite and GeoPackage explicitly enabled),
  builds with `BUILD_JOBS<=4`, installs, tests and verifies.

## Required wheelhouse content

Upstream GDAL's `autotest/conftest.py` imports `filelock` (to lock the PROJ
search-path mutation across parallel pytest workers), its `pytest.ini` declares
an `env =` section (provided by `pytest-env`, which in turn needs
`python-dotenv`), and running pytest with `-n` uses `pytest-xdist` / `execnet`.
The following wheels are therefore **hard requirements** and are checked by
`doctor` before the long build begins:

    numpy, pytest, pytest-xdist, pytest-env, setuptools, wheel,
    packaging, filelock, python-dotenv, execnet

If any of these is genuinely absent, `doctor` reports the exact missing wheel
and exits `78`; the driver then refuses to start a build rather than silently
turning the official ctest selections into a `ModuleNotFoundError` failure.

## Scope / frozen core profile

* Drivers exercised: GTiff, COG, VRT, MEM, GeoJSON, ESRI Shapefile, SQLite, GPKG.
* Official selectors executed with `TEST_JOBS=2`: `ctest -R '^test-unit$'`,
  `^autotest_alg$`, `^autotest_osr$`, and
  `pytest autotest/gcore/vrt_read.py`.
* `GDAL_DOWNLOAD_TEST_DATA=NO` and `GDAL_RUN_SLOW_TESTS=NO` are frozen in the run
  environment (they are exported explicitly, not inherited); no network is used.

## Python header discovery (fixed)

The earlier header probe called `sys.exit(...)` without importing `sys`, raising
`NameError` that was silently dropped by `subprocess` and misreported as a
missing `Python.h`. The probe now imports `sys` explicitly and locates the
actual file `Python.h` across:

1. `sysconfig.get_config_var('INCLUDEPY')`
2. `sysconfig.get_paths()['include']` and `['platinclude']`
3. `pkg-config --variable=includedir python-3.12` output (`-I` flags honoured)
4. `python3-config --includes` output (`-I` flags honoured)
5. `glob('/usr/include/python3.*')`
6. explicit `/usr/include/python3.12`, `/usr/include`

The first candidate whose directory actually contains `Python.h` is used. The
build-tool venv `/opt/build-tools` is **not** required to ship headers; the
real Ubuntu `python3.12-dev` headers under `/usr/include/python3.12` are
accepted. Because the header check is real and never skipped, a genuinely
missing `Python.h` still fails honestly. The resolved directory is passed to
CMake as both `Python3_INCLUDE_DIR` and `Python_INCLUDE_DIR`, while
`Python3_EXECUTABLE` / `Python_EXECUTABLE` point at the build venv's Python so
the autotest suite runs against the freshly built bindings.

## Independent consumption

* A C++ consumer under `/workspace/consumer/cpp` is compiled against the
  installed `GDAL::GDAL` CMake package, writes a GeoTIFF, reopens it and checks
  the pixel payload and geotransform.
* A Python consumer runs inside a dedicated `venv` created with **no system site
  packages**. The freshly built bindings are exposed either through a wheel built
  from `source/python` (`python_binding_channel=source-wheel:<name>`) or, if that
  optional wheel build fails, through an explicit `.pth` pointing at the
  cmake-installed `site-packages` (`cmake-install-pth`). `PYTHONPATH` is set to
  the venv alone for these runs, so no build-tree or system copy of `osgeo` can
  be used. The consumer asserts geotransform, pixel checksum, EPSG authority
  code, Shapefile feature count and a GeoPackage round-trip.

## Honest limitations

* If any checked source/tool/dependency/wheelhouse item is absent, `doctor`
  reports it and exits `78` instead of faking a build or falling back to a
  system libgdal/python-gdal.
* Optional drivers (netCDF/HDF5/OpenJPEG/…) are intentionally **off** in this
  core profile; only the core raster/vector drivers listed above are guaranteed.
* The GDAL Python wheel build depends on the upstream packaging of this release;
  the real outcome is recorded in the logs and never masked by dropping a
  selector or turning a failing test into a skip.
* No resource figures are claimed; they are measured only by the host run.
