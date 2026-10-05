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

`doctor` verifies the sdist checksum, the C/C++/ninja toolchain and the exact
upstream build/test wheels in `/opt/wheelhouse` (`meson-python==0.13.1`,
`meson==1.2.1`, `Cython~=3.0.5`, `numpy>=2.0`, `versioneer[toml]`, `wheel`,
`build`, plus run/test deps). It prints every missing item and exits `78`, or
`0` when ready. `--help` builds nothing.

## Filesystem roles (no venv anywhere under `output/install`)

| path | role |
| --- | --- |
| `/workspace/src` | verified extracted sdist sources |
| `/workspace/build/build-venv` | bounded offline venv holding **only** the pinned upstream build requirements; its `bin/` is prepended to `PATH` for every build command |
| `/workspace/tools/install-venv` | runtime venv used to execute the official upstream tests |
| `/workspace/output/pandas-*.whl` | the full source-built wheel, delivered at the output root |
| `/workspace/output/install` | declared install root: **package files only** (`pip install --no-index --no-deps --target`); the `_venv()` helper hard-refuses any path under this root |
| `/workspace/consumer/venv` | independent consumer venv, outside src, output and install root |

## Pipeline (every step goes through `buildkit.Session`)

1. `prepare()` verifies the sdist sha256 and extracts it under `/workspace/src`.
2. A bounded build venv under `/workspace/build/build-venv` receives the exact
   `[build-system].requires` pins from `/opt/wheelhouse` (offline, no isolation).
3. Every build-related command (`build_requirements`, `build_frontend`,
   `build_wheel`) runs with **`build-venv/bin` prepended to `PATH`**. This is the
   root cause fix: the pinned `meson==1.2.1`/`meson-python==0.13.1` from the
   wheelhouse now win over the mismatched global `/opt/build-tools` toolchain,
   and the `#!/usr/bin/env python3` shebang in `generate_version.py` resolves to
   the venv interpreter that actually has `versioneer[toml]` + `tomli` + `numpy`.
   `generate_version.py` is never rewritten and no global interpreter is used.
4. `python -m build --wheel --no-isolation --config-setting compile-args=-j4`
   compiles and links the native extensions; the complete wheel lands at
   `/workspace/output/`.
5. The same wheel is installed two ways: into
   `/workspace/tools/install-venv` (to run tests) and, with
   `pip install --no-index --no-deps --target /workspace/output/install`, as
   plain package files for the declared artifact tree.
6. Official tests: `pytest --pyargs pandas.tests.libs pandas.tests.tslibs
   -m "not network and not db" -n 2` from a scratch cwd (never the source tree,
   so the installed wheel is exercised, not the sdist).
7. `/workspace/consumer/venv` reinstalls the same freshly built wheel and runs
   `solution/consumer.py`, which asserts the native `.so` files load from the
   installed wheel, performs tz-aware groupby with missing values and duplicate
   keys, joins a lookup table, writes the data out, then re-derives every number
   in a fresh process.

## Honest limitations

- The frozen contract records `offline_dependencies_ready: false`. If the
  wheelhouse lacks an exact build-requirement version, `doctor` names it and the
  runner fails honestly rather than reaching the network or reusing a prebuilt
  pandas. A prebuilt pandas or a metadata-only package cannot satisfy the
  consumer assertions or `--no-build-isolation`.
- The core profile deliberately excludes `pandas.tests.groupby`; only `libs` and
  `tslibs` are executed and reported. `run.json` records this selector set.
- If the upstream suite reports failing cases, the exit code and full pytest log
  stay in `output/logs/` and `output/tests.json`; failures are never converted
  into skips and upstream expectations are never edited.
- Parquet persistence is used only when `pyarrow` is present in the wheelhouse;
  otherwise the consumer falls back to CSV and records which storage was used.
