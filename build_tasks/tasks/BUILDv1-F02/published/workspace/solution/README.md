# BUILDv1-F02 - TensorFlow v2.18.0 CPU wheel from source

Builds the complete TensorFlow CPU Python wheel from the frozen commit
`6550e4bd80223cdb8be6c3afd1f81e86a4d433c3` (release ref `v2.18.0`), runs the two
frozen official tests, then installs the newly built wheel into a fresh consumer
venv outside the source tree and verifies SavedModel save/reload semantics.

## Frozen CPU build facts baked into this solution

- **Bazel**: `.bazelversion` is parsed as the first non-empty, non-comment line;
the matching binary is looked up at `/opt/bazel/<version>/bazel` (the runtime
ships 6.5.0 / 7.4.1 / 7.6.0; 2.18.0 uses the 6.5.0 one). `/opt/bazel/<ver>` is
prepended to `PATH` for `./configure`.
- **Bazel caches** (declared by the design, hydrated by the manifest into
`/workspace/cache`): repository cache `/workspace/cache/bazel_repository`,
explicit startup `--output_base=/workspace/cache/bazel_output`.
- **CPU config**: `TF_NEED_CUDA=0`, `TF_NEED_ROCM=0`, TensorRT/SYCL/MPI off,
`.tf_configure.bazelrc` produced by the upstream `configure.py` with clang-18 /
CPython 3.12 answers.
- **Build**: `bazel --output_base=... build --repository_cache=... --jobs=4
--local_ram_resources=24000 --repo_env=USE_PYWRAP_RULES=1
--repo_env=WHEEL_NAME=tensorflow_cpu --config=opt
//tensorflow/tools/pip_package:wheel` - the full `tensorflow_cpu` wheel, no
shrinking of the model/core targets.
- **Tests**: `--config=linux --local_test_jobs=2 --cache_test_results=no` on the
frozen official selections `//tensorflow/python/kernel_tests/nn_ops:softmax_op_test`
and `//tensorflow/python/saved_model:load_test` with
`--test_filter=*LoadTest.test_capture_variables*`.
- **Consumer**: a fresh `/workspace/consumer/venv` with no system site packages;
the new wheel is installed with `--no-index --find-links=/opt/wheelhouse` plus a
constraints file pinning every runtime dependency to the exact version present in
the wheelhouse. A prebuilt TensorFlow wheel in `/opt/wheelhouse` is rejected by
`doctor`.

## Commands

```
python3 solution/main.py --help                          # usage only, no build
python3 solution/main.py doctor --input /workspace/input # exit 78 if missing, 0 if ready
python3 solution/main.py run --input /workspace/input --output /workspace/output --jobs 4
```

`doctor` verifies the archive sha256, parses `.bazelversion`, locates the Bazel
binary, checks the offline repository cache and the required packages (read from
the official `tensorflow/tools/pip_package/setup.py` template) against
`/opt/wheelhouse`, and refuses to pass if a prebuilt TensorFlow is present. It
prints a JSON report of the actual paths and hashes it checked.

## Honest limitations

A from-source TensorFlow CPU build requires, at minimum, a Bazel binary matching
`.bazelversion` and a fully populated offline Bazel repository cache (LLVM, XLA,
Eigen, protobuf, pybind11, rules_python, ...). This task ships with
`offline_dependencies_ready: false` and no network access. Under those conditions
`doctor` returns exit code **78** and prints exactly which items are missing, and
`run` raises honestly rather than substituting a prebuilt wheel. Once the builder
seeds the repository cache and `/opt/wheelhouse`, `doctor` returns 0 and `run`
executes the complete configure -> build -> package -> test -> consumer pipeline.

Nothing is claimed about wall time, peak memory or Bazel action counts - the
`reference_measurements` block of the contract is unmeasured and is left as-is.
No global `HOME` change is made; all writable paths are under `/workspace`.
