# BUILDv1-F08 - XGBoost CPU core and Python wheel

Builds the XGBoost v3.0.2 CPU native core (`libxgboost.so`), the official
C++ GoogleTest binary (`testxgboost`), packages the repo's Python binding
into a fresh CPU-only wheel that embeds the byte-identical library produced
in this run, installs that wheel with real dependency resolution into an
isolated consumer virtualenv, and independently consumes it from outside the
source tree.

## Commands

```
python3 solution/main.py doctor --input input
python3 solution/main.py run --input input --output output --jobs 4
```

* `doctor` verifies the frozen manifest, source archive checksum, the native
  toolchain (`cmake`, `ninja`, `cc`, `c++`, `python3`) and that the offline
  wheelhouse holds every genuine test/runtime dependency (numpy, scipy,
  pandas, scikit-learn, hypothesis, pytest). It prints exact missing items and
  exits `78` when anything is absent, `0` when ready.
* `run` performs the full chain: `cmake` configure (CPU only, OpenMP on,
  GOOGLE_TEST on, all CUDA/NCCL/federated/JVM/R plugins off) -> Ninja build ->
  `cmake --install` -> `ctest -R ^TestXGBoostLib$` (the full unmodified native
  suite) -> run the upstream `ops/script/pypi_variants.py` generator with
  `--use-cpu-suffix=0 --require-nccl-dep=0` to emit a supported CPU-only
  `python-package/pyproject.toml` -> build the wheel with `python -m build
  --wheel --no-isolation` -> create the consumer venv (no system site
  packages) -> `pip install --no-index` the wheel *with* dependency
  resolution, then the genuine test dependencies -> run the train/save/reload
  consumers -> run the official `tests/python/test_basic.py` with pytest.

### CPU-only metadata via the official generator

The shipped `python-package/pyproject.toml` declares the CUDA NCCL wheel as a
hard dependency. The recipe invokes the real upstream generator
`ops/script/pypi_variants.py` (the same tool the project uses for its PyPI
variants) with `--use-cpu-suffix=0 --require-nccl-dep=0`. This keeps the
package name `xgboost` and produces a legitimate CPU-only metadata set whose
only runtime requirements are `numpy`/`scipy`. No metadata, test, or source
file is patched by hand.

## Evidence produced under `output/`

* `logs/NNN_*.log` - verbatim stdout/stderr and exit codes of every phase.
* `commands.json` - executable, cwd, phase, wall time, log sha256 per command.
* `tests.json` - recorded official selectors with parsed case counts.
* `packaging.json` - native library path + sha256, wheel name + sha256, the
  embedded `libxgboost.so` sha256, the hash-match assertion, the parsed
  METADATA `Requires-Dist` entries and `nccl_hard_required: false`.
* `install_manifest.json`, `install.tar.gz` - the `cmake --install` tree.
* `run.json` - summary with the selector list and feature flags.

All subprocesses are launched through `buildkit.Session` with explicit
argument lists; build parallelism is clamped to `<=4` and OpenMP runtime
threads to `<=2`.

## Honest limitations

* The `native_library_packaging_route` is fixed to the reuse path: the CMake
  build writes `lib/libxgboost.so` and the wheel backend packages that same
  file; the recipe asserts the wheel-embedded copy has the identical sha256
  and fails otherwise. No system-wide `libxgboost` is ever consumed.
* The consumer venv installs the wheel with real dependency resolution from
  `/opt/wheelhouse` only, mirroring an external consumer. The recipe fails
  loudly if the wheel still advertises a hard NCCL dependency or if any
  genuine runtime/test wheel is missing; it never falls back to the network.
* `tests/python/test_basic.py` is executed unchanged. An all-skipped or empty
  pytest run (exit code 5) stops the pipeline rather than being reported as
  success.
* Only the CPU core scope is exercised; CUDA, NCCL, federated and JVM/R
  bindings are explicitly disabled and not validated by this recipe.
