# libuv core build

Build the frozen libuv 1.51.0 source release, run the three core official tests
(`timer`, `spawn_exit_code`, `threadpool_queue_work_simple`), install the
development package, and compile/run a source-external C consumer that exercises
async file read, child process exit code, threadpool work, timer callback, TCP
loopback echo, and clean `uv_loop_close()` with no leaked handles.

## Usage

```bash
python3 solution/main.py doctor --input input
python3 solution/main.py run --input input --output output --jobs 4
```

The `doctor` subcommand verifies the source archive checksum and the presence of
`cmake`, `cc`, and `make`; it returns 78 if anything is missing and 0 when ready.

## Consumer build flags

The public libuv headers reference the real platform types `pthread_rwlock_t`
and `struct addrinfo`, which live behind glibc's POSIX/GNU feature macros. The
consumer is compiled with `-std=gnu11` plus `-D_GNU_SOURCE
-D_POSIX_C_SOURCE=200809L` so those true system declarations are exposed. No fake
declarations are introduced and no thread/async operation is removed.

Forward declarations of `on_read`, `on_server_write`, and `on_client_write` are
included so callbacks defined later in the file can be referenced from earlier
functions; the compiler error the bounded run reported was purely an ordering
issue, fixed without changing behavior.

## Honest limitations

The frozen core profile intentionally selects only the three declared official
tests. The source archive must match the manifest SHA-256 exactly. The consumer
uses only the newly installed prefix through an explicit `-I`/`-L`/`-rpath` link
line; `ldd` is checked to prove the resolved `libuv` is the local install, not a
system copy. No network is used or required.
