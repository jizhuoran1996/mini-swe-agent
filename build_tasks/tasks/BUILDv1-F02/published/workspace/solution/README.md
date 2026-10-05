# BUILDv1-F02 - TensorFlow v2.18.0 CPU wheel from source

Builds the complete TensorFlow CPU Python wheel from the frozen commit
`6550e4bd80223cdb8be6c3afd1f81e86a4d433c3` (release ref `v2.18.0`), runs the two
frozen official tests, then installs the newly built wheel into a fresh consumer
venv outside the source tree and verifies SavedModel save/reload semantics.

## Frozen CPU build facts baked into this solution

- **Bazel**: `.bazelversion` is parsed as the first non-empty, non-comment line
(TensorFlow 2.18.0 pins `6.5.0`); the binary is taken from
`/opt/bazel/<version>/bazel`. `/opt/bazel/6.5.0` is prepended to `PATH` for
`bash ./configure` so upstream `configure.py`'s Bazel version probe sees it.
- **Configure**: invoked as `bash ./configure`. The upstream wrapper is a bash
script, not a Python file; it execs `configure.py` using `$PYTHON_BIN_PATH`. CPU
answers are supplied through the environment (`PYTHON_BIN_PATH`, `TF_NEED_CUDA=0`,
`TF_NEED_ROCM=0`, TensorRT/SYCL/MPI off, `TF_NEED_CLANG=1`) so no interactive
prompt is issued. The resulting `.tf_configure.bazelrc` is checked for existence
before the build is allowed to start.
- **Bazel caches** (design-declared): repository cache
`/workspace/cache/bazel_repository`, explicit startup
`--output_base=/workspace/cache/bazel_output`, both passed on the command line.
`HOME` for the Bazel server is redirected to `/workspace/build/home` so no
global HOME change is required and the server never tries to write under `/`.
- **CPU config**: `TF_NEED_CUDA=0`, `TF_NEED_ROCM=0`, clang-18 / CPython 3.12
answers; `CC`/`CXX` point at `clang-18`/`clang++-18` when the runtime provides
them, otherwise the build uses the system default compiler.
- **Build**: `bazel --output_base=... build --repository_cache=... --jobs=4
--local_ram_resources=24000 --repo_env=USE_PYWRAP_RULES=1
--repo_env=WHEEL_NAME=tensorflow_cpu --config=opt
//tensorflow/tools/pip_package:wheel` - the full `tensorflow_cpu` wheel, no
shrinking of the model/core targets.
- **Tests**: `--config=linux --local_test_jobs=2 --cache_test_results=no` on the
frozen official selections `//tensorflow/python/kernel_tests/nn_ops:softmax_op_test`
and `//tensorflow/python/saved_model:load_test` with
`--test_filter=*LoadTest.test_capture_variables*`.
- **Install / consumer**: the new wheel is copied to `--output`, unpacked into
`/workspace/output/install`, and installed into a fresh
`/workspace/consumer/venv` (no system site packages). Runtime dependencies are
read from the wheel METADATA, pinned via constraints to the exact versions in
`/opt/wheelhouse`, and installed with `--no-index --no-deps`; the wheel itself is
installed with `--no-deps`. A prebuilt TensorFlow wheel in `/opt/wheelhouse` is
rejected by `doctor` so no prebuilt package can accidentally satisfy the run.
`tensorflow-io-gcs-filesystem` is treated as optional (the runtime falls back
gracefully) and reported under `optional_missing` when absent.

## Commands

```
python3 solution/main.py --help                          # usage only, no build
python3 solution/main.py doctor --input /workspace/input # exit 78 if missing, 0 if ready
python3 solution/main.py run --input /workspace/input --output /workspace/output --jobs 4
```

`doctor` verifies the archive sha256, parses `.bazelversion`, locates the Bazel
binary and rejects a version mismatch, checks the offline repository cache at
the design-declared path, reads the required package list from the official
`tensorflow/tools/pip_package/setup.py` template and cross-checks it against
`/opt/wheelhouse`. It prints a JSON report of the actual paths and hashes it
checked and returns exit code 78 whenever any non-optional item is missing.

## Honest limitations

A from-source TensorFlow CPU build requires, at minimum, a Bazel binary matching
`.bazelversion` and a fully populated offline Bazel repository cache (LLVM, XLA,
Eigen, protobuf, pybind11, rules_python, ...). Under a runtime where the offline
cache or the required Python wheels are missing, `doctor` returns exit code
**78** and prints exactly which items are absent, and `run` raises honestly
instead of substituting a prebuilt wheel. Nothing is claimed about wall time,
peak memory or Bazel action counts - the `reference_measurements` block of the
contract is unmeasured and is left as-is.
