# BUILDv1-B06 core-profile Ruby source builder

Builds, tests, installs and independently consumes a fresh CRuby tree from the
frozen upstream tarball referenced by `manifest.json` without network access.

## Commands

- `python3 solution/main.py --help`
- `python3 solution/main.py doctor --input input`
  Checks the source archive checksum, bootstrap tools, development libraries
  and the bundled-gem cache. Prints every missing item and exits `78` when
  anything is absent, `0` when ready.
- `python3 solution/main.py run --input input --output output --jobs 4`
  Provisions cached bundled `.gem` files, runs `autogen.sh`, out-of-tree
  `configure` (invoked by absolute path inside `src/`), `make -j4`,
  `make test`, `make test-all TESTS=/workspace/src/test/ruby/test_string.rb`,
  `make install`, then executes the Ruby consumers under `/workspace/consumer`
  using the newly installed `bin/ruby` only.

## Offline bundled gems (root cause of the previous failure)

`make install` inside the Ruby 3.4 build downloads `test-unit`, `rake`,
`minitest`, `power_assert`, etc. via `tool/downloader.rb`, which contacts
`https://rubygems.org` and fails in an offline container. To keep the
scope intact, `run` copies cached `.gem` files from `/workspace/cache` (and the
frozen input directory) into `src/gems/` before the make rules fire, and
`doctor` reports any gem still missing as an explicit
`gem:<name>-<version>.gem` item and exits `78`. No source file is patched and
no downloader option is suppressed.

## Layout note

`src` and `build` are siblings (`/workspace/src`, `/workspace/build`).
`configure` is therefore called as `<src>/configure` from the build directory,
and the `test-all` selector uses the absolute path to the source-tree
`test/ruby/test_string.rb`.

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
- Build is offline. `doctor` returns `78` if the bundled gem cache has not been
  hydrated; the builder is expected to prepare it and retry. No gem is fetched
  from the network at build time.
- JIT is explicitly disabled, matching the reference profile.
- Consumer checks cover JSON, zlib, digest, socket, OpenSSL, thread queues,
  file I/O and string behavior; they do not claim to reproduce upstream CI.
