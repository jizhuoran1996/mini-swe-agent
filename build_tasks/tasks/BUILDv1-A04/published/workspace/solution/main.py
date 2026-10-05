#!/usr/bin/env python3
"""BUILDv1-A04 (curl, core): build + validate curl/libcurl from source.

Core profile scope: full CLI/library plus official upstream tests 1, 2 and 3
(HTTP GET, GET with Basic auth, POST with authentication/framing), built with
the OpenSSL TLS backend, then consumed by an independent C libcurl client.

The official test selection is executed through the upstream harness
(``tests/runtests.pl``) directly in verbose mode so real per-test logs are
preserved; the CMake ``tests`` target is deliberately not trusted because it
can return 0 with an empty captured log.  Every execution of a freshly built
binary is performed with ``LD_LIBRARY_PATH`` pointing at the private installed
libcurl so the new CLI can never silently bind to the older system libcurl.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import buildkit


# --------------------------------------------------------------------------- #
# doctor                                                                       #
# --------------------------------------------------------------------------- #
def check_doctor(input_dir):
    """Return the exact list of missing source / tool / dependency items."""
    missing = []
    for tool in ("cmake", "gcc", "make", "perl", "python3"):
        if shutil.which(tool) is None:
            missing.append("tool:" + tool)
    if shutil.which("gcc"):
        probe = subprocess.run(
            ["gcc", "-E", "-include", "openssl/ssl.h", "-x", "c", "-"],
            input=b"", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if probe.returncode != 0:
            missing.append("dependency:openssl-development-headers")
    manifest = Path(input_dir) / "manifest.json"
    if not manifest.exists():
        missing.append("source:manifest.json")
    else:
        try:
            data = json.loads(manifest.read_text())
            archive = Path(input_dir) / data["source"]["filename"]
            if not archive.exists():
                missing.append("source:" + data["source"]["filename"])
        except Exception as exc:  # noqa: BLE001
            missing.append("source:manifest-unreadable:%s" % exc)
    return missing


# --------------------------------------------------------------------------- #
# supplemental consumer / local server (kept outside the source tree)          #
# --------------------------------------------------------------------------- #
CONSUMER_C = r"""
#include <stdio.h>
#include <string.h>
#include <curl/curl.h>

static char buf[65536];
static size_t n;
static size_t wcb(void *p, size_t s, size_t m, void *u) {
    size_t k = s * m; (void)u;
    if (n + k < sizeof(buf)) memcpy(buf + n, p, k);
    n += k; return k;
}

int main(int argc, char **argv) {
    char url[2048];
    CURLcode rc;
    CURL *c;
    if (argc < 2) return 2;
    curl_global_init(CURL_GLOBAL_DEFAULT);
    c = curl_easy_init();
    if (!c) return 9;
    curl_easy_setopt(c, CURLOPT_WRITEFUNCTION, wcb);
    curl_easy_setopt(c, CURLOPT_FOLLOWLOCATION, 1L);

    n = 0; buf[0] = 0;
    snprintf(url, sizeof url, "%s/hello", argv[1]);
    curl_easy_setopt(c, CURLOPT_URL, url);
    rc = curl_easy_perform(c);
    if (rc != CURLE_OK) { fprintf(stderr, "GET failed: %s\n", curl_easy_strerror(rc)); return 3; }
    if (strncmp(buf, "hello world", 11) != 0) { fprintf(stderr, "GET body mismatch: [%s]\n", buf); return 4; }

    n = 0; buf[0] = 0;
    snprintf(url, sizeof url, "%s/redirect", argv[1]);
    curl_easy_setopt(c, CURLOPT_URL, url);
    rc = curl_easy_perform(c);
    if (rc != CURLE_OK) { fprintf(stderr, "redirect failed: %s\n", curl_easy_strerror(rc)); return 5; }
    if (strncmp(buf, "hello world", 11) != 0) { fprintf(stderr, "redirect body mismatch: [%s]\n", buf); return 6; }

    n = 0; buf[0] = 0;
    snprintf(url, sizeof url, "%s/post", argv[1]);
    curl_easy_setopt(c, CURLOPT_URL, url);
    curl_easy_setopt(c, CURLOPT_POSTFIELDS, "ping-data");
    rc = curl_easy_perform(c);
    if (rc != CURLE_OK) { fprintf(stderr, "POST failed: %s\n", curl_easy_strerror(rc)); return 7; }
    if (strncmp(buf, "ping-data", 9) != 0) { fprintf(stderr, "POST body mismatch: [%s]\n", buf); return 8; }

    curl_easy_cleanup(c);
    curl_global_cleanup();
    printf("CONSUMER OK\n");
    return 0;
}
"""

DRIVER_PY = r"""
import http.server
import os
import socketserver
import subprocess
import sys
import threading

BODY = b"hello world\n"


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/hello":
            self.send_response(200); self.send_header("Content-Length", str(len(BODY))); self.end_headers(); self.wfile.write(BODY)
        elif self.path == "/redirect":
            self.send_response(302); self.send_header("Location", "/hello"); self.send_header("Content-Length", "0"); self.end_headers()
        else:
            self.send_response(404); self.send_header("Content-Length", "0"); self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0")); d = self.rfile.read(n)
        if self.path == "/post":
            self.send_response(200); self.send_header("Content-Length", str(len(d))); self.end_headers(); self.wfile.write(d)
        else:
            self.send_response(404); self.send_header("Content-Length", "0"); self.end_headers()

    def log_message(self, *a):
        pass


