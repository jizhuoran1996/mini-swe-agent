# BUILDv1-F04 (core) — scikit-learn 1.6.1 source build

This delivers the **core profile** of BUILDv1-F04: build a complete native
scikit-learn wheel from the pinned source tarball, install it into an isolated
environment, run the official `sklearn.neighbors.tests.test_kd_tree` suite from
outside the source tree, and verify the compiled KD-tree extension plus a
serializable scikit-learn Pipeline from a standalone consumer virtualenv.

It deliberately does **not** run the reference/extended neighbour/model_selection
test sets — those belong to higher scale profiles.

## Usage

```
# readiness probe (fast, no build)
python3 solution/main.py doctor --input /workspace/input

# full pipeline
python3 solution/main.py run --input /workspace/input --output /workspace/output --jobs 4
```

`--help` never triggers a build. `doctor` prints each missing source, tool, or
wheelhouse dependency and exits with status **78** if anything is missing, **0**
if the environment is ready.

## What `run` does

1. `Session.prepare()` checks the source tarball SHA-256 against the manifest and
   extracts it into `/workspace/src` (unsafe archive members are rejected).
2. A build venv (`/workspace/build/build-venv`) is created with no system site
   packages and populated from `/opt/wheelhouse` using `--no-index`:
   `numpy`, `scipy`, `cython`, `meson-python`, `ninja`, `build`, ...
3. `python -m build --wheel --no-isolation --outdir ARTIFACTS
   --config-setting=compile-args=-j4 SRC` with `NINJAFLAGS=-j4` (concurrency
   capped at the frozen `build_jobs=4`). The Cython → C/C++ → shared-object
   compilation runs under the meson-python backend and its full log is kept.
4. The freshly produced wheel is installed with `--no-index --no-deps` into
   `$INSTALL_ROOT/venv` (`/workspace/output/install/venv`).
5. A separate consumer venv at `/workspace/consumer/venv` receives the same
   wheel plus runtime/test dependencies from the wheelhouse.
6. The official suite is executed from `/workspace/consumer/test-run` (outside
   the source tree) using `python -m pytest --pyargs
   sklearn.neighbors.tests.test_kd_tree --import-mode=importlib`, preceded by a
   `--collect-only` inventory run so the exact discovered test count is
   preserved in the logs.
7. Two consumer programs (embedded in `solution/main.py`) run inside the
   consumer venv:
   * `consumer_fit.py` — asserts `sklearn.__file__` points at the wheel's
     `site-packages` (never `/workspace/src`), compares `KDTree.query` against a
     brute-force distance ordering, fits `StandardScaler + LogisticRegression`,
     and pickles the pipeline plus its inputs/expected predictions.
   * `consumer_reload.py` — runs in a fresh process, unpickles the model, and
     asserts bit-identical predictions and equal probabilities.

## Outputs

* `output/artifacts/scikit_learn-1.6.1-*.whl` — the source-built wheel
* `output/install/venv/...` — installed environment (hashed into `install_manifest.json`)
* `output/logs/*.log` — every build/configure/install/test/consumer command
* `output/commands.json`, `output/tests.json`, `output/install_manifest.json`, `output/run.json`
* `/workspace/consumer/verify/pipeline.pkl` — reloadable pipeline artifact

## Honest limitations

* This is the **core** scope. Only `sklearn.neighbors.tests.test_kd_tree` is
  executed; the full `sklearn.neighbors.tests` subpackage is reserved for the
  reference profile.
* Wheel bytes are not required to be byte-reproducible; the manifest records the
  actual SHA-256 of the produced wheel.
* Build/test concurrency is capped at `--jobs 4` / 2 OMP threads exercised via
  environment variables; no CPU feature detection (`-march=native`) is used.
* All dependency resolution uses `/opt/wheelhouse` via `--no-index`; no network
  access is performed at any point.
