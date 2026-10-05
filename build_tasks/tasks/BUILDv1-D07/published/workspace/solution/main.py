#!/usr/bin/env python3
"""BUILDv1-D07 core driver: build and qualify the ClickHouse analytics toolset.

Core profile scope:
  * compile the full ``clickhouse`` monolith and the aggregated ``unit_tests_dbms``
    binary from the pinned source release that ships all CPU ``contrib/`` gitlink
    submodules (LLVM libc++, googletest, boost, fmt, protos/brotli/zstd/...),
  * run the official ``ColumnObject.*`` GoogleTest suite and capture its inventory,
  * stage the freshly built binary into a private install tree and consume it with
    a deterministic ``clickhouse local`` aggregate and JSON-column query.

The core profile deliberately does **not** start a persistent server/client.
No system ClickHouse and no prebuilt artifact is ever substituted: the delivered
binary is the one produced this session under ``$BUILD``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

TASK_ID = "BUILDv1-D07"
DEFAULT_INPUT = "/workspace/input"
DEFAULT_OUTPUT = "/workspace/output"

TOOL_ALIASES = {
    "cmake": ["cmake"],
    "ninja": ["ninja", "ninja-build"],
    "python3": ["python3", "python3.12", "python3.11"],
    "clang": ["clang", "clang-18", "clang-19", "clang-17"],
    "clang++": ["clang++", "clang++-18", "clang++-19", "clang++-17"],
    "ld.lld": ["ld.lld", "ld.lld-18", "ld.lld-19", "ld.lld-17"],
}

# Files that must exist inside the source bundle for a real CPU build.
REQUIRED_SOURCE = (
    "CMakeLists.txt",
    "cmake/tools.cmake",
    "contrib/CMakeLists.txt",
    "contrib/sysroot/README.md",
    "contrib/googletest/CMakeLists.txt",
    "contrib/boost/CMakeLists.txt",
    "contrib/zlib-ng/CMakeLists.txt",
    "contrib/openssl/CMakeLists.txt",
    "contrib/libarchive/CMakeLists.txt",
    "src/Columns/tests/gtest_column_object.cpp",
)

FILES_OF_INTEREST = ("CMakeLists.txt", "cmake/tools.cmake")
VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")
CMAKE_MIN_RE = re.compile(r"cmake_minimum_required\s*\(\s*VERSION\s+([0-9.]+)", re.I)
CLANG_MIN_RE = re.compile(r"CMAKE_CXX_COMPILER_VERSION\s+VERSION_LESS(?:_EQUAL)?\s+([0-9.]+)")


def sha256_file(path, chunk=8 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def probe(path):
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=20)
        lines = (out.stdout or out.stderr).strip().splitlines()
        return lines[0] if lines else ""
    except Exception as exc:  # pragma: no cover - diagnostic only
        return "<unavailable: %s>" % exc


def parse_version(text):
    if not text:
        return None
    m = VERSION_RE.search(text)
    if not m:
        return None
    return tuple(int(x) for x in m.groups() if x is not None)


def version_lt(a, b):
    n = max(len(a), len(b))
    a = tuple(a) + (0,) * (n - len(a))
    b = tuple(b) + (0,) * (n - len(b))
    return a < b


def scan_archive(archive, files_of_interest, required_paths):
    """One pass over the tar; return (contents of interesting files, missing required rel paths)."""
    remaining = set(required_paths)
    wanted = set(files_of_interest)
    contents = {}
    with tarfile.open(archive, "r:*") as tf:
        for member in tf:
            if not member.isfile():
                continue
            parts = member.name.split("/", 1)
            rel = parts[1] if len(parts) == 2 else member.name
            remaining.discard(rel)
            if rel in wanted:
                try:
                    fh = tf.extractfile(member)
                    if fh is not None:
                        contents[rel] = fh.read(1 << 20).decode(errors="replace")
                except Exception:
                    pass
    return contents, remaining


def resolve_path(p, fallback_root="/workspace"):
    p = Path(p)
    if p.exists():
        return p
    alt = Path(fallback_root) / p
    if alt.exists():
        return alt
    return p


def diagnose(input_dir):
    input_dir = Path(input_dir).resolve()
    missing = []
    found = {"tools": {}, "notes": []}

    manifest = None
    manifest_path = input_dir / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text())
            found["manifest"] = str(manifest_path)
        except Exception as exc:
            missing.append({"kind": "manifest", "item": str(manifest_path),
                            "reason": "unreadable: %s" % exc})
    else:
        missing.append({"kind": "manifest", "item": str(manifest_path),
                        "reason": "source manifest absent"})

    source = manifest.get("source", {}) if isinstance(manifest, dict) else {}
    filename = source.get("filename", "source-with-submodules.tar.gz")
    archive = input_dir / filename
    if not archive.is_file():
        candidates = sorted(input_dir.glob("*.tar.gz")) + sorted(input_dir.glob("*.tgz"))
        archive = candidates[0] if candidates else None

    cmake_min = None
    clang_min = None

    if archive is None:
        missing.append({"kind": "source", "item": filename,
                        "reason": "source archive absent under %s" % input_dir})
    else:
        found["archive"] = str(archive)
        want_sha = source.get("sha256") if isinstance(source, dict) else None
        got_sha = sha256_file(archive)
        found["archive_sha256"] = got_sha
        if want_sha and got_sha != want_sha:
            missing.append({"kind": "source", "item": str(archive),
                            "reason": "sha256 mismatch (manifest=%s actual=%s)" % (want_sha, got_sha)})
        try:
            contents, remaining = scan_archive(archive, FILES_OF_INTEREST, REQUIRED_SOURCE)
        except Exception as exc:
            contents, remaining = {}, set(REQUIRED_SOURCE)
            missing.append({"kind": "source", "item": str(archive),
                            "reason": "cannot read archive: %s" % exc})
        for rel in sorted(remaining):
            missing.append({"kind": "dependency", "item": rel,
                            "reason": "required source/submodule path absent from bundle"})
        top = contents.get("CMakeLists.txt")
        if top:
            m = CMAKE_MIN_RE.search(top)
            if m:
                cmake_min = m.group(1)
                found["cmake_minversion"] = cmake_min
        tools_text = contents.get("cmake/tools.cmake") or ""
        vers = CLANG_MIN_RE.findall(tools_text)
        if vers:
            clang_min = max(vers, key=lambda v: tuple(int(x) for x in v.split(".")))
            found["clang_minversion"] = clang_min

    for name, aliases in TOOL_ALIASES.items():
        path = None
        for cand in aliases:
            path = shutil.which(cand)
            if path:
                break
        entry = {"path": path, "aliases": list(aliases)}
        if path:
            entry["version"] = probe(path)
        found["tools"][name] = entry

    tools = found["tools"]

    if not tools["cmake"]["path"]:
        missing.append({"kind": "tool", "item": "cmake",
                        "reason": "not found on PATH (aliases: %s)" % ", ".join(TOOL_ALIASES["cmake"])})
    elif cmake_min:
        have = parse_version(tools["cmake"]["version"])
        want = tuple(int(x) for x in cmake_min.split("."))
        if have and version_lt(have, want):
            missing.append({"kind": "tool", "item": "cmake",
                            "reason": "CMake >= %s required by source, found %s"
                                      % (cmake_min, tools["cmake"]["version"])})

    if not tools["ninja"]["path"]:
        missing.append({"kind": "tool", "item": "ninja", "reason": "not found on PATH"})

    if not tools["python3"]["path"]:
        missing.append({"kind": "tool", "item": "python3", "reason": "not found on PATH"})

    for cc in ("clang", "clang++"):
        if not tools[cc]["path"]:
            missing.append({"kind": "tool", "item": cc,
                            "reason": "not found on PATH (aliases: %s)" % ", ".join(TOOL_ALIASES[cc])})
            continue
        if clang_min:
            have = parse_version(tools[cc]["version"])
            want = tuple(int(x) for x in clang_min.split("."))
            if have and version_lt(have, want):
                missing.append({"kind": "tool", "item": cc,
                                "reason": "Clang >= %s required by source, found %s"
                                          % (clang_min, tools[cc]["version"])})

    if not tools["ld.lld"]["path"]:
        found["notes"].append("ld.lld not found; using Clang default linker")

    return {"task_id": TASK_ID, "input_dir": str(input_dir),
            "ready": not missing, "missing": missing, "found": found}


def find_program(build_root, name, extra=()):
    for c in extra:
        if c.is_file():
            return c
    for c in (build_root / "src" / name, build_root / "programs" / name, build_root / name):
        if c.is_file():
            return c
    for m in sorted(build_root.rglob(name)):
        if m.is_file():
            return m
    return None


def _package(session, src, built):
    install = session.install
    bin_dir = install / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    dest = bin_dir / "clickhouse"
    shutil.copy2(built, dest)
    dest.chmod(0o755)
    for alias in ("clickhouse-client", "clickhouse-local", "clickhouse-server", "clickhouse-keeper"):
        link = bin_dir / alias
        if not link.exists():
            link.symlink_to("clickhouse")
    for name in ("LICENSE", "NOTICE"):
        extra = src / name
        if extra.is_file():
            shutil.copy2(extra, install / name)
    (install / "etc").mkdir(parents=True, exist_ok=True)
    return dest


def run_build(input_dir, output_dir, jobs):
    import buildkit  # trusted plumbing, supplied on PYTHONPATH

    report = diagnose(input_dir)
    if not report["ready"]:
        print(json.dumps(report, indent=2))
        print("doctor: %d missing item(s); refusing to build" % len(report["missing"]), file=sys.stderr)
        return 78

    jobs = max(1, min(int(jobs), 4))
    session = buildkit.Session(input_dir, output_dir, jobs)
    session.prepare()
    src, build = session.src, session.build

    tools = report["found"]["tools"]
    cmake = tools["cmake"]["path"]
    ninja = tools["ninja"]["path"]
    cc = tools["clang"]["path"]
    cxx = tools["clang++"]["path"]

    env = {"CC": cc, "CXX": cxx, "CMAKE_BUILD_PARALLEL_LEVEL": str(jobs)}

    session.run(
        [cmake, "-S", str(src), "-B", str(build), "-G", "Ninja",
         "-DCMAKE_MAKE_PROGRAM=" + ninja,
         "-DCMAKE_BUILD_TYPE=Release",
         "-DENABLE_TESTS=ON",
         "-DENABLE_RUST=OFF",
         "-DCMAKE_C_COMPILER=" + cc,
         "-DCMAKE_CXX_COMPILER=" + cxx,
         "-DCMAKE_C_FLAGS=-g0",
         "-DCMAKE_CXX_FLAGS=-g0"],
        cwd=str(src), phase="configure", name="cmake_configure", env=env, timeout=3600)

    session.run(
        [cmake, "--build", str(build), "--parallel", str(jobs),
         "--target", "clickhouse", "unit_tests_dbms"],
        cwd=str(build), phase="build", name="cmake_build", env=env, timeout=10800)

    unit = find_program(build, "unit_tests_dbms",
                        extra=(build / "src" / "unit_tests_dbms",))
    prog = find_program(build, "clickhouse",
                        extra=(build / "programs" / "clickhouse",))
    if unit is None:
        raise RuntimeError("unit_tests_dbms binary not produced under %s" % build)
    if prog is None:
        raise RuntimeError("clickhouse binary not produced under %s" % build)

    session.run([str(unit), "--gtest_list_tests", "--gtest_filter=ColumnObject.*"],
                cwd=str(build), phase="test_discovery", name="columnobject_list",
                env=env, timeout=900)
    session.test("ColumnObject.*", [str(unit), "--gtest_filter=ColumnObject.*"],
                 cwd=str(build), parser="gtest_cases", env=env, timeout=1800)

    dest = _package(session, src, prog)

    vlog = session.run([str(dest), "--version"], cwd=str(session.consumer),
                       phase="consumer", name="clickhouse_version", env=env, timeout=120)
    if "clickhouse" not in vlog.read_text(errors="replace").lower():
        raise RuntimeError("clickhouse --version did not report tool identity")

    qlog = session.run([str(dest), "local", "--query",
                        "SELECT sum(number) AS total, count() AS rows FROM numbers(1000)"],
                       cwd=str(session.consumer), phase="consumer",
                       name="clickhouse_local", env=env, timeout=300)
    qout = qlog.read_text(errors="replace")
    if "499500" not in qout or "1000" not in qout:
        raise RuntimeError("clickhouse local aggregate consumer mismatch: %s" % qout[:400])

    jlog = session.run([str(dest), "local", "--query",
                        "SELECT toJSONString(map('k', 42)) AS j"],
                       cwd=str(session.consumer), phase="consumer",
                       name="clickhouse_local_json", env=env, timeout=300)
    jout = jlog.read_text(errors="replace")
    if '\"k\":42' not in jout.replace(" ", ""):
        raise RuntimeError("clickhouse local JSON consumer mismatch: %s" % jout[:400])

    session.finish(features={
        "profile": "core",
        "build_type": "Release",
        "debug_symbols": "-g0",
        "targets": ["clickhouse", "unit_tests_dbms"],
        "official_test": "ColumnObject.*",
        "rust": "disabled",
        "consumer": ["clickhouse --version", "clickhouse local aggregate", "clickhouse local JSON"],
    })
    return 0


def make_parser():
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="BUILDv1-D07: build and qualify the ClickHouse toolset from source (core profile)")
    sub = parser.add_subparsers(dest="command")
    doc = sub.add_parser("doctor", help="list exact missing source/tool/dependency items; exit 78 if not ready")
    doc.add_argument("--input", default=DEFAULT_INPUT)
    run = sub.add_parser("run", help="configure, build, test, package and locally consume ClickHouse")
    run.add_argument("--input", default=DEFAULT_INPUT)
    run.add_argument("--output", default=DEFAULT_OUTPUT)
    run.add_argument("--jobs", type=int, default=4)
    return parser


def main(argv=None):
    args = make_parser().parse_args(argv)
    if args.command == "doctor":
        report = diagnose(str(resolve_path(args.input)))
        print(json.dumps(report, indent=2))
        return 0 if report["ready"] else 78
    if args.command == "run":
        input_dir = resolve_path(args.input)
        output_dir = resolve_path(args.output, fallback_root="/workspace")
        return run_build(str(input_dir), str(output_dir), args.jobs)
    make_parser().print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
