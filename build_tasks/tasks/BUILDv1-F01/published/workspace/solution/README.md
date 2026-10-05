# BUILDv1-F01 - CPU PyTorch wheel build + verification

## What this does
Builds a CPU-only `torch` wheel from the pinned PyTorch source archive using
its own PEP 517 backend (`setuptools.build_meta:__legacy__`, `--no-isolation`),
installs the freshly built wheel into an isolated consumer venv under
`/workspace/consumer/venv` (no system site-packages), runs the official
`test/test_nn.py -k Linear` selection outside the source tree, then exercises
the wheel from two independent consumers under `solution/`:

- `consumer_verify.py` - tensor math, analytic gradient of a matmul, `nn.Linear`
  forward + backward, `state_dict` save/load in a fresh scope, CPU-only
  assertion, and asserts the loaded `torch` lives inside the new venv.
- `consumer_ext.py` - compiles a small C++ tensor-add extension via
  `torch.utils.cpp_extension.load_inline` against the delivered headers, into an
  empty session-scoped `build_directory`, then loads it and checks semantics.

## Usage

    python3 solution/main.py run    --input input --output output --jobs 4
    python3 solution/main.py doctor --input input
    python3 solution/main.py --help

`doctor` performs no build; it lists every missing source archive, tool, or
wheelhouse dependency and returns `78` when anything is missing, `0` when ready.

## Profile (frozen CORE)
CPU wheel only. Disabled via environment: CUDA, ROCm, XPU, distributed (Gloo /
MPI / TensorPipe / NCCL), NNPACK, QNNPACK, XNNPACK, FBGEMM, Kineto, MKL-DNN,
Magma, cuDNN/cuSPARSELt/cuDSS/cuFile, ONNX, OpenCL, Vulkan. Kept: OpenMP,
mimalloc, standard ATen CPU kernels, `torch.nn`, autograd, serialization, and
`torch.utils.cpp_extension` headers. `USE_NATIVE_ARCH=0` is enforced.

Build parallelism is `--jobs` (capped at 4). Test-time OpenMP threads are 2.

## Honest limitations
- The full PyTorch CPU compile is very large; on the 6-CPU / 4-job container the
  `build` phase may exceed the 3 hour session budget. If it does, `run` reports
  the timeout honestly instead of fabricating success. This is the single
  biggest risk of the plan and is not hidden.
- `test_nn.py -k Linear` is a selection of the upstream file, not the whole
  file. Only the frozen CORE selector is executed; the reference profile adds
  `test_autograd.py` and is deliberately not run here.
- No GPU cases are executed; `torch.cuda.is_available()` is asserted False.
- Byte-for-byte reproducibility of the wheel is not claimed. The wheel hash is
  recorded in `output/wheel_sha256.json`.
- `finish()` marks `independent_verified` False because the grading host, not
  this process, performs the final independent check.

## Evidence layout (under `--output`)
- `commands.json`, `tests.json` - command + test records with log hashes
- `logs/*.log` - raw stdout/stderr of every build/test/consumer command
- `install/torch-*.whl` - the newly built wheel
- `install_manifest.json`, `install.tar.gz` - the packaged install tree
- `wheel_sha256.json`, `run.json` - artifact hashes and final summary
