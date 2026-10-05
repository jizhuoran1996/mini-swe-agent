# BUILDv1-F08 - XGBoost CPU core and Python wheel

Builds the XGBoost v3.0.2 CPU native core (`libxgboost.so`), the official
C++ GoogleTest binary (`testxgboost`), packages the repo's Python binding
into a fresh wheel embedng the library produced in this run, installs that
wheel into an isolated consumer virtualenv, and independently consumes it
from outside the source tree.

## Commands

```
python3 solution/main.py doctor --input input
python3 solution/main.py run --input input --output output --jobs 4
```

* `doctor` verifies the frozen manifest, source archive checksum, the native
toolchain (`cmake`, `ninja`, `cc`, `c++`, `python3`) and the offline
wheelhouse; it prints the exact missing items and exits `78` when anything is
absent, `0` when the environment is ready.
* `run` performs the full chain: `cmake` configure (CPU only, OpenMP on,
  GOOGLE_TEST on, all CUDA/NCCL/federated/JVM/R plugins off) -> Ninja build ->
  `cmake --install` -> `ctest -R ^TestXGBoostLib$` -> build the wheel with
  `python -m build --wheel --no-isolation` -> create the consumer venv (no
  system site packages) -> `pip install --no-index` the wheel plus the
  wheelhouse runtime deps -> train/save/reload a small model with the new
  library -> run the official `tests/python/test_basic.py` with pytest.

## Evidence produced under `output/`

* `logs/NNN_*.log` - verbatim stdout/stderr and exit codes of every phase.
* `commands.json` - executable, cwd, phase, wall time, log sha256 per command.
* `tests.json` - recorded official selectors with parsed case counts.
* `packaging.json` - native library path + sha256, wheel name + sha256, and
  the assertion that the wheel embeds `libxgboost.so`.
* `install_manifest.json`, `install.tar.gz` - the `cmake --install` tree.
* `run.json` - summary with the selector list and feature flags.

All subprocesses are launched through `buildkit.Session` with explicit
argument lists; build parallelism is clamped to `<=4` and OpenMP runtime
threads to `<=2`.

## Honest limitations

* The `native_library_packaging_route` is fixed to the reuse path: the CMake
  build writes `lib/libxgboost.so` and the wheel backend packages that file.
  If the wheel backend were to recompile, the extra native build would be
  recorded in `logs/` but the wheel's own hash still identifies the shipped
  artifact; no system-wide `libxgboost` is ever consumed.
* The consumer venv installs from `/opt/wheelhouse` only. If required runtime
  or build-backend wheels are absent there, the corresponding phase fails
  loudly instead of falling back to the network.
* Only the CPU core scope is exercised; CUDA, NCCL, federated and JVM/R
  bindings are explicitly disabled and not validated by this recipe.
