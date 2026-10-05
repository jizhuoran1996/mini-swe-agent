#!/usr/bin/env python3
"""BUILDv1-A09 - build/test/install the nghttp2 C library (frozen CORE profile).

CORE scope (per the frozen contract, NOT the reference profile):
  * full libnghttp2 C library
  * shared + static artifacts
  * official main and failmalloc upstream test targets

Applications (nghttp/nghttpd/nghttpx/h2load), HPACK tools and examples are
intentionally out of scope for core and are configured OFF.

doctor verifies the frozen inputs and reports the exact missing
source/tool/dependency items, exiting 78 when anything is missing. run
refuses to build on a not-ready input set so a missing dependency can never be
silently downgraded to a skip.
"""
import argparse
import shutil
import sys
import tarfile
from pathlib import Path

from buildkit import Session
import buildkit

REQUIRED_TOOLS = ["cmake", "make", "cc", "ar"]
REQUIRED_SOURCE = [
    "CMakeLists.txt",
    "CMakeOptions.txt",
    "lib/CMakeLists.txt",
    "lib/includes/nghttp2/nghttp2.h",
    "tests/CMakeLists.txt",
    "tests/munit/munit.c",
    "tests/munit/munit.h",
]

HPACK_CONSUMER = '''#include <nghttp2/nghttp2.h>
#include <stdio.h>
#include <string.h>

static int fail(const char *what, int rv) {
  fprintf(stderr, "FAIL %s: %s\\n", what, nghttp2_strerror(rv));
  return 1;
}

int main(void) {
  nghttp2_hd_deflater *deflater = NULL;
  nghttp2_hd_inflater *inflater = NULL;
  nghttp2_nv nva[] = {
      {(uint8_t *)":method", (uint8_t *)"GET", 7, 3, NGHTTP2_NV_FLAG_NONE},
      {(uint8_t *)":scheme", (uint8_t *)"http", 7, 4, NGHTTP2_NV_FLAG_NONE},
      {(uint8_t *)":path", (uint8_t *)"/index.html", 5, 11, NGHTTP2_NV_FLAG_NONE},
      {(uint8_t *)"user-agent", (uint8_t *)"nghttp2-core-consumer", 10, 21,
       NGHTTP2_NV_FLAG_NONE},
  };
  const size_t nvlen = sizeof(nva) / sizeof(nva[0]);
  uint8_t buf[4096];
  ssize_t outlen;
  size_t off = 0, seen = 0;
  int rv;

  rv = nghttp2_hd_deflate_new(&deflater, 4096);
  if (rv != 0) return fail("hd_deflate_new", rv);
  rv = nghttp2_hd_inflate_new(&inflater);
  if (rv != 0) return fail("hd_inflate_new", rv);

  if (nghttp2_hd_deflate_bound(deflater, nva, nvlen) > sizeof(buf)) {
    fprintf(stderr, "FAIL deflate bound exceeds buffer\\n");
    return 1;
  }
  outlen = nghttp2_hd_deflate_hd(deflater, buf, sizeof(buf), nva, nvlen);
  if (outlen < 0) return fail("hd_deflate_hd", (int)outlen);

  while (off < (size_t)outlen) {
    nghttp2_nv nv;
    int flags = 0;
    ssize_t consumed = nghttp2_hd_inflate_hd2(inflater, &nv, &flags, buf + off,
                                              (size_t)outlen - off, 1);
    if (consumed < 0) return fail("hd_inflate_hd2", (int)consumed);
    off += (size_t)consumed;
    if (flags & NGHTTP2_HD_INFLATE_EMIT) {
      if (seen >= nvlen) {
        fprintf(stderr, "FAIL extra emitted header\\n");
        return 1;
      }
      if (nv.namelen != nva[seen].namelen ||
          nv.valuelen != nva[seen].valuelen ||
          memcmp(nv.name, nva[seen].name, nv.namelen) != 0 ||
          memcmp(nv.value, nva[seen].value, nv.valuelen) != 0) {
        fprintf(stderr, "FAIL header %zu mismatch\\n", seen);
        return 1;
      }
      seen++;
    }
    if (flags & NGHTTP2_HD_INFLATE_FINAL) {
      nghttp2_hd_inflate_end_headers(inflater);
      break;
    }
    if (consumed == 0) break;
  }

  if (seen != nvlen) {
    fprintf(stderr, "FAIL header count %zu != %zu\\n", seen, nvlen);
    return 1;
  }

  nghttp2_hd_inflate_del(inflater);
  nghttp2_hd_deflate_del(deflater);
  printf("HPACK-ROUNDTRIP-OK headers=%zu encoded=%zd\\n", seen, outlen);
  return 0;
}
'''


def archive_paths(archive):
    paths = set()
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            parts = Path(member.name).parts
            if len(parts) > 1:
                paths.add(str(Path(*parts[1:])))
    return paths


