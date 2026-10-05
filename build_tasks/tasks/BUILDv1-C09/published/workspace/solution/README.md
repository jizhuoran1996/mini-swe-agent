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
  headers (`Python.h`), NumPy, the `/opt/wheelhouse` wheelhouse and each
  required wheel (numpy, pytest, pytest-xdist, setuptools, wheel, packaging).
  It prints the **exact** missing items, exits `78` if any are missing and `0`
  when ready.
* `run` re-runs that check, extracts the checksum-verified archive, creates the
  build/consumer venv from the offline wheelhouse, configures with the frozen
  core driver set (`GDAL_BUILD_OPTIONAL_DRIVERS=OFF`,
  `OGR_BUILD_OPTIONAL_DRIVERS=OFF`, SQLite and GeoPackage explicitly enabled),
  builds with `BUILD_JOBS<=4`, installs, tests and verifies.

## Scope / frozen core profile

* Drivers exercised: GTiff, COG, VRT, MEM, GeoJSON, ESRI Shapefile, SQLite, GPKG.
* Official selectors executed with `TEST_JOBS=2`: `ctest -R '^test-unit$'`,
  `^autotest_alg$`, `^autotest_osr$`, and
  `pytest autotest/gcore/vrt_read.py`.
* `GDAL_DOWNLOAD_TEST_DATA=NO` and `GDAL_RUN_SLOW_TESTS=NO` are frozen in the run
  environment (they are exported explicitly, not inherited); no network is used.

## Dependency handling

The consumer/build venv installs only from `/opt/wheelhouse` with `--no-index`.
`numpy`, `pytest`, `pytest-xdist`, `setuptools`, `wheel` and `packaging` are hard
requirements and reported by `doctor` when absent. `pytest-env` is installed
when its wheel is present (upstream GDAL's `pytest.ini` declares an `env =`
section that this plugin provides). If that wheel is genuinely absent, the driver
records the fact, runs the direct pytest selection against a copy of the upstream
`pytest.ini` with only the plugin-provided `env` section removed, and continues —
the same variables are exported explicitly, so no upstream test data,
expectation, selector or skip policy is changed. Nothing is downloaded, mocked
or substituted.

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
