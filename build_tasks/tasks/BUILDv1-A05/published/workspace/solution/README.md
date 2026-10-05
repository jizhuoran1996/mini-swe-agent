# BUILDv1-A05 — OpenSSL crypto/TLS SDK build & consumption

Builds the frozen OpenSSL source archive (`openssl-3.5.2`,
commit `0893a62353583343eb712adef6debdfbe597c227`) for `linux-x86_64`, runs
upstream source tests in the **core** profile (`TESTS="test_rsa test_dsa"`),
installs `install_sw` + `install_ssldirs`, and then verifies the installed
SDK from outside the source tree using a freshly compiled C consumer.

## Usage

```
python3 solution/main.py --help
python3 solution/main.py doctor --input /workspace/input
python3 solution/main.py run --input /workspace/input --output /workspace/output --jobs 4
```

`doctor` returns exit code 0 when the source archive (sha256), C/assembly
toolchain, `make`, `perl` and the required Perl modules are present, and 78
with a JSON list of the exact missing items otherwise. `--help` never touches
the build.

## What `run` does

1. `Session.prepare()` verifies the archive sha256 and extracts a clean copy
   into `/workspace/src` (refuses non-empty src/build/install directories).
2. `Configure linux-x86_64 --prefix=<install> --openssldir=<install>/ssl --libdir=lib`
   in the empty build tree `/workspace/build`.
3. `make -j<BUILD_JOBS<=4> build_sw`.
4. `make list-tests` (official test inventory is preserved in `output/logs`).
5. `make HARNESS_JOBS=<TEST_JOBS<=2> TESTS="test_rsa test_dsa" test`
   (recorded as official TAP test evidence).
6. `make install_sw` and `make install_ssldirs` into `/workspace/output/install`.
7. Compiles `consumer.c` (outside src) against the new prefix and runs it:
   - EVP SHA-256 of `hello world` versus the known digest;
   - EVP RSA-SHA256 signature verification over a fresh key produced by the
     installed `openssl` binary (tampered message must fail);
   - a real local TLS handshake (`s_server`/`s_client` with a fresh
     self-signed cert, `-verify_return_error`);
   - `ldd` proves the consumer resolves `libcrypto` from the install prefix;
   - negative case: hiding the installed `libcrypto.so*` must make the
     consumer stop reporting the freshly built OpenSSL version — it can never
     accidentally fall back to a system library as the delivered target.
8. `Session.finish()` writes `install_manifest.json`, `install.tar.gz`,
   `commands.json`, `tests.json` and `run.json` under the output directory.

## Honest limitations

- No FIPS provider validation is claimed; only the default provider is used.
- The core profile deliberately limits official testing to the RSA and DSA
  source test recipes (`test_rsa test_dsa`); broader groups (`-99`, full
  `make test`) are out of scope for this profile.
- All work is offline and confined to `/workspace` and `/tmp`; no system
  OpenSSL library or binary is used as a delivered artifact.
- Timestamps/build IDs may cause non-functional byte differences; they are not
  treated as failures.
