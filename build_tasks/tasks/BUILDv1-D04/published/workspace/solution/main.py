#!/usr/bin/env python3
"""BUILDv1-D04 (core profile): build the RocksDB static SDK from source, run the

official db_basic_test suite, install headers/library and verify an out-of-tree
static consumer that writes, reopens, reads and deletes keys across processes.

All build/install/test/consumer commands go through buildkit.Session so that logs
and exit codes are preserved as evidence.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

import buildkit

TASK_ID = "BUILDv1-D04"
PROJECT = "RocksDB"
PROFILE = "core"
REQUIRED_TOOLS = ("make", "g++", "cc", "ar")
COMPRESSION_HEADERS = ("snappy.h", "zlib.h", "lz4.h", "zstd.h", "bzlib.h")
TEST_BINARIES = ("db_basic_test",)
COMPRESSION_LIBS = ("-lz", "-lsnappy", "-llz4", "-lzstd", "-lbz2")
BASE_LIBS = ("-lpthread", "-ldl", "-lrt")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def find_header(name: str):
    for root in ("/usr/include", "/usr/local/include"):
        candidate = Path(root) / name
        if candidate.exists():
            return str(candidate)
    return None


def gtest_inventory(text: str):
    """Turn `--gtest_list_tests` output into fully-qualified test names."""
    names, suite = [], None
    for raw in text.splitlines():
        if not raw.strip():
            continue
        if not raw.startswith((" ", "\t")):
            suite = raw.strip()
            continue
        if suite is None:
            continue
        names.append(suite + raw.split()[0])
    return names


def platform_link_libs(src: Path):
    """Harvest the -l flags the RocksDB Makefile recorded in make_config.mk."""
    tokens = []
    config = src / "make_config.mk"
    if config.is_file():
        for line in config.read_text(errors="replace").splitlines():
            line = line.strip()
            if line.startswith(("PLATFORM_LDFLAGS", "PLATFORM_LIBS")):
                _, _, value = line.partition("=")
                tokens.extend(t for t in value.split() if re.fullmatch(r"-l\S+", t))
    return merge(tokens, BASE_LIBS)


def merge(*sequences):
    ordered = []
    for sequence in sequences:
        for token in sequence:
            if token not in ordered:
                ordered.append(token)
    return ordered


def link_candidates(src: Path):
    parsed = platform_link_libs(src)
    return [parsed, merge(parsed, COMPRESSION_LIBS), merge(BASE_LIBS, COMPRESSION_LIBS)]


# --------------------------------------------------------------------------- #
# doctor
# --------------------------------------------------------------------------- #
def doctor(input_dir):
    input_dir = Path(input_dir)
    problems, notes = [], []

    manifest_path = input_dir / "manifest.json"
    manifest = None
    if not manifest_path.is_file():
        problems.append(f"missing input manifest: {manifest_path}")
    else:
        try:
            manifest = json.loads(manifest_path.read_text())
        except Exception as exc:  # noqa: BLE001 - report exactly what is wrong
            problems.append(f"unreadable input manifest {manifest_path}: {exc}")

    if manifest is not None:
        source = manifest.get("source") or {}
        archive = input_dir / str(source.get("filename", ""))
        if not source.get("filename"):
            problems.append("manifest does not declare source.filename")
        elif not archive.is_file():
            problems.append(f"missing source archive: {archive}")
        elif buildkit.digest(archive) != source.get("sha256"):
            problems.append(f"source archive sha256 mismatch: {archive}")
        else:
            notes.append(
                f"source archive ok: {archive.name} ({archive.stat().st_size} bytes, sha256 verified)"
            )

    for tool in REQUIRED_TOOLS:
        resolved = shutil.which(tool)
        if resolved is None:
            problems.append(f"missing tool: {tool}")
        else:
            notes.append(f"tool {tool}: {resolved}")

    for directory in ("/workspace", "/tmp"):
        if not os.access(directory, os.W_OK):
            problems.append(f"not writable: {directory}")

    for header in COMPRESSION_HEADERS:
        found = find_header(header)
        if found:
            notes.append(f"dependency header {header}: {found}")
        else:
            notes.append(
                f"optional dependency header {header}: not found "
                "(RocksDB auto-detects and builds without it)"
            )

    print(f"doctor for {TASK_ID} ({PROJECT}, profile={PROFILE})")
    print(f"input directory: {input_dir}")
    for note in notes:
        print(f"  ok      : {note}")
    for problem in problems:
        print(f"  MISSING : {problem}")
    if problems:
        print(f"doctor: NOT READY ({len(problems)} blocking item(s))")
        return 78
    print("doctor: READY")
    return 0


# --------------------------------------------------------------------------- #
# build / install / verify
# --------------------------------------------------------------------------- #
def install_targets(src: Path):
    makefile = (src / "Makefile").read_text(errors="replace")
    found = set(re.findall(r"^(install[A-Za-z0-9_]*(?:-[A-Za-z0-9_]+)?)\s*:", makefile, re.M))
    static = next((n for n in ("install-static", "install_static") if n in found), None)
    headers = next((n for n in ("install-headers", "install_headers") if n in found), None)
    if static:
        return [t for t in (headers, static) if t]
    if "install" in found:
        return ["install"]
    return ["install-headers", "install-static"]


def link_consumer(sess, env, cxx, link_prefix, candidates):
    for index, extra in enumerate(candidates):
        sess.run(
            link_prefix + list(extra),
            cwd=sess.consumer,
            phase="consumer_build",
            name=f"consumer_static_link_{index}",
            env=env,
            timeout=1800,
            check=False,
        )
        if sess.commands[-1]["exit_code"] == 0:
            return extra
    raise RuntimeError("static consumer link failed for every candidate library set")


def run(args):
    sess = buildkit.Session(args.input, args.output, args.jobs)
    sess.prepare()
    src, install, consumer = sess.src, sess.install, sess.consumer

    test_tmp = sess.build / "test_tmp"
    test_tmp.mkdir(parents=True, exist_ok=True)
    env = {"CC": "gcc", "CXX": "g++", "TEST_TMPDIR": str(test_tmp)}
    jobs = str(sess.jobs)

    sess.run(
        ["make", "-j", jobs, "DEBUG_LEVEL=0", "static_lib", *TEST_BINARIES],
        cwd=src,
        phase="build",
        name="build_static_lib_and_tests",
        env=env,
        timeout=7200,
    )

    # 1. official discovery first, so the executed set is pinned before running.
    for binary in TEST_BINARIES:
        log = sess.run(
            [f"./{binary}", "--gtest_list_tests"],
            cwd=src,
            phase="discovery",
            name=f"list_{binary}",
            env=env,
            timeout=900,
        )
        names = gtest_inventory(log.read_text(errors="replace"))
        sess.write(
            f"discovery_{binary}.json",
            {"binary": binary, "task_id": TASK_ID, "discovered": len(names), "tests": names},
        )
        if not names:
            raise RuntimeError(f"official discovery found no tests in {binary}")

    for binary in TEST_BINARIES:
        sess.test(binary, [f"./{binary}"], cwd=src, parser="gtest_cases", env=env, timeout=5400)

    # 2. install the static SDK with the project's own install targets.
    chosen = install_targets(src)
    sess.run(
        ["make", "DEBUG_LEVEL=0", f"PREFIX={install}", *chosen],
        cwd=src,
        phase="install",
        name="install_static_sdk",
        env=env,
        timeout=1800,
        check=False,
    )
    static_lib = install / "lib" / "librocksdb.a"
    header = install / "include" / "rocksdb" / "db.h"
    if not static_lib.is_file() or not header.is_file():
        # Documented fallback: the upstream install target did not place files.
        (install / "lib").mkdir(parents=True, exist_ok=True)
        if (src / "librocksdb.a").is_file():
            shutil.copy2(src / "librocksdb.a", static_lib)
        if (src / "include").is_dir():
            shutil.copytree(src / "include", install / "include", dirs_exist_ok=True)
        for pc in src.glob("*.pc"):
            shutil.copy2(pc, install / "lib" / pc.name)
    if not static_lib.is_file() or not header.is_file():
        raise RuntimeError("install step produced neither librocksdb.a nor rocksdb headers")

    # 3. build and run the out-of-tree consumer against the installed SDK only.
    source = Path(__file__).resolve().parent / "consumer.cc"
    consumer_src = consumer / "rocksdb_consumer.cc"
    shutil.copy2(source, consumer_src)
    binary = consumer / "rocksdb_consumer"
    cxx = shutil.which("g++") or "g++"
    link_prefix = [
        cxx, "-std=c++17", "-O2",
        "-I", str(install / "include"),
        str(consumer_src), str(static_lib), "-o", str(binary),
    ]
    link_consumer(sess, env, cxx, link_prefix, link_candidates(src))

    ldd_log = sess.run(
        ["ldd", str(binary)], cwd=consumer, phase="consumer_check",
        name="ldd_consumer", env=env, timeout=120, check=False,
    )
    if sess.commands[-1]["exit_code"] == 0 and "librocksdb" in ldd_log.read_text(errors="replace"):
        raise RuntimeError("consumer resolved a system librocksdb instead of the build artifact")

    dbdir = consumer / "db"
    shutil.rmtree(dbdir, ignore_errors=True)
    for name in ("write", "verify", "delete", "final"):
        sess.run(
            [str(binary), name, str(dbdir)],
            cwd=consumer,
            phase="consumer",
            name=f"consumer_{name}",
            env=env,
            timeout=600,
        )

    pc_files = sorted(p.name for p in install.rglob("*.pc"))
    sess.finish(
        features={
            "profile": PROFILE,
            "static_lib": True,
            "shared_lib": False,
            "db_basic_test": True,
            "table_test": False,
            "installed_headers": True,
            "pkg_config_files": pc_files,
            "consumer_static_link": True,
            "consumer_reopen_verified": True,
        }
    )
    return 0


# --------------------------------------------------------------------------- #
def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="main.py",
        description=f"{TASK_ID}: build, install and verify a RocksDB static SDK ({PROJECT}).",
    )
    sub = parser.add_subparsers(dest="command")
    run_p = sub.add_parser("run", help="build, install, run official tests and verify a consumer")
    run_p.add_argument("--input", default="input", help="read-only input directory")
    run_p.add_argument("--output", default="output", help="writable output directory")
    run_p.add_argument("--jobs", type=int, default=4, help="build jobs (clamped to 4)")
    doc_p = sub.add_parser("doctor", help="report missing source/tool/dependency items")
    doc_p.add_argument("--input", default="input", help="read-only input directory")

    args = parser.parse_args(argv)
    if args.command == "run":
        return run(args)
    if args.command == "doctor":
        return doctor(args.input)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