def inspect(session):
    """Return (missing_items, detail) for the frozen core input set."""
    missing = []
    detail = {}
    manifest = session.manifest
    archive = session.input / manifest["source"]["filename"]
    if not archive.is_file():
        missing.append("source archive %s (expected %s)" % (archive, manifest["source"]["filename"]))
        return missing, detail
    actual = buildkit.digest(archive)
    detail["source_sha256"] = actual
    if actual != manifest["source"]["sha256"]:
        missing.append("source archive sha256 mismatch for %s" % archive)
        return missing, detail

    tools = {}
    for tool in REQUIRED_TOOLS:
        found = shutil.which(tool)
        tools[tool] = found
        if found is None:
            missing.append("build tool not found on PATH: %s" % tool)
    detail["tools"] = tools

    try:
        paths = archive_paths(archive)
    except tarfile.TarError as exc:
        missing.append("source archive is not a readable tar file: %s" % exc)
        return missing, detail
    detail["archive_entries"] = len(paths)

    for rel in REQUIRED_SOURCE:
        if rel in paths:
            continue
        if rel.startswith("tests/munit/"):
            missing.append(
                "tests/munit submodule content missing from source archive (%s); "
                "offline_dependencies_ready=false requires pre-acquired munit" % rel)
        else:
            missing.append("source path missing from archive: %s" % rel)
    return missing, detail


def do_doctor(args):
    session = Session(args.input, args.output, 1)
    missing, detail = inspect(session)
    session.write("doctor.json", {"ready": not missing, "missing": missing, "detail": detail})
    if missing:
        print("doctor: NOT READY (%d missing item(s))" % len(missing))
        for item in missing:
            print("  missing: %s" % item)
        return 78
    print("doctor: ready")
    return 0


def find_dirs(install):
    include = None
    lib = None
    for path in install.rglob("nghttp2/nghttp2.h"):
        include = path.parent.parent
        break
    for path in install.rglob("libnghttp2.so*"):
        lib = path.parent
        break
    return include, lib


def do_run(args):
    session = Session(args.input, args.output, args.jobs)
    missing, detail = inspect(session)
    session.write("doctor.json", {"ready": not missing, "missing": missing, "detail": detail})
    if missing:
        print("doctor: NOT READY - refusing to build (%d missing item(s))" % len(missing))
        for item in missing:
            print("  missing: %s" % item)
        return 78

    session.prepare()
    src, build, install = str(session.src), str(session.build), str(session.install)
    jobs = str(session.jobs)

    session.run([
        "cmake", "-S", src, "-B", build,
        "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_INSTALL_PREFIX=%s" % install,
        "-DENABLE_LIB_ONLY=ON",
        "-DBUILD_SHARED_LIBS=ON",
        "-DBUILD_STATIC_LIBS=ON",
        "-DBUILD_TESTING=ON",
        "-DENABLE_APP=OFF",
        "-DENABLE_HPACK_TOOLS=OFF",
        "-DENABLE_EXAMPLES=OFF",
        "-DENABLE_DOC=OFF",
        "-DENABLE_HTTP3=OFF",
        "-DENABLE_FAILMALLOC=ON",
    ], cwd=src, phase="configure", name="cmake_configure", timeout=1800)

    session.run(["cmake", "--build", build, "--parallel", jobs],
                cwd=build, phase="build", name="library_build", timeout=7200)

    session.run(["cmake", "--build", build, "--target", "main", "failmalloc",
                 "--parallel", jobs],
                cwd=build, phase="build", name="test_targets", timeout=3600)

    session.test("main",
                 ["ctest", "--test-dir", build, "-R", "^main$", "--output-on-failure", "-j", "2"],
                 cwd=build, timeout=5400)
    session.test("failmalloc",
                 ["ctest", "--test-dir", build, "-R", "failmalloc", "--output-on-failure", "-j", "2"],
                 cwd=build, timeout=5400)

    session.run(["cmake", "--install", build], cwd=build, phase="install",
                name="cmake_install", timeout=1800)

    csrc = session.consumer / "hpack_consumer.c"
    csrc.write_text(HPACK_CONSUMER)
    exe = session.consumer / "hpack_consumer"
    include, lib = find_dirs(session.install)
    if include is None or lib is None:
        raise RuntimeError("installed nghttp2 headers/library not found under %s" % install)
    cc = shutil.which("cc") or shutil.which("gcc") or "cc"
    session.run([cc, "-std=c11", "-O2", "-Wall", "-o", str(exe), str(csrc),
                 "-I%s" % include, "-L%s" % lib, "-lnghttp2", "-Wl,-rpath,%s" % lib],
                cwd=str(session.consumer), phase="consumer",
                name="hpack_consumer_build", timeout=600)
    session.run([str(exe)], cwd=str(session.consumer), phase="consumer",
                name="hpack_consumer_run", timeout=120)

    session.finish(features={
        "profile": "core",
        "library_only": True,
        "shared_library": True,
        "static_library": True,
        "official_tests": ["main", "failmalloc"],
        "consumer": "hpack_deflate_inflate_roundtrip",
    })
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="BUILDv1-A09 nghttp2 CORE-profile source builder")
    sub = parser.add_subparsers(dest="command")
    run = sub.add_parser("run", help="build, test, install and consume nghttp2")
    run.add_argument("--input", required=True)
    run.add_argument("--output", required=True)
    run.add_argument("--jobs", type=int, default=4)
    doc = sub.add_parser("doctor", help="report missing source/tool/dependency items")
    doc.add_argument("--input", required=True)
    doc.add_argument("--output", default="/workspace/output")
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return do_doctor(args)
    if args.command == "run":
        return do_run(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
