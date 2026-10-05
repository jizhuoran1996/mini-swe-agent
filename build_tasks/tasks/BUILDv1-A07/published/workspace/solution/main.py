#!/usr/bin/env python3
"""BUILDv1-A07: build, test, install the libevent CORE profile (no TLS).

The source archive, ref and commit are read from the input manifest at
runtime; the frozen contract binds release-2.2.2-alpha. Core scope is
event_core + event_extra + event_pthreads (shared and static), with TLS
explicitly disabled (OpenSSL and MbedTLS OFF).

The entire upstream test suite is executed exactly once via CTest after a
ctest -N inventory. Every configure/build/inventory/test/install/consumer
command goes through buildkit.Session so real logs, exit codes and CTest
summaries are preserved. Failing upstream cases are recorded verbatim in
tests.json; they are never skipped, filtered or rewritten.
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from buildkit import Session, digest

SOLUTION_DIR = Path(__file__).resolve().parent
CORE_TOOLS = ("cmake", "cc", "make", "python3")
CTEST_SUMMARY_RE = re.compile(
    r"(\d+)% tests passed,\s*(\d+) tests failed out of (\d+)")
UNITTEST_SUMMARY_RE = re.compile(r"Ran (\d+) tests?")


def progress(msg):
    print("[BUILDv1-A07] " + msg, flush=True)


def doctor(input_dir):
    """List exact missing source/tool/dependency items; 78 if missing, 0 if ready."""
    missing = []
    idir = Path(input_dir)
    manifest_path = idir / "manifest.json"
    manifest = None
    if not manifest_path.is_file():
        missing.append("source manifest: " + str(manifest_path))
    else:
        try:
            manifest = json.loads(manifest_path.read_text())
        except ValueError as exc:
            missing.append("source manifest unreadable: " + str(exc))
    if manifest:
        src = manifest.get("source", {})
        archive = idir / str(src.get("filename", "source.tar.gz"))
        if not archive.is_file():
            missing.append("source archive: " + str(archive))
        else:
            expected = src.get("sha256")
            if expected and digest(archive) != expected:
                missing.append("source archive sha256 mismatch: " + str(archive))
    for tool in CORE_TOOLS:
        if shutil.which(tool) is None:
            missing.append("tool: " + tool)
    if missing:
        for item in missing:
            print("missing: " + item, flush=True)
        return 78
    print("doctor: ready (source archive + tools: " + ", ".join(CORE_TOOLS) + ")",
          flush=True)
    return 0


def _record_ctest_failure(sess, log_path, exit_code):
    """Persist the real CTest log/exit code when ctest exited non-zero.

    Session.test() raises on a non-zero underlying ctest exit, so the caller
    catches that and calls this to guarantee the failing run is still present
    in tests.json with `failed: true` and a non-null raw log.
    """
    text = log_path.read_text(errors="replace") if log_path.exists() else ""
    parsed = None
    unit = None
    match = CTEST_SUMMARY_RE.search(text)
    if match:
        parsed = int(match.group(3))
        unit = "ctest_cases"
    else:
        match = UNITTEST_SUMMARY_RE.search(text)
        if match:
            parsed = int(match.group(1))
            unit = "unittest_cases"
    sess.tests.append({
        "selector": "ctest",
        "command_index": len(sess.commands) - 1,
        "exit_code": exit_code,
        "parsed_count": parsed,
        "count_unit": unit,
        "raw_log": str(log_path.relative_to(sess.output)),
        "nonempty_log": bool(text.strip()),
        "log_sha256": digest(log_path) if log_path.exists() else None,
        "failed": True,
    })
    sess.write("tests.json", sess.tests)


def run_ctest_once(sess, build):
    """Execute the full upstream suite exactly once. Return (all_passed, log_path)."""
    step_jobs = max(1, min(2, sess.jobs))
    argv = ["ctest", "--test-dir", str(build), "--output-on-failure",
            "-j", str(step_jobs)]
    try:
        log = sess.test("ctest", argv, cwd=build, parser="auto", timeout=7200)
        return True, log
    except RuntimeError:
        last = sess.commands[-1]
        log_path = sess.output / last["log"]
        if not any(t.get("selector") == "ctest" for t in sess.tests):
            _record_ctest_failure(sess, log_path, last.get("exit_code", 1))
        return False, log_path


def build_and_run_consumer(sess, install):
    """Compile and run the independent C consumer against the fresh install."""
    consumer_bin = sess.consumer / "event_consumer"
    sess.run([
        "cc", "-O2", "-Wall", "-Wextra",
        "-I" + str(install / "include"),
        str(SOLUTION_DIR / "consumer.c"),
        "-L" + str(install / "lib"),
        "-Wl,-rpath," + str(install / "lib"),
        "-levent_pthreads", "-levent_extra", "-levent_core",
        "-lpthread",
        "-o", str(consumer_bin),
    ], cwd=sess.consumer, phase="consumer_build", name="consumer_build", timeout=600)
    log = sess.run([str(consumer_bin)], cwd=sess.consumer, phase="consumer_run",
                   name="consumer_run",
                   env={"LD_LIBRARY_PATH": str(install / "lib")},
                   timeout=180)
    text = log.read_text(errors="replace")
    if "CONSUMER_OK" not in text:
        raise RuntimeError("consumer did not report CONSUMER_OK")
    return consumer_bin


def do_run(args):
    sess = Session(args.input, args.output, args.jobs)
    progress("preparing source archive")
    src = sess.prepare()
    build = sess.build
    install = sess.install

    progress("configure")
    sess.run([
        "cmake", "-S", str(src), "-B", str(build),
        "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_INSTALL_PREFIX=" + str(install),
        "-DEVENT__LIBRARY_TYPE=BOTH",
        "-DEVENT__DISABLE_TESTS=OFF",
        "-DEVENT__DISABLE_SAMPLES=OFF",
        "-DEVENT__DISABLE_BENCHMARK=ON",
        "-DEVENT__DISABLE_REGRESS=OFF",
        "-DEVENT__DISABLE_OPENSSL=ON",
        "-DEVENT__DISABLE_MBEDTLS=ON",
    ], cwd=src, phase="configure", name="cmake_configure", timeout=1800)

    progress("build (-j %d)" % sess.jobs)
    sess.run(["cmake", "--build", str(build), "--parallel", str(sess.jobs)],
             cwd=build, phase="build", name="cmake_build", timeout=3600)

    progress("ctest inventory")
    inv = sess.run(["ctest", "--test-dir", str(build), "-N"],
                   cwd=build, phase="inventory", name="ctest_inventory", timeout=300)
    match = re.search(r"Total Tests:\s*(\d+)", inv.read_text(errors="replace"))
    discovered = int(match.group(1)) if match else 0
    if discovered == 0:
        raise RuntimeError("ctest -N reported zero tests; upstream suite missing")
    progress("discovered %d upstream tests" % discovered)

    progress("running full upstream suite (single pass, no reruns)")
    tests_passed, _ = run_ctest_once(sess, build)
    progress("upstream tests all_passed=%s" % tests_passed)

    progress("install")
    sess.run(["cmake", "--install", str(build)],
             cwd=build, phase="install", name="cmake_install", timeout=1800)

    libs = sorted(p.name for p in (install / "lib").glob("libevent*"))
    headers = sorted(p.name for p in (install / "include" / "event2").glob("*.h"))
    if not libs or not headers:
        raise RuntimeError("install incomplete: libs=%s headers=%d" % (libs, len(headers)))
    progress("installed %d libs, %d headers" % (len(libs), len(headers)))

    progress("consumer compile + run")
    build_and_run_consumer(sess, install)

    sess.finish(features={
        "profile": "core",
        "source_ref": sess.manifest["source"].get("release_ref"),
        "source_commit": sess.manifest["source"].get("commit"),
        "components": ["event_core", "event_extra", "event_pthreads"],
        "tls": False,
        "openssl": "disabled",
        "mbedtls": "disabled",
        "library_type": "BOTH",
        "ctest_discovered": discovered,
        "ctest_all_passed": tests_passed,
        "installed_libs": libs,
        "installed_event2_header_count": len(headers),
        "consumer": "bufferevent_pair + timer + pthreads, no TLS",
        "consumer_ok": True,
    })
    progress("done")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="BUILDv1-A07 libevent core-profile builder (no TLS)")
    sub = parser.add_subparsers(dest="command")
    runner = sub.add_parser("run", help="build, test, install and consume libevent")
    runner.add_argument("--input", required=True)
    runner.add_argument("--output", required=True)
    runner.add_argument("--jobs", type=int, default=4)
    doc = sub.add_parser("doctor", help="report missing source/tool/dependency items")
    doc.add_argument("--input", required=True)
    args = parser.parse_args(argv)
    if args.command == "run":
        return do_run(args)
    if args.command == "doctor":
        return doctor(args.input)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
