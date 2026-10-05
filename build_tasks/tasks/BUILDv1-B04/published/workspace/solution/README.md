# BUILDv1-B04 - CPython source build (core profile)

Builds the locked CPython revision (v3.12.10, commit
`0cc81280367df838c4b199f8f0378837165071c2`) from the mounted source archive,
installs it into an isolated prefix, runs the frozen official regression
modules and proves the install tree is usable from new virtualenvs created
outside the source tree.

## Commands

    python3 solution/main.py doctor --input input
    python3 solution/main.py run --input input --output output --jobs 4

`doctor` validates the source archive checksum/size plus the presence of the C
toolchain, `env`, and the development headers used by the extension modules. It
exits `78` when anything is missing (listing exact items) and `0` when ready,
without building anything. `--help` never builds.

`run` performs, with every step recorded through the trusted `buildkit` helper:

1. `prepare()` - verifies the archive sha256 and safely extracts the tree.
2. `configure --prefix=<output>/install` in an out-of-tree build dir.
3. `make -j<BUILD_JOBS>` (default 4).
4. An extension gate importing `json, sqlite3, zlib, _ssl, ctypes, lzma, bz2,
   hashlib, select, socket, threading, asyncio, subprocess`; a silently omitted
   extension fails the run instead of turning into a skip.
5. `make install`.
6. Official regression modules `test_json`, `test_sqlite3`, `test_importlib`
   run through `./python -m test -v -j<TEST_JOBS>`.
7. Two consumer environments created with the freshly installed interpreter
   (`venv --without-pip`) under `/workspace/consumer`; `consumer.py` (written
   outside the source tree) executes a JSON to SQLite to JSON roundtrip, spawns
   a subprocess with the venv interpreter, runs four threads and an asyncio
   task, and asserts `sys.executable`, `sys.prefix` and `json.__file__` do not
   point into the source or build trees.
8. `finish()` emits `install_manifest.json`, `install.tar.gz`, `commands.json`,
   `tests.json` and `run.json`.

## Inherited environment handling (the test_importlib failure that was fixed)

The controller process is itself launched with `PYTHONPATH=/opt/controller`
(so `buildkit` is importable) and `PYTHONDONTWRITEBYTECODE=1`. Both reach the
interpreter under test through `buildkit.run()`, which copies `os.environ`
before applying explicit overrides - omitting a variable is therefore not
enough to remove it.

* `PYTHONPATH=/opt/controller` puts `/opt/controller` on `sys.path`. The
  official helper `test.support.import_helper.forget()` walks **every**
  `sys.path` entry and calls `unlink(<dir>/<module>.pyc)`. On the read-only
  root filesystem that syscall fails with `OSError: [Errno 30] Read-only file
  system`, which the helper does not catch (it only tolerates
  `FileNotFoundError`), so `test_importlib.test_threaded_import` reported
  `Ran 1277 tests ... FAILED (errors=5)`.
* `PYTHONDONTWRITEBYTECODE=1` suppresses `__pycache__/*.pyc` creation, which
  several importlib loader tests depend on.

Every interpreter invocation under test (extension gate, regrtest and both
consumer venvs) is therefore prefixed with
`env -u PYTHONPATH -u PYTHONDONTWRITEBYTECODE -u PYTHONPYCACHEPREFIX
-u PYTHONHOME -u PYTHONSTARTUP -u PYTHONUSERBASE ...`, so bytecode caching is
active and no controller directory is injected into `sys.path`. No upstream
test, fixture or expected output is modified, and no test is skipped.

`regrtest` runs in verbose (`-v`) mode so that any remaining failure keeps its
full traceback in the preserved log.

## Evidence layout

- `output/logs/*.log` - raw stdout+stderr for every command (with sha256).
- `output/commands.json` - exact argument lists, cwd, exit code, wall time.
- `output/tests.json` - per-selector official test records.
- `output/install_manifest.json` / `output/install.tar.gz` - installed tree.

## Honest limitations

- regrtest does not emit one of the helper's recognized machine summaries in
  this configuration, so `tests.json` may carry `parsed_count: null`; the full
  upstream verbose log is retained and the exit code plus the
  `Ran N tests`/`Result:` lines are the authoritative evidence. No case counts
  are manufactured.
- The `venv` consumer is created with `--without-pip`; no PyPI access and no
  third-party application packages are used, per the offline dependency plan.
- Only the declared core platform and the three frozen modules are validated;
  this does not represent the complete upstream CI matrix.
- Optimizations (PGO/LTO) are intentionally disabled to keep the build bounded;
  behaviour, not micro-benchmark performance, is the acceptance criterion.
