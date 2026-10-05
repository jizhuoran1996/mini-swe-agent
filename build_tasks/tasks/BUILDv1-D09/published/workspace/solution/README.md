# NGINX core HTTP build (proxy + SSI)

This is the CORE profile build of NGINX 1.28.0 from the frozen source archive.
It deliberately excludes TLS/SSL, HTTP/2, stream, and mail modules.

## Usage

```bash
python3 solution/main.py run --input input --output output --jobs 4
python3 solution/main.py doctor --input input
python3 solution/main.py --help
```

The `doctor` command lists missing source/tool/dependency items and exits
with code `78` if anything is missing, or `0` if ready.

## What is built

- `auto/configure --prefix=<output>/install`
- `make -j4`
- `make install`
- Official `nginx-tests` TAP files `proxy.t` and `ssi.t` via `prove -v -j2`
- A standalone Python consumer outside the source tree that starts the
  installed nginx in a private prefix, serves a static file, reverse-proxies
  to a local fixture upstream, checks a 404, and verifies graceful reload.

## Honest limitations

- This is the CORE profile: TLS/SSL (`ssl.t`, `--with-http_ssl_module`),
  HTTP/2, stream and mail are intentionally out of scope and are not built
  or tested here.
- The `nginx-tests` source tree must be present under `input/` either as a
  directory literally named `nginx-tests` or as a `nginx-tests*.tar.gz`
  archive. The builder does not download anything.
- PCRE (v1 or v2) and zlib development headers must be present; the doctor
  command reports them as missing if they are not.
- No privileged ports, system nginx, or global HOME changes are used.
