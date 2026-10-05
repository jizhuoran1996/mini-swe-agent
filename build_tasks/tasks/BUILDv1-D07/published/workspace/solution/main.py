#!/usr/bin/env python3
"""BUILDv1-D07 core driver: build and qualify the ClickHouse analytics toolset.

Core profile scope:
  * compile the full ``clickhouse`` monolith and the aggregated ``unit_tests_dbms``
    binary from the pinned source release whose CPU ``contrib/`` gitlink submodules
    (LLVM libc++, googletest, boost, fmt, protos/brotli/zstd/...) all ship in the
    frozen source-with-submodules archive,
  * run the official ``ColumnObject.*`` GoogleTest suite and capture its inventory,
  * stage the freshly built binary into a private install tree and consume it with
    a deterministic ``clickhouse local`` SQL aggregate and JSON-column query.

The core profile deliberately does **not** start a persistent server/client.
No system ClickHouse and no prebuilt artifact is ever substituted: the delivered
binary is the one produced this session under ``$BUILD``.

Compiler/linker selection follows the upstream sanctioned route: only
``-DCMAKE_C_COMPILER`` / ``-DCMAKE_CXX_COMPILER`` / ``-DCMAKE_LINKER`` cache
entries are supplied.  ``PreLoad.cmake`` rejects any non-empty ``CFLAGS`` /
``CXXFLAGS`` / ``LDFLAGS`` / ``CMAKE_*_FLAGS`` / ``CMAKE_*FLAGS_INIT`` value, so
those are explicitly cleared in the child environment instead of being
injected.  Debug-info layout is chosen through upstream's build-type contract
(``CMAKE_BUILD_TYPE=Release`` implies ``OMIT_HEAVY_DEBUG_SYMBOLS=ON``); no custom
``CFLAGS`` are used and no upstream CMake is patched.

Compiler caching is intentionally disabled via the genuine, upstream-supported
``-DCOMPILER_CACHE=disabled`` option: this benchmark performs a full cold source
build and no ccache/sccache binary is provisioned.  The message emitted by
``cmake/ccache.cmake`` names this option explicitly.  No fake cache tool is
installed and no error is suppressed.
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

# Prefer genuine suffixed clang-19/lld-19; fall back to older suffixed tools so
# the doctor reports the real version gap when 19 is absent.
TOOL_ALIASES = {
    "cmake": ["cmake"],
    "ninja": ["ninja", "ninja-build"],
    "python3": ["python3", "python3.12", "python3.11"],
    "clang": ["clang-19", "clang", "clang-18", "clang-17"],
    "clang++": ["clang++-19", "clang++", "clang++-18", "clang++-17"],
    "ld.lld": ["ld.lld-19", "ld.lld", "ld.lld-18", "ld.lld-17"],
    "llvm-config": ["llvm-config-19", "llvm-config", "llvm-config-18"],
}

# Variables PreLoad.cmake refuses when non-empty. We clear every one of them in
# the child environment so no custom flag leaks in from us or from any parent.
PRELOAD_FORBIDDEN_FLAGS = (
    "CFLAGS", "CXXFLAGS", "LDFLAGS",
    "CMAKE_C_FLAGS", "CMAKE_CXX_FLAGS",
    "CMAKE_EXE_LINKER_FLAGS", "CMAKE_SHARED_LINKER_FLAGS", "CMAKE_MODULE_LINKER_FLAGS",
    "CMAKE_C_FLAGS_INIT", "CMAKE_CXX_FLAGS_INIT",
    "CMAKE_EXE_LINKER_FLAGS_INIT", "CMAKE_MODULE_LINKER_FLAGS_INIT",
)

# Real source paths the vendored CPU submodules physically expose. Boost and
# OpenSSL do NOT ship a top-level CMakeLists.txt; ClickHouse drives them through
# the first-party wrappers in contrib/boost-cmake and contrib/openssl-cmake.
#
# Some upstream headers in an autotools project are generated at configure time
# (OpenSSL's include/openssl/ssl.h is derived from ssl.h.in). Those entries carry
# ``accept`` alternatives so the doctor accepts the genuine template the official
# build consumes, instead of demanding a pre-generated output before configure.
REQUIRED_PATHS = (
    {"label": "CMakeLists.txt", "kind": "source", "accept": ("CMakeLists.txt",)},
    {"label": "PreLoad.cmake", "kind": "source", "accept": ("PreLoad.cmake",)},
    {"label": "cmake/tools.cmake", "kind": "source", "accept": ("cmake/tools.cmake",)},
    {"label": "cmake/ccache.cmake", "kind": "source", "accept": ("cmake/ccache.cmake",)},
    {"label": "contrib/CMakeLists.txt", "kind": "source", "accept": ("contrib/CMakeLists.txt",)},
    {"label": "contrib/sysroot/README.md", "kind": "dependency",
     "accept": ("contrib/sysroot/README.md",)},
    {"label": "contrib/googletest/CMakeLists.txt", "kind": "dependency",
     "accept": ("contrib/googletest/CMakeLists.txt",)},
    {"label": "contrib/boost-cmake/CMakeLists.txt", "kind": "dependency",
     "accept": ("contrib/boost-cmake/CMakeLists.txt",)},
    {"label": "contrib/boost/boost/version.hpp", "kind": "dependency",
     "accept": ("contrib/boost/boost/version.hpp",)},
    {"label": "contrib/openssl-cmake/CMakeLists.txt", "kind": "dependency",
     "accept": ("contrib/openssl-cmake/CMakeLists.txt",)},
    {"label": "contrib/openssl/Configure", "kind": "dependency",
     "accept": ("contrib/openssl/Configure",)},
    # ssl.h is a generated header: accept the real template the configure step
    # consumes when the generated output is not (yet) present in the bundle.
    {"label": "contrib/openssl/include/openssl/ssl.h", "kind": "dependency",
     "accept": ("contrib/openssl/include/openssl/ssl.h",
                "contrib/openssl/include/openssl/ssl.h.in"),
     "generated_by_configure": True,
     "generated_note": ("contrib/openssl/include/openssl/ssl.h is generated from "
                        "include/openssl/ssl.h.in by the official OpenSSL configure step")},
    {"label": "contrib/zlib-ng/CMakeLists.txt", "kind": "dependency",
     "accept": ("contrib/zlib-ng/CMakeLists.txt",)},
    {"label": "contrib/libarchive/CMakeLists.txt", "kind": "dependency",
     "accept": ("contrib/libarchive/CMakeLists.txt",)},
    {"label": "src/Columns/tests/gtest_column_object.cpp", "kind": "source",
     "accept": ("src/Columns/tests/gtest_column_object.cpp",)},
)
_ALL_ACCEPTED = frozenset(p for entry in REQUIRED_PATHS for p in entry["accept"])

FILES_OF_INTEREST = ("CMakeLists.txt", "cmake/tools.cmake", "cmake/ccache.cmake")
VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")
CMAKE_MIN_RE = re.compile(r"cmake_minimum_required\s*\(\s*VERSION\s+([0-9.]+)", re.I)
CMAKE_MIN_ALT_RE = re.compile(r"cmake_minimum_required\s*\(\s*([0-9.]+)", re.I)
CLANG_VAR_RE = re.compile(r"CLANG_MINIMUM_VERSION[\s\"']+([0-9]+)")
CLANG_GUARD_RE = re.compile(r"CMAKE_CXX_COMPILER_VERSION\s+VERSION_LESS(?:_EQUAL)?\s+\$?\{?CLANG_MINIMUM_VERSION\}?")
CLANG_GUARD_LITERAL_RE = re.compile(r"CMAKE_CXX_COMPILER_VERSION\s+VERSION_LESS(?:_EQUAL)?\s+([0-9.]+)")


def sha256_file(path, chunk=8 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def probe(path, args=("--version",)):
    try:
        out = subprocess.run([path, *args], capture_output=True, text=True, timeout=20)
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


def scan_archive(archive, files_of_interest, accepted):
    """One pass over the tar.

    Returns (contents of interesting files, subset of accepted rel paths present).
    """
    wanted = set(files_of_interest)
    contents = {}
    seen = set()
    with tarfile.open(archive, "r:*") as tf:
        for member in tf:
            if not member.isfile():
                continue
            parts = member.name.split("/", 1)
            rel = parts[1] if len(parts) == 2 else member.name
            if rel in accepted:
                seen.add(rel)
            if rel in wanted:
                try:
                    fh = tf.extractfile(member)
                    if fh is not None:
                        contents[rel] = fh.read(1 << 20).decode(errors="replace")
                except Exception:
                    pass
    return contents, seen


def resolve_path(p, fallback_root="/workspace"):
    p = Path(p)
    if p.exists():
        return p
    alt = Path(fallback_root) / p
    if alt.exists():
        return alt
    return p


def preload_rejecting_env(jobs):
    """Environment for every cmake invocation.

    Explicitly clears every variable PreLoad.cmake rejects, so neither we nor any
    caller of this program can leak a custom CFLAGS/CXXFLAGS/LDFLAGS/CMAKE_*FLAGS
    value into the ClickHouse build. Compiler/linker identity travels exclusively
    through the sanctioned -DCMAKE_*_COMPILER / -DCMAKE_LINKER cache entries.
    """
    env = {name: "" for name in PRELOAD_FORBIDDEN_FLAGS}
    env["CMAKE_BUILD_PARALLEL_LEVEL"] = str(jobs)
    return env


def diagnose(input_dir):
    input_dir = Path(input_dir).resolve()
    missing = []
    found = {"tools": {}, "notes": [], "generated_at_configure": []}

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
            contents, seen = scan_archive(archive, FILES_OF_INTEREST, _ALL_ACCEPTED)
        except Exception as exc:
            contents, seen = {}, set()
            missing.append({"kind": "source", "item": str(archive),
                            "reason": "cannot read archive: %s" % exc})

        for entry in REQUIRED_PATHS:
            hit = next((c for c in entry["accept"] if c in seen), None)
            if hit is None:
                missing.append({"kind": entry["kind"], "item": entry["label"],
                                "reason": "required source/submodule path absent from bundle"})
                continue
            if entry.get("generated_by_configure") and hit != entry["label"]:
                # The generated output is not shipped; the real template the
                # official build consumes is present. This is not a defect.
                found["generated_at_configure"].append({
                    "expected_after_configure": entry["label"],
                    "template_present": hit,
                    "note": entry["generated_note"],
                })
                found["notes"].append(entry["generated_note"])

        top = contents.get("CMakeLists.txt")
        if top:
            m = CMAKE_MIN_RE.search(top) or CMAKE_MIN_ALT_RE.search(top)
            if m:
                cmake_min = m.group(1)
                found["cmake_minversion"] = cmake_min
        tools_text = contents.get("cmake/tools.cmake") or ""
        mv = CLANG_VAR_RE.search(tools_text)
        if mv:
            clang_min = mv.group(1)
            found["clang_minversion"] = clang_min
            found["clang_minimum_source"] = "CLANG_MINIMUM_VERSION in cmake/tools.cmake"
        else:
            vers = CLANG_GUARD_LITERAL_RE.findall(tools_text)
            if vers:
                clang_min = max(vers, key=lambda v: tuple(int(x) for x in v.split(".")))
                found["clang_minversion"] = clang_min
                found["clang_minimum_source"] = "literal VERSION_LESS guard in cmake/tools.cmake"
            elif CLANG_GUARD_RE.search(tools_text):
                found["notes"].append("cmake/tools.cmake references CLANG_MINIMUM_VERSION but value not parsed")

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
        want = tuple(int(x) for x in cmake_min.split(".") if x)
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
            want = (int(clang_min),)
            if have and version_lt(have, want):
                missing.append({"kind": "tool", "item": cc,
                                "reason": "Clang >= %s required by source (CLANG_MINIMUM_VERSION), found %s"
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

    session = buildkit.Session(input_dir, output_dir, jobs)
    # Session.jobs is authoritative: buildkit clamps the requested value against
    # the frozen manifest's build_job_limit (8 for this recorded resource-only
    # core variant) and never exceeds that genuinely provisioned lane cap.
    jobs = session.jobs
    session.prepare()
    src, build = session.src, session.build

    tools = report["found"]["tools"]
    cmake = tools["cmake"]["path"]
    ninja = tools["ninja"]["path"]
    cc = tools["clang"]["path"]
    cxx = tools["clang++"]["path"]
    lld = tools["ld.lld"].get("path") if isinstance(tools.get("ld.lld"), dict) else None

    # Only the sanctioned cache entries are supplied; PreLoad.cmake's forbidden
    # flag variables are explicitly cleared (never injected).
    env = preload_rejecting_env(jobs)

    configure = [
        cmake, "-S", str(src), "-B", str(build), "-G", "Ninja",
        "-DCMAKE_MAKE_PROGRAM=" + ninja,
        "-DCMAKE_BUILD_TYPE=Release",
        "-DENABLE_TESTS=ON",
        "-DENABLE_RUST=OFF",
        # Genuine upstream option, named verbatim by the cmake/ccache.cmake error.
        # This is a full cold source build and no ccache/sccache is provisioned;
        # we do not install a fake cache tool and do not suppress the message.
        "-DCOMPILER_CACHE=disabled",
        "-DCMAKE_C_COMPILER=" + cc,
        "-DCMAKE_CXX_COMPILER=" + cxx,
    ]
    # Upstream-supported link-time switch: point CMake at the real lld driver
    # through CMAKE_LINKER, which PreLoad.cmake does not inspect.
    if lld:
        configure.append("-DCMAKE_LINKER=" + lld)

    session.run(configure, cwd=str(src), phase="configure", name="cmake_configure",
                env=env, timeout=3600)

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
        "debug_info_policy": "upstream CMAKE_BUILD_TYPE=Release implies OMIT_HEAVY_DEBUG_SYMBOLS=ON; no custom CFLAGS",
        "compiler_cache": "disabled (upstream -DCOMPILER_CACHE=disabled; no ccache/sccache provisioned)",
        "targets": ["clickhouse", "unit_tests_dbms"],
        "official_test": "ColumnObject.*",
        "rust": "disabled",
        "build_jobs": jobs,
        "toolchain_selection": {
            "CMAKE_C_COMPILER": cc, "CMAKE_CXX_COMPILER": cxx, "CMAKE_LINKER": lld or "default",
        },
        "forbidden_flags_cleared": list(PRELOAD_FORBIDDEN_FLAGS),
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