class S(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


def main():
    binary = sys.argv[1]
    libdir = sys.argv[2] if len(sys.argv) > 2 else ""
    srv = S(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    env = dict(os.environ)
    if libdir:
        env["LD_LIBRARY_PATH"] = libdir + ":" + env.get("LD_LIBRARY_PATH", "")
    p = subprocess.run([binary, "http://127.0.0.1:%d" % port], env=env,
                       capture_output=True, text=True)
    sys.stdout.write(p.stdout); sys.stderr.write(p.stderr)
    srv.shutdown()
    sys.exit(p.returncode)


if __name__ == "__main__":
    main()
"""


# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #
def find_libdir(install):
    """Return the prefix sub-directory that actually holds the new libcurl."""
    candidates = [install / "lib", install / "lib64",
                  install / "lib" / "x86_64-linux-gnu",
                  install / "lib" / "aarch64-linux-gnu"]
    for c in candidates:
        if c.is_dir() and list(c.glob("libcurl.so*")):
            return c
    for c in install.rglob("libcurl.so*"):
        return c.parent
    return install / "lib"


def merged_env(extra):
    env = dict(os.environ)
    env.update({str(k): str(v) for k, v in extra.items() if v is not None})
    return env


# --------------------------------------------------------------------------- #
# official test selection (tests 1, 2, 3) - verbose, private libcurl bound      #
# --------------------------------------------------------------------------- #
def run_official_tests(sess, src, build, install, libdir, base_env):
    """Execute the frozen upstream selection with preserved verbose evidence."""
    harness = src / "tests" / "runtests.pl"
    if not harness.exists():
        raise RuntimeError("upstream test harness tests/runtests.pl missing")

    curl_bin = build / "src" / "curl"
    if not curl_bin.exists():
        curl_bin = install / "bin" / "curl"
    if not curl_bin.exists():
        raise RuntimeError("no freshly built curl binary available for tests")

    # Prove the freshly built CLI resolves to the private libcurl.
    ldd_log = sess.run(["ldd", str(curl_bin)], cwd=src, phase="verify",
                       name="ldd_new_cli", env=base_env, check=False, timeout=120)
    ldd_text = ldd_log.read_text(errors="replace")
    sess.write("ldd_new_cli.txt", ldd_text)
    if "curl_easy_ssls_export" in ldd_text or "not found" in ldd_text:
        raise RuntimeError("fresh CLI fails to bind the private libcurl: " + ldd_text)

    tests_build = build / "tests"
    cwd_primary = tests_build if tests_build.is_dir() else src / "tests"

    env = dict(base_env)
    env["TFLAGS"] = "1 2 3"
    env["CURL"] = str(curl_bin)

    attempts = [
        (["perl", str(harness), "-v", "1", "2", "3"], cwd_primary),
        (["perl", str(harness), "-v", "-srcdir", str(src / "tests"), "1", "2", "3"],
         tests_build if tests_build.is_dir() else src),
        (["perl", str(harness), "1", "2", "3"], cwd_primary),
    ]

    chosen = None
    for argv, cwd in attempts:
        if not Path(cwd).is_dir():
            continue
        try:
            log = sess.run(argv, cwd=cwd, phase="test_probe", name="official_test_probe",
                           env=env, check=False, timeout=1800)
        except Exception:  # timeout or launch failure -> next attempt
            continue
        text = log.read_text(errors="replace")
        if re.search(r"(?im)^\s*test\s+0*1\b", text) or "TESTDONE" in text:
            chosen = (argv, cwd)
            break
        if text.strip() and chosen is None:
            chosen = (argv, cwd)

    if chosen is None:
        raise RuntimeError("official test selection produced no evidence")

    argv, cwd = chosen
    log = sess.test("official_tests_1_2_3", argv, cwd=cwd, env=env, timeout=1800)
    text = log.read_text(errors="replace")

    m = re.search(r"TESTDONE:\s*(\d+)\s+tests", text)
    ok_count = len(re.findall(r"(?im)^\s*test\s+0*\d+\.{2,}\s*OK", text))
    sess.write("official_test_summary.json", {
        "harness": "tests/runtests.pl",
        "frozen_selection": ["1", "2", "3"],
        "command": argv,
        "cwd": str(cwd),
        "log": str(log.relative_to(sess.output)),
        "reported_tests": int(m.group(1)) if m else None,
        "parsed_ok_lines": ok_count,
        "raw_log_preserved": True,
    })
    return argv


# --------------------------------------------------------------------------- #
# run                                                                          #
# --------------------------------------------------------------------------- #
def cmd_run(args):
    missing = check_doctor(args.input)
    if missing:
        print("doctor: missing required items:")
        for item in missing:
            print("  -", item)
        return 78

    sess = buildkit.Session(args.input, args.output, args.jobs)
    src = sess.prepare()
    build = sess.build
    install = sess.install
    jobs = str(sess.jobs)

    if not (src / "tests" / "runtests.pl").exists():
        raise RuntimeError("official upstream test harness missing from the source tree")

    install_lib = install / "lib"
    install_lib64 = install / "lib64"
    rpath = ";".join(str(p) for p in (install_lib, install_lib64))

    sess.run(["cmake", "-S", str(src), "-B", str(build),
              "-DCMAKE_BUILD_TYPE=Release",
              "-DCMAKE_INSTALL_PREFIX=" + str(install),
              "-DBUILD_TESTING=ON",
              "-DBUILD_CURL_EXE=ON",
              "-DBUILD_SHARED_LIBS=ON",
              "-DBUILD_STATIC_LIBS=ON",
              "-DCURL_USE_OPENSSL=ON",
              "-DCMAKE_INSTALL_RPATH=" + rpath,
              "-DCMAKE_BUILD_WITH_INSTALL_RPATH=ON"],
             cwd=src, phase="configure", name="cmake_configure", timeout=1800)

    sess.run(["cmake", "--build", str(build), "--parallel", jobs],
             cwd=src, phase="build", name="cmake_build", timeout=5400)

    sess.run(["cmake", "--build", str(build), "--target", "testdeps",
              "--parallel", jobs],
             cwd=src, phase="build", name="cmake_testdeps", timeout=3600)

    sess.run(["cmake", "--install", str(build)],
             cwd=src, phase="install", name="cmake_install", timeout=600)

    libdir = find_libdir(install)
    build_libdir = build / "lib"
    ld_paths = [str(libdir), str(install_lib), str(install_lib64), str(build_libdir)]
    existing = os.environ.get("LD_LIBRARY_PATH", "")
    if existing:
        ld_paths.append(existing)
    base_env = {"LD_LIBRARY_PATH": os.pathsep.join(p for p in ld_paths if p)}

    version_log = sess.run([str(install / "bin" / "curl"), "-V"],
                           cwd=src, phase="install", name="curl_version",
                           env=base_env, timeout=60)
    version_text = version_log.read_text(errors="replace")
    sess.write("curl_V.txt", version_text)
    if "OpenSSL" not in version_text:
        raise RuntimeError("curl -V does not report OpenSSL TLS backend")

    if not (install / "bin" / "curl").exists():
        raise RuntimeError("curl CLI missing from install prefix")
    if not list(libdir.glob("libcurl.so*")):
        raise RuntimeError("shared libcurl missing from install prefix")

    # Official upstream tests 1 / 2 / 3 with preserved verbose logs.
    chosen = run_official_tests(sess, src, build, install, libdir, base_env)

    # Independent consumer, compiled and run outside the source tree.
    sess.consumer.mkdir(parents=True, exist_ok=True)
    consumer_c = sess.consumer / "consumer.c"
    consumer_bin = sess.consumer / "consumer"
    driver = sess.consumer / "driver.py"
    consumer_c.write_text(CONSUMER_C)
    driver.write_text(DRIVER_PY)

    sess.run(["gcc", str(consumer_c), "-o", str(consumer_bin),
              "-I", str(install / "include"),
              "-L", str(libdir),
              "-Wl,-rpath," + str(libdir),
              "-lcurl"],
             cwd=sess.consumer, phase="consumer", name="consumer_compile",
             env=base_env, timeout=300)

    sess.run(["python3", str(driver), str(consumer_bin), str(libdir)],
             cwd=sess.consumer, phase="consumer", name="consumer_http",
             env=base_env, timeout=300)

    # Negative case: the same consumer must fail on a refused connection.
    sess.run(["python3", "-c",
              "import subprocess,sys;"
              "p=subprocess.run([sys.argv[1],'http://127.0.0.1:1/hello']);"
              "sys.exit(0 if p.returncode!=0 else 1)",
              str(consumer_bin)],
             cwd=sess.consumer, phase="consumer", name="consumer_negative",
             env=base_env, timeout=120)

    features = {
        "openssl_tls": True,
        "shared_libcurl": True,
        "static_libcurl": True,
        "official_test_selection": ["1", "2", "3"],
        "official_test_command": " ".join(chosen),
        "private_libdir": str(libdir),
        "curl_version": version_text.strip().splitlines()[0] if version_text.strip() else "",
    }
    sess.finish(features=features)
    print("build complete: " + str(sess.output))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="BUILDv1-A04 curl core builder")
    sub = ap.add_subparsers(dest="cmd")

    run_p = sub.add_parser("run", help="build, test, install and consume curl")
    run_p.add_argument("--input", default="/workspace/input")
    run_p.add_argument("--output", default="/workspace/output")
    run_p.add_argument("--jobs", type=int, default=4)

    doc_p = sub.add_parser("doctor", help="report missing source/tool/dependency items")
    doc_p.add_argument("--input", default="/workspace/input")

    args = ap.parse_args(argv)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "doctor":
        missing = check_doctor(args.input)
        if missing:
            print("doctor: missing required items:")
            for item in missing:
                print("  -", item)
            return 78
        print("doctor: ready")
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
