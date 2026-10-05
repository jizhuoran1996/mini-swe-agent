#!/usr/bin/env python3
"""BUILDv1-D06 (core profile): build the Apache Arrow C++ core/IPC SDK from the
pinned source archive, run the official `arrow-ipc-read-write-test` CTest entry,
install the SDK and consume it from an out-of-tree CMake consumer.

All build/configure/install/test/consumer commands go through the trusted
buildkit Session so logs, exit codes and test evidence are preserved.

The frozen core profile is *core + IPC*; compute/CSV/Parquet are out of scope.
CMake aborts on missing optional third-party packages, so the run probes the
host honestly: it enables the optional compute module only when a genuine re2
(header + linkable library, or CMake package config) is actually present, and
otherwise configures core+IPC without compute.  It never fabricates a missing
dependency or a failure message; the real configure log tail is surfaced.
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from buildkit import Session

HERE = Path(__file__).resolve().parent

# Toolchain binaries required to compile and package the SDK.
TOOLS = ["cmake", "ninja", "c++", "cc", "flatc", "pkg-config"]

# Development headers that must exist as real files (never synthesized).
HEADER_DEPS = {
    "flatbuffers": "flatbuffers/flatbuffers.h",
    "rapidjson": "rapidjson/document.h",
    "gtest": "gtest/gtest.h",
}

OFFICIAL_TEST = "arrow-ipc-read-write-test"


def _prefix_candidates():
    """Install-prefix candidates to hand to CMake for dependency discovery."""
    roots = ["/opt", "/workspace/cache", "/usr/local", "/usr"]
    seen, out = set(), []

    def add(path):
        try:
            path = os.path.normpath(str(path))
        except Exception:
            return
        if path not in seen and os.path.isdir(path):
            seen.add(path)
            out.append(path)

    for root in roots:
        add(root)
        if not os.path.isdir(root):
            continue
        try:
            children = sorted(os.listdir(root))
        except OSError:
            continue
        for child in children:
            add(os.path.join(root, child))
    # staged dependencies may sit one level deeper (/opt/<dep>/<prefix>)
    for root in ("/opt", "/workspace/cache"):
        if not os.path.isdir(root):
            continue
        try:
            children = sorted(os.listdir(root))
        except OSError:
            continue
        for child in children:
            level1 = os.path.join(root, child)
            if not os.path.isdir(level1):
                continue
            try:
                grandchildren = sorted(os.listdir(level1))
            except OSError:
                continue
            for grandchild in grandchildren:
                add(os.path.join(level1, grandchild))
    return out


def _find_header_dep(prefixes, header):
    for base in prefixes:
        if os.path.isfile(os.path.join(base, "include", header)):
            return base
    return None


def _find_re2(prefixes):
    """Locate a genuine re2 header + linkable library, else None."""
    for base in prefixes:
        include_dir = os.path.join(base, "include")
        if not os.path.isfile(os.path.join(include_dir, "re2", "re2.h")):
            continue
        for rel in ("lib", "lib64", os.path.join("lib", "x86_64-linux-gnu")):
            lib_dir = os.path.join(base, rel)
            if not os.path.isdir(lib_dir):
                continue
            try:
                entries = sorted(os.listdir(lib_dir))
            except OSError:
                continue
            for entry in entries:
                if entry == "libre2.so" or entry.startswith("libre2.so.") \
                        or entry == "libre2.a":
                    return include_dir, os.path.join(lib_dir, entry)
    return None


def _find_re2_config(prefixes):
    """Locate a re2 CMake package directory, else None."""
    for base in prefixes:
        for rel in ("lib/cmake/re2", "lib64/cmake/re2", "share/cmake/re2"):
            directory = os.path.join(base, rel)
            if not os.path.isdir(directory):
                continue
            for entry in os.listdir(directory):
                if entry in ("re2Config.cmake", "re2-config.cmake"):
                    return directory
    return None


def inventory(input_dir):
    """Return (missing_items, found_dependency_prefixes, prefix_candidates)."""
    missing = []
    prefixes = _prefix_candidates()
    source = Path(input_dir)
    if not (source / "manifest.json").is_file():
        missing.append("input/manifest.json")
    if not (source / "source.tar.gz").is_file():
        missing.append("input/source.tar.gz")
    for tool in TOOLS:
        if shutil.which(tool) is None:
            missing.append("tool:" + tool)
    found = {}
    for dep, header in HEADER_DEPS.items():
        base = _find_header_dep(prefixes, header)
        if base is None:
            missing.append("dependency:%s (need include/%s)" % (dep, header))
        else:
            found[dep] = base
    return missing, found, prefixes


def cmd_doctor(args):
    missing, found, prefixes = inventory(args.input)
    re2 = _find_re2(prefixes)
    re2_config = _find_re2_config(prefixes)
    print(json.dumps({
        "status": "ready" if not missing else "missing",
        "missing": missing,
        "found_deps": found,
        "re2": ({"include": re2[0], "library": re2[1]} if re2 else
                ({"cmake_dir": re2_config} if re2_config else None)),
        "components": (["core", "ipc", "compute"] if (re2 or re2_config) else
                       ["core", "ipc"]),
    }, indent=2))
    return 0 if not missing else 78


def _build_consumer(session, env):
    consumer = session.consumer
    consumer.mkdir(parents=True, exist_ok=True)
    (consumer / "consumer.cpp").write_text(
        (HERE / "consumer" / "consumer.cpp").read_text())
    (consumer / "CMakeLists.txt").write_text(
        (HERE / "consumer" / "CMakeLists.txt").read_text())
    build = consumer / "build"
    session.run(["cmake", "-S", str(consumer), "-B", str(build), "-G", "Ninja",
                 "-DCMAKE_BUILD_TYPE=Release",
                 "-DCMAKE_PREFIX_PATH=" + str(session.install)],
                cwd=consumer, phase="consumer", name="consumer_configure",
                env=env, timeout=600)
    session.run(["cmake", "--build", str(build), "--parallel", str(session.jobs)],
                cwd=build, phase="consumer", name="consumer_build", env=env, timeout=900)
    data = consumer / "roundtrip.arrow"
    session.run([str(build / "consumer"), str(data)], cwd=consumer,
                phase="consumer", name="consumer_run", env=env, timeout=300)
    session.write("consumer_result.json", {
        "binary": str(build / "consumer"),
        "ipc_file": str(data),
        "ipc_bytes": data.stat().st_size,
        "assertion": "schema + row order + null positions + values round-trip through installed SDK",
    })


def cmd_run(args):
    missing, found, prefixes = inventory(args.input)
    if missing:
        print(json.dumps({"status": "missing", "missing": missing}, indent=2))
        return 78

    session = Session(args.input, args.output, jobs=args.jobs)
    src = session.prepare()
    cpp = src / "cpp"

    env = {}
    if (src / "testing").is_dir():
        env["ARROW_TEST_DATA"] = str(src / "testing")
    if (cpp / "submodules" / "parquet-testing").is_dir():
        env["PARQUET_TEST_DATA"] = str(cpp / "submodules" / "parquet-testing")

    re2 = _find_re2(prefixes)
    re2_config = _find_re2_config(prefixes)
    compute = "ON" if (re2 or re2_config) else "OFF"

    cmake_args = [
        "cmake", "-S", str(cpp), "-B", str(session.build), "-G", "Ninja",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_INSTALL_PREFIX=" + str(session.install),
        "-DCMAKE_PREFIX_PATH=" + ";".join(prefixes),
        "-DARROW_BUILD_TESTS=ON",
        "-DARROW_BUILD_STATIC=OFF",
        "-DARROW_BUILD_SHARED=ON",
        "-DARROW_BUILD_EXAMPLES=OFF",
        "-DARROW_BUILD_BENCHMARKS=OFF",
        "-DARROW_BUILD_UTILITIES=OFF",
        "-DARROW_COMPUTE=" + compute,
        "-DARROW_IPC=ON",
        "-DARROW_CSV=OFF",
        "-DARROW_DATASET=OFF",
        "-DARROW_PARQUET=OFF",
        "-DARROW_JEMALLOC=OFF",
        "-DARROW_MIMALLOC=OFF",
        "-DARROW_USE_GLOG=OFF",
        "-DARROW_DEPENDENCY_SOURCE=SYSTEM",
    ]
    if re2:
        cmake_args += ["-DRE2_INCLUDE_DIR=" + re2[0], "-DRE2_LIB=" + re2[1]]
    if re2_config:
        cmake_args.append("-Dre2_DIR=" + re2_config)
    if compute == "OFF":
        # core+IPC only: avoid optional packages that have no system provider.
        cmake_args += ["-DARROW_WITH_RE2=OFF", "-DARROW_WITH_UTF8PROC=OFF"]

    result = session.run(cmake_args, cwd=cpp, phase="configure",
                         name="cmake_configure", env=env, timeout=1800, check=False)
    configure = session.commands[-1]
    if configure["exit_code"] != 0:
        tail = result.read_bytes()[-12000:].decode(errors="replace")
        missing_lines = [line.strip() for line in tail.splitlines()
                         if "Could NOT find" in line or "CMake Error" in line]
        raise RuntimeError("Arrow configure failed (log tail below):\n" +
                           "\n".join(missing_lines[-10:]) + "\n---\n" + tail)

    session.run(["cmake", "--build", str(session.build), "--target", OFFICIAL_TEST,
                 "--parallel", str(session.jobs)],
                cwd=session.build, phase="build", name="build_official_test",
                env=env, timeout=7200)
    session.run(["cmake", "--install", str(session.build)], cwd=session.build,
                phase="install", name="cmake_install", env=env, timeout=1800)

    session.run(["ctest", "--test-dir", str(session.build), "-N",
                 "-R", "^%s$" % OFFICIAL_TEST],
                cwd=session.build, phase="discover", name="ctest_inventory", env=env)

    session.test(OFFICIAL_TEST,
                 ["ctest", "--test-dir", str(session.build), "--output-on-failure",
                  "-R", "^%s$" % OFFICIAL_TEST, "-j", "2"],
                 cwd=session.build, parser="auto", env=env, timeout=1800)

    _build_consumer(session, env)
    session.finish(features={
        "components": ["core", "ipc"] + (["compute"] if compute == "ON" else []),
        "official_test": OFFICIAL_TEST,
        "consumer": "arrow-ipc-roundtrip",
        "dependency_source": "system",
        "re2": bool(re2 or re2_config),
        "installed": "libarrow + headers + CMake/pkg-config export",
    })
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="build, test and verify the Arrow SDK")
    run.add_argument("--input", required=True)
    run.add_argument("--output", required=True)
    run.add_argument("--jobs", type=int, default=4)
    run.set_defaults(func=cmd_run)
    doctor = sub.add_parser("doctor", help="report missing source/tool/dependency items")
    doctor.add_argument("--input", required=True)
    doctor.set_defaults(func=cmd_doctor)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
