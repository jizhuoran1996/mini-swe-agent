# BUILDv1-F02 - TensorFlow v2.18.0 CPU wheel from source

Builds the complete TensorFlow CPU Python wheel from the frozen commit
`6550e4bd80223cdb8be6c3afd1f81e86a4d433c3` (release ref `v2.18.0`), runs the two
frozen official tests, then installs the newly built wheel into a fresh consumer
venv outside the source tree and verifies SavedModel save/reload semantics.

## What changed after the real 16461-action failure

The previous cold build compiled and linked **all 16,461 native actions**
(16,442 reached, `Linking tensorflow/libtensorflow_cc.so.2.18.0` completed) and
failed only at the final packaging action
`//tensorflow/tools/pip_package:wheel`:

```
File ".../build_pip_package.py", line 287, in patch_so
    rpath = subprocess.check_output(...)
FileNotFoundError: [Errno 2] No such file or directory: 'patchelf'
```

`build_pip_package.py` shells out to a **real `patchelf`** executable to rewrite
RPATHs inside the wheel's shared objects. No RPATH stub, source edit, or fake
wheel is acceptable, so this release:

* registers `patchelf` as a **required tool** in `doctor` (reported in
  `missing_tool`, exit code **78** when absent);
* discovers the genuine bootstrap binary (`PATH`, then the declared bootstrap
  directories) and runs an **actual `patchelf --version`** through `Session.run`
  *before* the build starts;
* exports the patchelf directory into Bazel actions with
  `--action_env=PATH=<patchelf dir>:<client PATH>` for both the build and the test
  invocations, so the wheel-packaging run action can execute the real tool.

No test, target, optimization, feature, input, or tolerance was reduced.

## Build vs Test configuration parity (this release)

The live review flagged a scheduling/config-consistency defect: the wheel build
used `--config=opt` plus the two `--repo_env` flags while the `bazel test`
invocation dropped them and re-added `--config=linux`, and the test invocation
was passing `--jobs=TEST_JOBS`. Those are the wrong knobs: Bazel `--jobs` bounds
**compilation**, not test execution.

This release fixes that narrowly:

* A single `shared` list is computed once and appended **verbatim** to both the
  wheel build and both `bazel test` invocations:
  `--action_env=PATH=...`, the clang compatibility copts, the two `--repo_env`
  flags (`USE_PYWRAP_RULES=1`, `WHEEL_NAME=tensorflow_cpu`), and `--config=opt`.
* The redundant `--config=linux` is dropped from the test invocation. The OS
  platform config is auto-selected by Bazel, and configure already writes the CPU
  copts into `build:opt`; stacking another config on top would change the compile
  action set and can force the giant native graph to rebuild.
* Compilation jobs use `session.jobs` (= `min(user --jobs, manifest
  build_job_limit)`; this manifest declares 8) for **both** the wheel build and
  the test invocations, so test-originated compilation shares the same bounded
  pool.
* Concurrent test **executions** are separately bounded at `TEST_JOBS=2` via
  `--local_test_jobs=2`.
* `--local_ram_resources=16000`, `--test_output=all`, `--cache_test_results=no`,
  `--test_timeout=1800` are preserved.
* The **same cold `--output_base`** is used everywhere, so Bazel can reuse only
  actions genuinely compiled in this run - never preloaded/exported target
  outputs or prior-run caches.
* Official selections, filters, expectations, tolerances and the classifier are
  unchanged: `//tensorflow/python/kernel_tests/nn_ops:softmax_op_test` and
  `//tensorflow/python/saved_model:load_test` with
  `--test_filter=*LoadTest.test_capture_variables*`.

This is a consistency fix between the supported upstream configuration and the
independently bounded build-vs-test concurrency; no acceptance test was relaxed,
no test was skipped, no expectation was altered.

## Parallelism

Build parallelism is `min(user --jobs, manifest build_job_limit)` (this manifest
declares 8) and the Bazel `--jobs` value is bound to it for both `bazel build`
and `bazel test`; `--local_ram_resources=16000` is retained. Official test
execution parallelism stays fixed at `TEST_JOBS=2` via `--local_test_jobs=2`.

## Other frozen CPU build facts baked into this solution

