Fourth bounded run; the previous run's only failure was a bookkeeping crash, not
a build or test problem.

FIX (latest real failure). `Session.run()` returns the path of the log file it
wrote, not a process/result object, so the negative-case code that read
`negative_decode.exit_code` raised `AttributeError: 'PosixPath' object has no
attribute 'exit_code'`. Exit status for `check=False` commands is now read from
`session.commands[-1]["exit_code"]`, exactly the record the helper appends for
every command, and the corrupt-input diagnostic is read from the recorded log path
(`output_dir / commands[-1]["log"]`). Both negative cases now assert a nonzero
exit code explicitly instead of merely observing output:

* corrupt compressed input must be rejected by the CLI decompression
  (`observed_exit_code != 0`);
* after temporarily removing the installed `libzstd.so`, relinking a fresh consumer
  must fail (`observed_exit_code != 0`), and the library is restored in a `finally`
  block with `artifact_restored` recorded.

PRESERVED. The streaming consumer fix from the previous round is unchanged:
compression feeds every chunk and keeps flushing with `ZSTD_e_end` until the call
returns 0 so the frame is completed (a `0` during `ZSTD_e_continue` only means the
current chunk was drained, never EOF), and decompression loops until
`ZSTD_decompressStream` returns 0 (decoded *and* flushed), continuing with an empty
input window after the compressed bytes are exhausted so a pending final flush
still happens, declaring truncation only when a call makes no forward progress.
There is no separate empty read loop that could reset completion state. Dictionary
compression, streaming semantics, the CLI dictionary round-trip and the binary
round-trip are all preserved.

MANDATORY REVIEW RETAINED. No `PAGER_C` stand-in exists and `PATH` is never
modified. The real `/usr/bin/less` is used verbatim by the upstream
`tests/cli-tests/cltools/zstdless.sh`; `doctor` lists `runtime:less` as a required
item (exit 78 when absent) and the run aborts with an explicit dependency error if
it is missing. `output/dependencies.json` records the resolved binary with
`"stand_in": false`.

Pipeline unchanged: verify archive SHA-256 against the manifest, extract to
/workspace/src, snapshot upstream test discovery, `make -j4`, `make install
PREFIX=...`, confirm `less`, run `make check` plus the four named targets through
`Session.test`, then build and run the out-of-tree consumers from
/workspace/consumer. `BUILD_JOBS<=4`, `TEST_JOBS<=2`; no network, no system install,
no modified test expectations.
