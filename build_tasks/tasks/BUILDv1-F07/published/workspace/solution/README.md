# BUILDv1-F07 - pandas 2.2.3 source wheel

Builds the pandas 2.2.3 Cython distribution (native `pandas._libs` extensions)
from the frozen PyPI sdist, installs the freshly built wheel, runs the frozen
official `pandas.tests.libs` + `pandas.tests.tslibs` suite, and independently
re-consumes the wheel from a separate venv.

## Commands

```
python3 solution/main.py --help
python3 solution/main.py doctor --input input
python3 solution/main.py run --input input --output output --jobs 4
```

`doctor` verifies the sdist checksum, the C/C++/ninja toolchain, the stdlib
`venv`/`ensurepip` modules and every required offline wheel in `/opt/wheelhouse`,
including the **exact pinned numpy**. It prints each missing item and exits
`78`, or `0` when ready. `--help` builds nothing.

## numpy pin (the fixed segfault)

The first attempt followed the upstream `[build-system].requires` literally:
`numpy>=2.0`. Offline pip then resolved numpy **2.5.3**, and the consumer
segfaulted (SIGSEGV, `-11`) inside the compiled pandas code. pandas 2.2.3's
native extensions are not compatible with that numpy generation, so numpy is now
pinned to **`numpy==2.2.6`** - an older, supported release that satisfies the
upstream `>=2.0` requirement - and the *same* pin is used for the build venv,
the runtime test venv and the consumer venv. `versions.json` records the
concrete numpy/Cython/meson-python/pandas versions observed in every
environment, and the runner refuses to continue if the build, runtime and
consumer numpy versions differ (ABI consistency). No assertion, operation or
official test was removed or weakened to accommodate the pin.

## Filesystem roles (no venv anywhere under `output/install`)

| path | role |
| --- | --- |
| `/workspace/src` | verified extracted sdist sources |
| `/workspace/build/build-venv` | bounded offline venv holding **only** the pinned upstream build requirements; its `bin/` is prepended to `PATH` for every build command |
| `/workspace/tools/install-venv` | runtime venv used to execute the official upstream tests |
| `/workspace/output/pandas-*.whl` | the full source-built wheel, delivered at the output root |
| `/workspace/output/install` | declared install root: **package files only** (`pip install --no-index --no-deps --target`); `_venv()` hard-refuses any path under this root |
| `/workspace/consumer/venv` | independent consumer venv, outside src, output and install root |

## Pipeline (every step goes through `buildkit.Session`)

1. `prepare()` verifies the sdist sha256 and extracts it under `/workspace/src`.
2. A bounded build venv under `/workspace/build/build-venv` receives the pinned
   `[build-system].requires` from `/opt/wheelhouse` (offline, no isolation).
3. Every build-related command runs with **`build-venv/bin` prepended to
   `PATH`**: the pinned `meson==1.2.1`/`meson-python==0.13.1` win over the
   global `/opt/build-tools` toolchain, and the `#!/usr/bin/env python3` shebang
   in `generate_version.py` resolves to the venv interpreter that carries
   `versioneer[toml]` + `tomli`. No upstream file is rewritten.
4. `python -m build --wheel --no-isolation --config-setting compile-args=-j4`
   compiles and links the native extensions; the complete wheel lands at
   `/workspace/output/`.
5. The same wheel is installed into `/workspace/tools/install-venv` (to run
   tests) and, via `pip install --no-index --no-deps --target
   /workspace/output/install`, as plain package files for the artifact tree.
6. Official tests: `pytest --pyargs pandas.tests.libs pandas.tests.tslibs
   -m "not network and not db" -n 2` from a scratch cwd (never the source tree,
   so the installed wheel is exercised), with `PYTHONFAULTHANDLER=1`.
7. `/workspace/consumer/venv` reinstalls the same freshly built wheel and runs
   `solution/consumer.py` in three phases: `smoke` (tiny groupby probe),
   `build` (tz-aware groupby with missing values and duplicate keys, join of a
   lookup table, write out) and `reload` (fresh process re-derives every
   number, `weighted == 24`, same numpy). Every phase asserts that the native
   `.so` files load from the installed wheel, not the source tree.

## Honest limitations

- The frozen contract records `offline_dependencies_ready: false`. If the
  wheelhouse lacks `numpy==2.2.6` or any other exact build requirement,
  `doctor` names it and the runner fails honestly rather than reaching the
  network or reusing a prebuilt pandas. Neither a prebuilt pandas wheel nor a
  metadata-only package can satisfy the consumer assertions or the
  `--no-build-isolation` build.
- The core profile deliberately excludes `pandas.tests.groupby`; only `libs` and
  `tslibs` are executed and reported. `run.json` records this selector set.
- If the upstream suite reports failing cases, the exit code and full pytest log
  stay in `output/logs/` and `output/tests.json`; failures are never converted
  into skips and upstream expectations are never edited.
- Parquet persistence is used only when `pyarrow` is present in the wheelhouse;
  otherwise the consumer falls back to CSV and records which storage was used.
