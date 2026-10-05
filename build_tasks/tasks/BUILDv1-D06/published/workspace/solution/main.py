#!/usr/bin/env python3
"""BUILDv1-D06 (core profile): build the Apache Arrow C++ core/IPC SDK from a
fixed source archive, run the official `arrow-ipc-read-write-test` CTest entry,
install the SDK and consume it from an out-of-tree CMake consumer.

All build/configure/install/test/consumer commands go through the trusted
buildkit Session so logs, exit codes and test evidence are preserved.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

from buildkit import Session

HERE = Path(__file__).resolve().parent

# Bootstrap/toolchain binaries required by the build.
TOOLS = ["cmake", "ninja", "c++", "cc", "flatc", "pkg-config"]

# System dependency *headers* (dev packages) required by the core+IPC build.
# gflags is required by Arrow when ARROW_BUILD_TESTS is enabled.
DEPS = {
    "flatbuffers": ["flatbuffers/flatbuffers.h"],
    "rapidjson": ["rapidjson/document.h"],
    "gtest": ["gtest/gtest.h"],
    "gflags": ["gflags/gflags.h"],
}

OFFICIAL_TEST = "arrow-ipc-read-write-test"


def _prefixes():
    """Candidate installation prefixes to probe for dependency headers."""
    seen, out = set(), []

    def add(p):
        p = str(p)
        if p not in seen and Path(p).is_dir():
            seen.add(p)
            out.append(p)

    add("/usr")
    add("/usr/local")
    for root in ("/opt", "/workspace/cache"):
        r = Path(root)
        if not r.is_dir():
            continue
        add(r)
        try:
            for child in sorted(r.iterdir()):
                add(child)
        except OSError:
            pass
    return out


def _find_dep(prefixes, headers):
    for base in prefixes:
        for header in headers:
            if (Path(base) / "include" / header).is_file():
                return base
    return None


def missing_items(input_dir):
    """Return (missing_items_list, found_dep_prefixes)."""
    missing, found = [], {}
    inp = Path(input_dir)
    if not (inp / "manifest.json").is_file():
        missing.append("input/manifest.json")
    if not (inp / "source.tar.gz").is_file():
        missing.append("input/source.tar.gz")
    for tool in TOOLS:
        if shutil.which(tool) is None:
            missing.append("tool:" + tool)
    prefixes = _prefixes()
    for dep, headers in DEPS.items():
        base = _find_dep(prefixes, headers)
        if base is None:
            missing.append("dependency:%s (need include/%s)" % (dep, headers[0]))
        else:
            found[dep] = base
    return missing, found


def cmd_doctor(args):
    missing, found = missing_items(args.input)
    print(json.dumps({
        "status": "ready" if not missing else "missing",
        "missing": missing,
        "found_prefixes": sorted(set(found.values())),
    }, indent=2))
    return 0 if not missing else 78


def _build_consumer(session, env):
    cdir = session.consumer
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "consumer.cpp").write_text((HERE / "consumer" / "consumer.cpp").read_text())
    (cdir / "CMakeLists.txt").write_text((HERE / "consumer" / "CMakeLists.txt").read_text())
    bdir = cdir / "build"
    session.run([
        "cmake", "-S", str(cdir), "-B", str(bdir), "-G", "Ninja",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_PREFIX_PATH=" + str(session.install),
    ], cwd=cdir, phase="consumer", name="consumer_configure", env=env)
    session.run(["cmake", "--build", str(bdir), "--parallel", str(session.jobs)],
                cwd=bdir, phase="consumer", name="consumer_build", env=env)
    data = cdir / "roundtrip.arrow"
    session.run([str(bdir / "consumer"), str(data)],
                cwd=cdir, phase="consumer", name="consumer_run", env=env)
    session.write("consumer_result.json", {
        "binary": str(bdir / "consumer"),
        "ipc_file": str(data),
        "ipc_bytes": data.stat().st_size,
        "assertion": "schema + row order + null positions + values round-trip",
    })


def cmd_run(args):
    missing, found = missing_items(args.input)
    if missing:
        print(json.dumps({"status": "missing", "missing": missing}, indent=2))
        return 78

    session = Session(args.input, args.output, jobs=args.jobs)
    src = session.prepare()
    cpp = src / "cpp"
    jobs = str(session.jobs)
    env = {
        "ARROW_TEST_DATA": str(src / "testing"),
        "PARQUET_TEST_DATA": str(src / "cpp" / "submodules" / "parquet-testing" / "data"),
    }

    cmake_args = [
        "cmake", "-S", str(cpp), "-B", str(session.build), "-G", "Ninja",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_INSTALL_PREFIX=" + str(session.install),
        "-DARROW_BUILD_TESTS=ON",
        "-DARROW_BUILD_SHARED=ON",
        "-DARROW_BUILD_STATIC=OFF",
        "-DARROW_BUILD_BENCHMARKS=OFF",
        "-DARROW_BUILD_EXAMPLES=OFF",
        "-DARROW_BUILD_UTILITIES=OFF",
        "-DARROW_COMPUTE=OFF",
        "-DARROW_CSV=OFF",
        "-DARROW_PARQUET=OFF",
        "-DARROW_DATASET=OFF",
        "-DARROW_JSON=ON",
        "-DARROW_IPC=ON",
        "-DARROW_USE_GLOG=OFF",
        "-DARROW_DEPENDENCY_SOURCE=SYSTEM",
    ]
    extra_prefixes = sorted(p for p in set(found.values()) if p not in ("/usr", "/usr/local"))
    if extra_prefixes:
        cmake_args.append("-DCMAKE_PREFIX_PATH=" + ";".join(extra_prefixes))

    log = session.run(cmake_args, cwd=cpp, phase="configure", name="cmake_configure",
                      env=env, check=False)
    rc = session.commands[-1]["exit_code"]
    if rc != 0:
        text = log.read_text(errors="replace")
        if "gflags" in text.lower() and "could not find" in text.lower():
            print(json.dumps({
                "status": "missing",
                "missing": ["dependency:gflags (required by ARROW_BUILD_TESTS; "
                            "CMake could not find gflagsAlt)"],
                "hint": "provide libgflags-dev or a gflags prefix and re-run doctor",
            }, indent=2))
            return 78
        raise RuntimeError("Arrow configure failed; see " + str(log))

    session.run(["cmake", "--build", str(session.build), "--parallel", jobs],
                cwd=session.build, phase="build", name="cmake_build", env=env)
    session.run(["cmake", "--install", str(session.build)],
                cwd=session.build, phase="install", name="cmake_install", env=env)
    session.run(["cmake", "--build", str(session.build), "--target", OFFICIAL_TEST,
                 "--parallel", jobs],
                cwd=session.build, phase="build", name="cmake_build_official_test", env=env)

    # Preserve exact official test discovery/inventory before execution.
    session.run(["ctest", "--test-dir", str(session.build), "-N",
                 "-R", "^%s$" % OFFICIAL_TEST],
                cwd=session.build, phase="discover", name="ctest_inventory", env=env)

    session.test(OFFICIAL_TEST,
                 ["ctest", "--test-dir", str(session.build), "--output-on-failure",
                  "-R", "^%s$" % OFFICIAL_TEST, "-j", "2"],
                 cwd=session.build, parser="auto", env=env, timeout=1800)

    _build_consumer(session, env)
    session.finish(features={
        "components": ["core", "ipc"],
        "official_test": OFFICIAL_TEST,
        "consumer": "arrow-ipc-roundtrip",
        "installed": "libarrow + headers + CMake/pkg-config export",
    })
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_run = sub.add_parser("run", help="build, test and verify the Arrow SDK")
    p_run.add_argument("--input", required=True)
    p_run.add_argument("--output", required=True)
    p_run.add_argument("--jobs", type=int, default=4)
    p_run.set_defaults(func=cmd_run)
    p_doc = sub.add_parser("doctor", help="report missing source/tool/dependency items")
    p_doc.add_argument("--input", required=True)
    p_doc.set_defaults(func=cmd_doctor)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
