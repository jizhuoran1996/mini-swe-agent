# BUILDv1-F03 core: CPU jaxlib + JAX source build

Builds the CPU `jaxlib` native wheel and the matching `jax` frontend wheel from
the pinned JAX 0.5.3 source tree using the prepared Bazel 7.4.1 and its
prehydrated repository/output caches, installs both wheels into a fresh venv
outside the source tree, runs the official `testPad` subset of
`tests/lax_numpy_test.py`, and then exercises an independent JIT/vmap/grad
consumer.

## Usage

    python3 solution/main.py doctor --input /workspace/input
    python3 solution/main.py run --input /workspace/input --output /workspace/output --jobs 4

`doctor` exits 78 listing exact missing items when anything is absent, 0 when
the prepared environment is ready.

## Prepared cache (checked as-is, no filename conventions)

- executable `/opt/bazel/7.4.1/bazel`
- non-empty `/workspace/cache/bazel_repository` (Bazel repository cache)
- non-empty `/workspace/cache/bazel_output/external` (hydrated external tree)

Build invocation (explicit argument list, no shell):

    build/build.py build --wheels=jaxlib --python_version=3.12 \
      --bazel_path=/opt/bazel/7.4.1/bazel \
      --bazel_startup_options=--output_base=/workspace/cache/bazel_output \
      --bazel_options=--repository_cache=/workspace/cache/bazel_repository \
      --bazel_options=--jobs=<jobs<=4> \
      --bazel_options=--local_ram_resources=24000

No `--verbose` flag is passed (not part of `build`'s stable CLI). Hermetic
Python dependencies are resolved by Bazel's declared repositories; no prebuilt
jaxlib is substituted anywhere.

## External-tree repair step

The first execution aborted during analysis with:

    Unable to load package for @@llvm-raw//:WORKSPACE: BUILD file not found
    in directory '' of external repository @@llvm-raw

The hydrated external tree contains real repository contents (its
`utils/bazel/configure.bzl` loads fine) but is missing the empty root
`WORKSPACE` markers Bazel writes into every fetched repository; the JAX/XLA
rule `llvm_configure` resolves repository roots with
`repository_ctx.path(Label("@llvm-raw//:WORKSPACE"))`, so a missing marker
breaks analysis. Before invoking Bazel the runner:

1. re-creates an empty root `WORKSPACE` in every non-symlink external
   repository directory that lacks one (leaving existing `WORKSPACE.bazel`
   untouched),
2. deletes dangling repository symlinks and empty repository directories along
   with their `@<repo>.marker` files so Bazel re-materialises them from the
   prepared repository cache — still fully offline.

Actions are recorded in `output/external_tree_repair.json`. Nothing is
fabricated: if the cache cannot satisfy a repository, Bazel fails loudly.

## CPU-only dependency resolution

`build/test-requirements.txt` and `build/requirements_lock_3_12.txt` are parsed
with real PEP 508 syntax (line continuations, `--hash` flags, extras, markers,
all version operators). Accelerator-only distributions (`nvidia-*`, `cuda*`,
`cudnn`, `nccl`, `triton`, `libtpu`, `rocm`) are filtered out: the frozen core
profile is CPU-only.

## Honest limitations

- CPU-only; no CUDA/TPU is built or claimed.
- The official run is the core `testPad` subset only.
- The full XLA compile is large: Bazel jobs are capped at 4 with a 24 GiB RAM
  budget and a 9000 s build deadline inside the 3 h task wall.
- When the prepared cache, wheelhouse, or source archive is incomplete the run
  fails honestly; it never weakens the contract into a skip.