- **Bazel**: `.bazelversion` is parsed as the first non-empty, non-comment line
(TensorFlow 2.18.0 pins `6.5.0`); the binary is always
`/opt/bazel/<version>/bazel` (never any other installed Bazel). `/opt/bazel/6.5.0`
is prepended to `PATH` for `bash ./configure` so upstream `configure.py`'s Bazel
probe sees the correct tool.
- **Configure**: invoked as `bash ./configure` (a bash wrapper that execs
`configure.py` via `$PYTHON_BIN_PATH`). CPU answers are supplied through the
environment (`PYTHON_BIN_PATH`, `TF_NEED_CUDA=0`, `TF_NEED_ROCM=0`,
TensorRT/SYCL/OpenCL/MPI off, `TF_NEED_CLANG=1`), so no interactive prompt is
issued. `.tf_configure.bazelrc` is verified before the build may start.
- **Bazel caches**: derived from the manifest's
`bazel_dependency_preparation.cache_directories` (`bazel_repository`,
`bazel_output/external`), i.e. the repository cache at
`/workspace/cache/bazel_repository`, explicit startup
`--output_base=/workspace/cache/bazel_output`, and prepared external repositories
at `/workspace/cache/bazel_output/external`. These are the exact paths the
builder froze; no legacy cache locations are invented. `HOME` for the Bazel
server is redirected to `/workspace/build/home`, so no global HOME change is
needed.
- **Prepared external repositories are immutable inputs.** We never synthesize
toolchain configuration or stub workspace rules; `doctor`/`run` verify that
`local_config_cc` carries its real `BUILD` and
`armeabi_cc_toolchain_config.bzl` and otherwise fail honestly with the actual
path.
- **clang-18 compatibility flags**: the vendored `@upb//:upb` C source uses an
anonymous struct type inside `offsetof`, which clang>=16 diagnoses as
`-Wgnu-offsetof-extensions`; TensorFlow's `-Werror` set promotes this to an
error. We pass only `--copt=-Wno-error=gnu-offsetof-extensions` and
`--host_copt=-Wno-error=gnu-offsetof-extensions` (also included in the
`CC_OPT_FLAGS` used by `configure`) so that one known C extension is demoted back
to a warning for target and host compilations. These are the *same* flags used by
the wheel build and both test invocations. Every other warning/error setting, all
source code, all BUILD/toolchain definitions and all official tests remain
unchanged.
- **Build**: `bazel --output_base=... build --repository_cache=... --jobs=<N>
--local_ram_resources=16000 --action_env=PATH=...
--copt=-Wno-error=gnu-offsetof-extensions
--host_copt=-Wno-error=gnu-offsetof-extensions --repo_env=USE_PYWRAP_RULES=1
--repo_env=WHEEL_NAME=tensorflow_cpu --config=opt
//tensorflow/tools/pip_package:wheel` - the full `tensorflow_cpu` wheel, no
shrinking of the model/core targets.
- **Tests**: `bazel test --jobs=<N> --local_test_jobs=2 --local_ram_resources=16000
--test_output=all --cache_test_results=no --test_timeout=1800` plus the *same*
`--action_env=PATH=...`, the same clang compatibility flags, the same two
`--repo_env` flags and the same `--config=opt` shared with the wheel build, on
the frozen official selections
`//tensorflow/python/kernel_tests/nn_ops:softmax_op_test` and
`//tensorflow/python/saved_model:load_test` with
`--test_filter=*LoadTest.test_capture_variables*`.
- **Install / consumer**: the new wheel is copied to `--output`, unpacked into
`/workspace/output/install`, and installed into a fresh
`/workspace/consumer/venv` (no system site packages). Runtime dependencies are
read from the wheel METADATA, pinned via constraints to the exact versions in
`/opt/wheelhouse`, and installed with `--no-index --find-links` (offline, so
`pip` resolves the genuine transitive closure - `requests -> urllib3`/`idna`/
`charset-normalizer`/`certifi`, `keras -> rich`/`namex`/`optree`, ...) from the
frozen wheelhouse; the direct dependencies remain pinned by the constraint file.
The newly built target wheel itself is installed with
`--no-index --no-deps` into both the install tree and the consumer venv, so a
prebuilt TensorFlow wheel present in `/opt/wheelhouse` is rejected by `doctor`
and can never satisfy the run.
`tensorflow-io-gcs-filesystem` is treated as optional (its absence does not break
`import tensorflow`) and reported under `optional_missing`. Save and reload are
executed in **separate consumer processes** so the reload is a genuine second
process using only the newly built wheel + pinned dependencies.

## Commands

```
python3 solution/main.py --help                           # usage only, no build
python3 solution/main.py doctor --input /workspace/input  # exit 78 if missing, 0 if ready
python3 solution/main.py run --input /workspace/input --output /workspace/output --jobs 8
```

## Honest limitations

A from-source TensorFlow CPU build requires, at minimum, a Bazel matching
`.bazelversion`, a fully sealed offline dependency set (the Bazel repository
cache and the pre-resolved `external` repository tree: LLVM, XLA, Eigen,
protobuf, pybind11, rules_python, `local_config_cc`, ...), and a real `patchelf`
for the official packaging step. Those are prepared by the builder; this solution
verifies their actual paths, hashes, and `--version` output but does not and
cannot regenerate them offline. When any of them is missing, `doctor` returns
exit code **78** listing the exact absent items and `run` aborts before invoking
Bazel. Nothing is claimed about wall time, peak memory or Bazel action counts -
the `reference_measurements` block of the contract is unmeasured.
