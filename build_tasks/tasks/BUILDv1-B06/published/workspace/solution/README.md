# BUILDv1-B06 core-profile Ruby source builder

Builds, tests, installs and independently consumes a fresh CRuby tree from the
frozen upstream tarball referenced by `manifest.json`.

## Commands

- `python3 solution/main.py --help`
- `python3 solution/main.py doctor --input input`
  Checks the source archive checksum, bootstrap tools and the development
  libraries needed by the selected default extensions. Prints every missing
  item and exits `78` when anything is absent, `0` when ready.
- `python3 solution/main.py run --input input --output output --jobs 4`
  Runs `autogen.sh`, out-of-tree `configure` (invoked by absolute path inside
  `src/`), `make -j4`, `make test`,
  `make test-all TESTS=/workspace/src/test/ruby/test_string.rb`,
  `make install`, then executes the Ruby consumers under
  `/workspace/consumer` using the newly installed `bin/ruby` only.

## Layout note

`src` and `build` are siblings (`/workspace/src`, `/workspace/build`).
`configure` is therefore called as `<src>/configure` from the build directory
instead of the `../configure` shown in the upstream recipe, and the
`test-all` selector uses an absolute path to the source-tree test file rather
than `../test/ruby/...`.

## Outputs

- `output/install/` installed Ruby tree
- `output/install.tar.gz` and `output/ruby-install.tar.gz`
- `output/logs/` every command log
- `output/commands.json`, `output/tests.json`
- `output/test_inventory.json`
- `output/rbconfig.json`, `output/default_gems.json`
- `output/consumer_report.json`
- `output/install_manifest.json`

## Honest limitations

- Core profile only: official selectors are `make test` and
  `test/ruby/test_string.rb`; the wider `test/ruby/` tree and ruby/spec are
  outside this profile.
- The build is intentionally offline. Missing dependencies are reported by
  `doctor` and are not downloaded at build time.
- JIT is explicitly disabled; the reference profile does not make optional
  JIT an implicit requirement.
- Consumer checks cover JSON, zlib, digest, socket, OpenSSL, thread queues,
  file I/O and string behavior. They do not claim to reproduce every upstream
  CI platform.
