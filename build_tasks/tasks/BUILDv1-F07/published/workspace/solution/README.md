# BUILDv1-F07 - pandas 2.2.3 source build

Builds the pandas 2.2.3 Cython distribution (native `pandas._libs` extensions)
from the frozen PyPI sdist with meson-python, installs the resulting wheel into
an isolated venv, runs the official `pandas.tests.libs` + `pandas.tests.tslibs`
suite, and verifies the wheel from an independent consumer venv.

## Commands

```
python3 solution/main.py --help
python3 solution/main.py doctor --input input
python3 solution/main.py run --input input --output output --jobs 4
```

*d `doctor` checks the source archive checksum, the C/C++ toolchain, the
required Python build modules (meson-python, meson, Cython, numpy, versioneer)
and the `/opt/wheelhouse` dependency cache. It prints each missing item and
exits `78` when anything is absent, `0` when ready.

## Pipeline (all steps via `buildkit.Session`)

1. `Session.prepare()` verifies the sdist sha256 and extracts it under
   `/workspace/src` (no prebuilt objects reused).
2. `python -m build --wheel --no-isolation --config-setting=compile-args=-j4`
   compiles and links the extensions; the wheel lands in `output/`.
3. The wheel is installed with `pip --no-index --find-links /opt/wheelhouse`
   into `/workspace/output/install` (build/test venv).
4. Official tests: `pytest --pyargs pandas.tests.libs pandas.tests.tslibs
   -m "not network and not db" -n 2`.
5. An independent consumer venv at `/workspace/consumer/venv` reinstalls the
   same freshly built wheel and runs `solution/consumer.py`, which asserts the
   native `.so` files load from the installed wheel (not the source tree),
   performs tz-aware groupby aggregation with missing values, writes the data
   out, then re-derives the results in a fresh process.

## Honest limitations

- `doctor` reflects the frozen `offline_dependencies_ready: false` state of
  the contract: if the wheelhouse lacks a build/test dependency, `doctor` will
  name it and the runner fails honestly rather than substituting a network
  download or a prebuilt pandas.
- The core profile intentionally excludes `pandas.tests.groupby`; only
  `libs` and `tslibs` are executed and reported.
- If the upstream suite reports failing cases, the exit code and full pytest
  log are preserved in `output/logs/` and `output/tests.json`; failing tests
  are never converted into skips and expectations are never edited.
