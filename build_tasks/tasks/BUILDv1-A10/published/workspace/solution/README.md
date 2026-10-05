# BUILDv1-A10 - libgit2 v1.9.1 embedded workspace-management package

## What it does

`solution/main.py` drives the frozen CORE build of libgit2 commit
`0060d9cf5666f015b1067129bd874c6cc4c9c7ac` (release `v1.9.1`):

1. `Session.prepare()` verifies the source tarball sha256 and safely extracts it to `/workspace/src`.
2. CMake configures `Release`, `BUILD_TESTS=ON`, `BUILD_EXAMPLES=ON`, `BUILD_CLI=OFF`,
   `USE_HTTPS=OpenSSL`, `USE_SSH=OFF`, installing into `/workspace/output/install`.
3. `cmake --build` with `--parallel <jobs>` (jobs is capped at 4).
4. `ctest -N -R '^offline$'` records the official CTest inventory to `ctest_inventory.txt`
   before execution.
5. The official offline suite runs through CTest in verbose mode. CTest's `offline` entry is a
   single aggregate test, so its own `1/1` percentage is never reported as a case count. The
   verbose transcript contains the real Clar output produced by `libgit2_tests -v -xonline`, one
   line per executed case (`<suite>::<case>` followed by `.` passed, `S` skipped, `F`/`E` failed).
   `parse_clar()` counts the distinct case lines, the suite prefixes, and the status characters,
   writing them to `clar_summary.json` and the full discovered case list to
   `clar_test_inventory.txt`. If no case line can be parsed the run fails instead of reporting 0.
6. `cmake --install` populates the private prefix.
7. A standalone C consumer (embedded in `main.py`, written to `/workspace/consumer/src`) is
   compiled outside the source tree against the installed headers/library and executed. It creates
   a repo, writes two blobs/trees/commits with a fixed signature, diffs them, rejects a nonexistent
   commit, checks out the older commit into the worktree and re-reads the file.
8. The resulting objects are re-checked with the system `git` CLI, the detached HEAD is compared to
   the consumer-reported commit, and `ldd` is required to resolve `libgit2.so` inside the install
   prefix (never the base image copy).

## Commands

```
python3 solution/main.py doctor --input input      # exit 0 when ready, 78 with a missing-item list
python3 solution/main.py run --input input --output output --jobs 4
```

`--help` prints usage without touching the source tree or building anything.

## Reporting rules

* `clar_summary.json` reports `suites`, `tests`, `passed`, `skipped`, `failed`, `assertions` and
  the number of cases whose status character was captured (`statuses_captured`). Values that the
  upstream transcript does not support stay `null`; nothing is extrapolated from the single CTest
  aggregate entry.
* `run.json` `features` mirrors the parsed Clar numbers (`clar_suites`, `clar_tests`,
  `clar_passed`, `clar_skipped`, `clar_failed`).

## Honest limitations

* Only local repository/object/index capability is exercised. Network, SSH and invasive suites are
  deliberately out of scope, matching the frozen CORE profile; the Clar suite itself is invoked with
  `-xonline`, so online cases are excluded upstream rather than skipped by this tool.
* If the mounted archive does not actually contain the bundled `deps` sources, CMake configuration
  will fail and the run aborts; that failure is reported honestly instead of being worked around.
* The consumer compares worktree content and object existence; byte-for-byte build reproducibility
  across hosts is not asserted.
