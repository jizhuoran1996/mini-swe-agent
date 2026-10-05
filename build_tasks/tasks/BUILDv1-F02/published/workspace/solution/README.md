# BUILDv1-F02 - TensorFlow v2.18.0 CPU wheel from source

Builds the complete TensorFlow CPU Python wheel from the frozen commit
`6550e4bd80223cdb8be6c3afd1f81e86a4d433c3` (release ref `v2.18.0`), runs the two
frozen official tests, then installs the newly built wheel into a fresh consumer
venv outside the source tree and verifies SavedModel save/reload semantics.

## Frozen CPU build facts baked into this solution

- **Bazel**: `.bazelversion` is parsed as the first non-empty, non-comment line
(TensorFlow 2.18.0 pins `6.5.0`); the binary is always
`/opt/bazel/<version>/bazel` (never any other installed Bazel). `/opt/bazel/6.5.0`
is prepended to `PATH` for `bash ./configure` so upstream `configure.py`'s Bazel
probe sees the correct tool.
- **Configure**: invoked as `bash ./configure`. The upstream wrapper is a bash
script (not a Python file) which execs `configure.py` via `$PYTHON_BIN_PATH`.
CPU answers are supplied through the environment (`PYTHON_BIN_PATH`,
`TF_NEED_CUDA=0`, `TF_NEED_ROCM=0`, TensorRT/SYCL/MPI off, `TF_NEED_CLANG=1`), so
no interactive prompt is issued. The resulting `.tf_configure.bazelrc` is
verified before the build may start.
- **Bazel caches**: derived from the manifest's
`bazel_dependency_preparation.cache_directories` (`bazel_repository`,
`bazel_output/external`), i.e. the repository cache at
`/workspace/cache/bazel_repository`, explicit startup
`--output_base=/workspace/cache/bazel_output`, and prepared external repositories
at `/workspace/cache/bazel_output/external`. These are the exact paths the
builder froze; no legacy cache locations are invented. `HOME` for the Bazel
server is redirected to `/workspace/build/home`, so no global HOME change is
needed.
- **Prepared external repositories are treated as immutable inputs.** We never
synthesize toolchain configuration or stub workspace rules. `doctor` and `run`
verify that `local_config_cc` carries its real `BUILD` and
`armeabi_cc_toolchain_config.bzl`; if not, the pipeline fails honestly with the
actual path so the builder can re-run the corrected preparation step.
- **Clang-18 compatibility flags**: the vendored `@upb//:upb` C source uses an
anonymous struct type inside `offsetof`, which clang-18 diagnoses as
`-Wgnu-offsetof-extensions`; TensorFlow's `-Werror` set promotes this to an
error. We pass only `--copt=-Wno-error=gnu-offsetof-extensions` and
`--host_copt=-Wno-error=gnu-offsetof-extensions` (also included in the
`CC_OPT_FLAGS` used by `configure`) so that this one known C extension is
demoted back to a warning for target and host compilations. Every other
warning/error setting, all source code, all BUILD/toolchain definitions and all
official tests remain unchanged.
- **Build**: `bazel --output_base=... build --repository_cache=... --jobs=4
--local_ram_resources=24000 --copt=-Wno-error=gnu-offsetof-extensions
--host_copt=-Wno-error=gnu-offsetof-extensions --repo_env=USE_PYWRAP_RULES=1
--repo_env=WHEEL_NAME=tensorflow_cpu --config=opt
//tensorflow/tools/pip_package:wheel` - the full `tensorflow_cpu` wheel, no
shrinking of the model/core targets.
- **Tests**: `--config=linux --local_test_jobs=2 --cache_test_results=no` plus
the same clang compatibility flags, on the frozen official selections
`//tensorflow/python/kernel_tests/nn_ops:softmax_op_test` and
`//tensorflow/python/saved_model:load_test` with
`--test_filter=*LoadTest.test_capture_variables*`.
- **Install / consumer**: the new wheel is copied to `--output`, unpacked into
`/workspace/output/install`, and installed into a fresh
`/workspace/consumer/venv` (no system site packages). Runtime dependencies are
read from the wheel METADATA, pinned via constraints to the exact versions in
`/opt/wheelhouse`, and installed with `--no-index --no-deps`; the wheel itself is
installed with `--no-deps`. A prebuilt TensorFlow wheel present in `/opt/wheelhouse`
is rejected by `doctor`, so no prebuilt package can satisfy the run.
`tensorflow-io-gcs-filesystem` is treated as optional (its absence does not break
`import tensorflow`) and reported under `optional_missing`.

## Commands

```
python3 solution/main.py --help                           # usage only, no build
python3 solution/main.py doctor --input /workspace/input  # exit 78 if missing, 0 if ready
python3 solution/main.py run --input /workspace/input --output /workspace/output --jobs 4
```

## Honest limitations

A from-source TensorFlow CPU build requires, at minimum, a Bazel matching
`.bazelversion` plus a fully sealed offline dependency set: the Bazel repository
cache and the pre-resolved `external` repository tree (LLVM, XLA, Eigen,
protobuf, pybind11, rules_python, `local_config_cc`, ...). Those are prepared by
the builder; this solution verifies their actual paths and hashes but does not
and cannot regenerate them offline. When they are missing or incomplete, `doctor`
returns exit code **78** listing the exact absent items and `run` aborts before
invoking Bazel. Nothing is claimed about wall time, peak memory or Bazel action
counts - the `reference_measurements` block of the contract is unmeasured.
