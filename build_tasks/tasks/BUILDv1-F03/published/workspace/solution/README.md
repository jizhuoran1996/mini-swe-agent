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

### Prepared Bazel cache (authoritative)

The doctor checks the actual prepared artifacts, not filename conventions:

- executable `/opt/bazel/7.4.1/bazel`
- non-empty `/workspace/cache/bazel_repository` (Bazel repository cache)
- non-empty `/workspace/cache/bazel_output/external` (prehydrated external tree)

The build is invoked as:

    build/build.py build --wheels=jaxlib --python_version=3.12 \
      --bazel_path=/opt/bazel/7.4.1/bazel \
      --bazel_startup_options=--output_base=/workspace/cache/bazel_output \
      --bazel_options=--repository_cache=/workspace/cache/bazel_repository \
      --bazel_options=--jobs=<jobs<=4> \
      --bazel_options=--local_ram_resources=24000

The Flags `--verbose` is intentionally not passed: it is not part of the build
subcommand's stable interface and the reviewer flagged it as unreliable. Hermetic
Python dependencies are resolved through Bazel's declared repositories; no
jaxlib is substituted from any prebuilt source.

### CPU-only dependency resolution

`build/test-requirements.txt` and `build/requirements_lock_3_12.txt` are parsed
with real PEP 508 syntax: line continuations, `--hash=...` option flags, extras,
environment markers, and every version specifier are handled. Accelerator-only
distributions (`nvidia-*`, `cuda*`, `cudnn`, `nccl`, `triton`, `libtpu`, `rocm`)
are filtered out: the frozen core profile is CPU-only and never requires a GPU
wheel. The retained set (plus a fixed minimal CPU list including rich/colorama/
pygments transitively pulled by the bootstrap wheelhouse) must be present under
`/opt/wheelhouse`.

## Honest limitations

- CPU-only. No CUDA/TPU is built or claimed.
- The official run is the core `testPad` subset only; full `lax_numpy` CPU
  coverage is outside the frozen core profile.
- Build is large and CPU-heavy; Bazel jobs are capped at 4 with a 24 GiB RAM
  budget.
- When the prepared Bazel cache, wheelhouse, or source archive is incomplete,
  doctor reports the exact missing items (exit 78) and does not weaken the
  contract into a skip.
