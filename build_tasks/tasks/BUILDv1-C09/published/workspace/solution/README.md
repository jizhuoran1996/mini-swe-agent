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
  the tools, the PROJ/SQLite development dependencies plus
  `/usr/share/proj/proj.db`, Python development headers, and the
  `/opt/wheelhouse` wheelhouse with every required wheel. It prints the **exact**
  missing items and the resolved `python_include_dir`, exits `78` if any are
  missing and `0` when ready.
* `run` re-runs that check, extracts the checksum-verified archive, creates the
  build/consumer venv from the offline wheelhouse, configures with the frozen
  core driver set, builds with `BUILD_JOBS<=4`, installs, tests and verifies.

## Fixes applied to this revision

1. **Wheel-name normalisation.** Wheel filenames normalise both `-` and `.` to
   `_`, so the distribution `python-dotenv` ships as `python_dotenv-*.whl`.
   Wheelhouse matching parses each `*.whl` filename, takes its distribution
   component and applies `re.sub(r'[-_.]+', '-', name.lower())` before
   comparison. Genuine `python_dotenv`, `filelock`, `pytest-env`, `pytest-xdist`
   and `execnet` wheels now match.
2. **Python.h discovery.** The header probe imports `sys` explicitly, so a
   `sys.exit` NameError can no longer masquerade as a missing header. It probes
   `sysconfig.get_config_var('INCLUDEPY')`, `sysconfig.get_paths()['include']`
   and `['platinclude']`, `pkg-config --variable=includedir python-3.12`,
   `python3-config --includes`, `glob('/usr/include/python3.*')` and the
   explicit `/usr/include/python3.12` path, and returns the first directory that
   actually contains `Python.h`. Build-tool venv prefixes are **not** required
   to ship headers — the real Ubuntu `python3.12-dev` headers under
   `/usr/include/python3.12` are accepted. The resolved directory is passed to
   CMake as `Python3_INCLUDE_DIR` and `Python_INCLUDE_DIR` while
   `Python3_EXECUTABLE` points at the build venv.
3. **OGR/GDAL object-lifetime bug (this trial).** The Python consumer previously
   used the chained expression
   `ogr.Open(gpkg).GetLayer(0).GetFeatureCount()`. OGR layers are owned by their
   datasource, so the temporary datasource was garbage-collected before
   `GetFeatureCount()` ran and the call raised
   `TypeError: in method 'Layer_GetFeatureCount', argument 1 of type
   'OGRLayerShadow *'`. Every datasource is now held in a named variable for
   the full duration of the Layer/Feature/Geometry operations and released in
   correct order (`layer` first, then `datasource`). The C++ consumer holds its
   raster band in a named pointer before use and clears it before
   `GDALClose`. The expected feature counts (5 Shapefile / 5 GeoPackage) and the
   GeoPackage payload are unchanged.

## Required wheelhouse content

    numpy, pytest, pytest-xdist, pytest-env, setuptools, wheel,
    packaging, filelock, python-dotenv, execnet

If any is genuinely absent, `doctor` reports the exact missing wheel and exits
`78`; the driver refuses to start a build instead of silently turning the
official selections into a `ModuleNotFoundError`.

## Scope / frozen core profile

* Drivers exercised: GTiff, COG, VRT, MEM, GeoJSON, ESRI Shapefile, SQLite, GPKG.
* Official selectors with `TEST_JOBS=2`: `ctest -R '^test-unit$'`,
  `^autotest_alg$`, `^autotest_osr$`, and the full upstream module
  `pytest autotest/gcore/vrt_read.py` (no subset, no skip).
* `GDAL_DOWNLOAD_TEST_DATA=NO` and `GDAL_RUN_SLOW_TESTS=NO` are exported
  explicitly; the environment is frozen, not inherited, and no network is used.

## Independent consumption

* The C++ consumer under `/workspace/consumer/cpp` compiles against the
  installed `GDAL::GDAL` CMake package, writes a GeoTIFF, reopens it and checks
  the pixel payload and geotransform.
* The Python consumer runs in a dedicated `venv` created with **no system site
  packages**. The fresh bindings are exposed via a wheel built from
  `source/python` (`python_binding_channel=source-wheel:<name>`) or, if that
  optional wheel build fails, via an explicit `.pth` pointing at the
  cmake-installed site-packages. `PYTHONPATH` is restricted to the venv for
  these runs. Assertions cover geotransform, pixel checksum, EPSG 4326 authority
  code, Shapefile feature count and GeoPackage round-trip.

## Honest limitations

* Any missing source/tool/dependency/wheelhouse item is reported by `doctor`
  with exit `78`; no system libgdal / python-gdal substitution is used.
* Optional drivers (netCDF/HDF5/OpenJPEG/…) are intentionally **off** in this
  core profile.
* The Python wheel build depends on upstream packaging of this release; the
  outcome is recorded in the logs and never masked by dropping a selector or
  turning a failing test into a skip.
* No resource figures are claimed; they are measured only by the host run.
