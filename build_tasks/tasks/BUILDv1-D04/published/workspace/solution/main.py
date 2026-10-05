#!/usr/bin/env python3
"""BUILDv1-D04 (core profile): build the RocksDB static SDK from the frozen source,
run the official db_basic_test suite, install headers/library and verify an out-of-tree
static consumer that writes, reopens, reads and deletes keys across processes.

All build/install/test/consumer commands go through buildkit.Session, so every command's
exit code and log is preserved as evidence.
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
MAKE_BASE = ["PORTABLE=1"]  # never -march=native
ALL_MODES = ([], ["DEBUG_LEVEL=1"], ["DEBUG_LEVEL=2"])
STATIC_LIB_NAME = "librocksdb.a"


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def mode_label(flags):
    return "upstream_default" if not flags else flags[-1].replace("=", "_")


def find_header(name: str):
    for root in ("/usr/include", "/usr/local/include"):
        candidate = Path(root) / name
        if candidate.exists():
            return str(candidate)
    return None


def merge(*sequences):
    ordered = []
    for sequence in sequences:
        for token in sequence:
            if token not in ordered:
                ordered.append(token)
    return ordered


def gtest_inventory(text: str):
    """Turn `--gtest_list_tests` output into fully-qualified test names."""
    names, suite = [], None
    for raw in text.splitlines():
        if not raw.strip():
            continue
        if not raw.startswith((" ", "\t")):
            suite = raw.strip()
            continue
        if suite is not None:
            names.append(suite + raw.split()[0])
    return names


def platform_link_libs(src: Path):
    """Harvest the -l flags the RocksDB build recorded in make_config.mk."""
    tokens = []
    config = src / "make_config.mk"
    if config.is_file():
        for line in config.read_text(errors="replace").splitlines():
            line = line.strip()
            if line.startswith(("PLATFORM_LDFLAGS", "PLATFORM_LIBS", "EXEC_LDFLAGS")):
                _, _, value = line.partition("=")
                tokens.extend(t for t in value.split() if re.fullmatch(r"-l\S+", t))
    return merge(tokens, BASE_LIBS)


def link_candidates(src: Path):
    parsed = platform_link_libs(src)
    return [parsed, merge(parsed, COMPRESSION_LIBS), merge(BASE_LIBS, COMPRESSION_LIBS)]


def rocksdb_version(src: Path):
    text = (src / "include" / "rocksdb" / "version.h").read_text(errors="replace")

    def number(name):
        found = re.search(rf"#define\s+{name}\s+(\d+)", text)
        return found.group(1) if found else "0"

    return f"{number('ROCKSDB_MAJOR')}.{number('ROCKSDB_MINOR')}.{number('ROCKSDB_PATCH')}"


def locate_static_lib(src: Path):
    """Find the static archive wherever the build placed it."""
    direct = src / STATIC_LIB_NAME
    if direct.is_file():
        return direct
    try:
        found = sorted(p for p in src.rglob("librocksdb*.a") if p.is_file())
    except OSError:
        found = []
    return found[0] if found else None


# --------------------------------------------------------------------------- #
# build-mode selection: upstream disables SyncPoint and the DBImpl TEST_ helpers
# under -DNDEBUG, so the official test binary only compiles in an assert-enabled
# (non-NDEBUG) build. Pick such a mode by dry-run probing the real recipes.
# --------------------------------------------------------------------------- #
def static_mode_candidates(src: Path):
    text = (src / "Makefile").read_text(errors="replace")
    ndebug, current = set(), None
    for line in text.splitlines():
        found = re.match(r"\s*ifeq\s*\(\s*\$\(DEBUG_LEVEL\)\s*,\s*([0-9A-Za-z_]+)\s*\)", line)
        if found:
            current = found.group(1)
        if "-DNDEBUG" in line and current is not None:
            ndebug.add(current)
    declared = re.search(r"(?m)^\s*DEBUG_LEVEL\s*[:?]?=\s*([0-9A-Za-z_]+)", text)
    default = declared.group(1) if declared else None
    ordered = []
    if default is None or default not in ndebug:
        ordered.append([])
    for level in ("1", "2"):
        if level not in ndebug:
            ordered.append([f"DEBUG_LEVEL={level}"])
    ordered.extend(ALL_MODES)
    unique, seen = [], set()
    for flags in ordered:
        if tuple(flags) not in seen:
            seen.add(tuple(flags))
            unique.append(flags)
    return unique


def probe_mode(sess, src, env, flags):
    """Dry-run only: report whether this mode compiles db_basic_test with -DNDEBUG."""
    log = sess.run(
        ["make", "-n", *MAKE_BASE, *flags, "db/db_basic_test.o"],
        cwd=src,
        phase="probe",
        name=f"probe_{mode_label(flags)}",
        env=env,
        timeout=300,
        check=False,
    )
    text = log.read_text(errors="replace")
    if not re.search(r"-c\s+(\./)?db/db_basic_test\.cc", text):
        return None  # inconclusive, no displayed compile recipe
    return "-DNDEBUG" in text


def choose_mode(sess, src, env):
    verdicts = {mode_label(flags): probe_mode(sess, src, env, flags) for flags in ALL_MODES}
    for flags in ALL_MODES:
        if verdicts[mode_label(flags)] is False:
            return flags, verdicts
    for flags in ALL_MODES:
        if verdicts[mode_label(flags)] is None:
            return flags, verdicts
    return static_mode_candidates(src)[0], verdicts


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
            notes.append(f"source archive ok: {archive.name} ({archive.stat().st_size} bytes, sha256 verified)")
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
            notes.append(f"optional dependency header {header}: not found (RocksDB auto-detects and builds without it)")
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
# build / install
# --------------------------------------------------------------------------- #
def install_targets(src: Path):
    makefile = (src / "Makefile").read_text(errors="replace")
    found = set(re.findall(r"^(install[A-Za-z0-9_]*(?:-[A-Za-z0-9_]+)?)\s*:", makefile, re.M))
    static = next((name for name in ("install-static", "install_static") if name in found), None)
    headers = next((name for name in ("install-headers", "install_headers") if name in found), None)
    if static:
        return [target for target in (headers, static) if target]
    return ["install-headers", "install-static"]


def build_static(sess, src, env, jobs, first):
    order = [first] + [flags for flags in ALL_MODES if flags != first]
    attempts, used = [], None
    for flags in order:
        sess.run(
            ["make", "-j", str(jobs), *MAKE_BASE, *flags, "static_lib", *TEST_BINARIES],
            cwd=src,
            phase="build",
            name=f"build_{mode_label(flags)}",
            env=env,
            timeout=7200,
            check=False,
        )
        code = sess.commands[-1]["exit_code"]
        attempts.append({"mode": flags or ["<upstream default>"], "exit_code": code})
        if code == 0:
            used = flags
            break
        # different modes change CXXFLAGS, which make does not track: clean before retrying.
        sess.run(["make", "clean"], cwd=src, phase="clean", name=f"clean_after_{mode_label(flags)}",
                 env=env, timeout=900, check=False)
    if used is None:
        raise RuntimeError("library + db_basic_test build failed in every candidate mode: " + json.dumps(attempts))
    for binary in TEST_BINARIES:
        if not (src / binary).is_file():
            raise RuntimeError(f"build reported success but {binary} is missing")
    lib = locate_static_lib(src)
    sess.write(
        "post_build_state.json",
        {
            "task_id": TASK_ID,
            "mode": used or ["<upstream default>"],
            "static_lib": str(lib) if lib else None,
            "static_lib_bytes": lib.stat().st_size if lib else 0,
            "test_binaries": {b: (src / b).stat().st_size for b in TEST_BINARIES if (src / b).is_file()},
            "include_dir_present": (src / "include").is_dir(),
        },
    )
    return used, attempts


def stage_install(sess, src, install, env, mode, jobs, attempts):
    """Run the upstream install targets; if they place nothing, stage built artifacts
    directly so a real, usable SDK is always delivered (recorded honestly)."""
    targets = install_targets(src)
    sess.run(
        ["make", *MAKE_BASE, *mode, f"PREFIX={install}", f"INSTALL_PATH={install}", *targets],
        cwd=src,
        phase="install",
        name="install_static_sdk",
        env=env,
        timeout=1800,
        check=False,
    )
    install_exit = sess.commands[-1]["exit_code"]
    install_log = sess.commands[-1]["log"]

    static_lib = install / "lib" / STATIC_LIB_NAME
    header = install / "include" / "rocksdb" / "db.h"
    staged_directly = False
    source_lib = None
    if not (static_lib.is_file() and header.is_file()):
        staged_directly = True
        source_lib = locate_static_lib(src)
        if source_lib is None:
            # The install targets changed the build tree; rebuild the archive explicitly.
            sess.run(["make", "-j", str(jobs), *MAKE_BASE, *mode, "static_lib"], cwd=src,
                     phase="build", name="rebuild_static_lib", env=env, timeout=7200, check=False)
            source_lib = locate_static_lib(src)
        if source_lib is None:
            tail = (sess.output / install_log).read_text(errors="replace")[-6000:]
            raise RuntimeError(
                "no librocksdb.a found after build and install; modes tried: "
                + json.dumps(attempts) + "\ninstall log tail:\n" + tail
            )
        (install / "lib").mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_lib, static_lib)
        header = install / "include" / "rocksdb" / "db.h"
        if not header.is_file():
            if not (src / "include").is_dir():
                raise RuntimeError(f"no installed headers and no source headers at {src / 'include'}")
            shutil.copytree(src / "include", install / "include", dirs_exist_ok=True)
    if not (static_lib.is_file() and header.is_file()):
        raise RuntimeError("install step produced neither librocksdb.a nor rocksdb headers")

    for target, dest in (("static_lib", static_lib), ("static_lib", install / "lib" / f"{STATIC_LIB_NAME}")):
        del target, dest  # no-op; kept minimal

    pkg_config = sorted(str(p.relative_to(install)) for p in install.rglob("*.pc"))
    generated_pc = None
    if not pkg_config:
        # The upstream Makefile ships no pkg-config file; generate one that
        # describes exactly this install tree (marked as builder-generated).
        pc_dir = install / "lib" / "pkgconfig"
        pc_dir.mkdir(parents=True, exist_ok=True)
        private = " ".join(link for link in platform_link_libs(src) if link != "-lrocksdb")
        (pc_dir / "rocksdb.pc").write_text(
            "prefix={p}\nincludedir=${{prefix}}/include\nlibdir=${{prefix}}/lib\n\n"
            "Name: rocksdb\nDescription: RocksDB embedded key-value store, static SDK "
            "(builder-generated by {task})\nVersion: {version}\n"
            "Cflags: -I${{includedir}}\nLibs: -L${{libdir}} -lrocksdb\nLibs.private: {private}\n".format(
                p=install, task=TASK_ID, version=rocksdb_version(src), private=private
            )
        )
        generated_pc = "lib/pkgconfig/rocksdb.pc"
        pkg_config = [generated_pc]

    sess.write(
        "install_notes.json",
        {
            "task_id": TASK_ID,
            "make_targets": targets,
            "make_exit_code": install_exit,
            "make_log": install_log,
            "copy_fallback_used": staged_directly,
            "staged_from": str(source_lib) if source_lib else None,
            "builder_generated_pkg_config": generated_pc,
            "static_library": str(static_lib.relative_to(install)),
            "static_library_bytes": static_lib.stat().st_size,
            "link_libraries": list(platform_link_libs(src)),
        },
    )
    return pkg_config


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #
def run(args):
    sess = buildkit.Session(args.input, args.output, args.jobs)
    sess.prepare()
    src, install, consumer = sess.src, sess.install, sess.consumer
    test_tmp = sess.build / "test_tmp"
    test_tmp.mkdir(parents=True, exist_ok=True)
    env = {"CC": "gcc", "CXX": "g++", "TEST_TMPDIR": str(test_tmp)}

    mode, verdicts = choose_mode(sess, src, env)
    mode, attempts = build_static(sess, src, env, sess.jobs, mode)
    sess.write(
        "build_mode.json",
        {"task_id": TASK_ID, "dry_run_ndebug_verdicts": verdicts,
         "selected_mode": mode or ["<upstream default>"], "build_attempts": attempts,
         "portable": True, "jobs": sess.jobs},
    )

    # 1. official discovery first: the executed set is pinned before running.
    for binary in TEST_BINARIES:
        log = sess.run([f"./{binary}", "--gtest_list_tests"], cwd=src, phase="discovery",
                       name=f"list_{binary}", env=env, timeout=900)
        names = gtest_inventory(log.read_text(errors="replace"))
        sess.write(f"discovery_{binary}.json",
                   {"binary": binary, "task_id": TASK_ID, "discovered": len(names), "tests": names})
        if not names:
            raise RuntimeError(f"official discovery found no tests in {binary}")

    # 2. official test execution.
    for binary in TEST_BINARIES:
        sess.test(binary, [f"./{binary}"], cwd=src, parser="gtest_cases", env=env, timeout=7200)

    # 3. install the static SDK with the same build variables as library and test.
    pkg_config = stage_install(sess, src, install, env, mode, sess.jobs, attempts)

    # 4. out-of-tree static consumer: installed headers + installed archive only.
    consumer_src = consumer / "rocksdb_consumer.cc"
    shutil.copy2(Path(__file__).resolve().parent / "consumer.cc", consumer_src)
    binary = consumer / "rocksdb_consumer"
    cxx = shutil.which("g++") or "g++"
    link_prefix = [cxx, "-std=c++17", "-O2", "-I", str(install / "include"),
                   str(consumer_src), str(install / "lib" / STATIC_LIB_NAME), "-o", str(binary)]
    linked_with = None
    for index, extra in enumerate(link_candidates(src)):
        sess.run(link_prefix + list(extra), cwd=consumer, phase="consumer_build",
                 name=f"consumer_static_link_{index}", env=env, timeout=1800, check=False)
        if sess.commands[-1]["exit_code"] == 0:
            linked_with = list(extra)
            break
    if linked_with is None:
        raise RuntimeError("static consumer link failed for every candidate library set")

    ldd_log = sess.run(["ldd", str(binary)], cwd=consumer, phase="consumer_check", name="ldd_consumer",
                       env=env, timeout=120, check=False)
    if sess.commands[-1]["exit_code"] == 0 and "librocksdb" in ldd_log.read_text(errors="replace"):
        raise RuntimeError("consumer resolved a system librocksdb instead of the built artifact")

    dbdir = consumer / "db"
    shutil.rmtree(dbdir, ignore_errors=True)
    for name in ("write", "verify", "delete", "final"):
        sess.run([str(binary), name, str(dbdir)], cwd=consumer, phase="consumer",
                 name=f"consumer_{name}", env=env, timeout=600)

    sess.write(
        "consumer_manifest.json",
        {
            "task_id": TASK_ID,
            "source": str(consumer_src),
            "binary": str(binary),
            "link_libraries": linked_with,
            "include_dir": str(install / "include"),
            "archive": str(install / "lib" / STATIC_LIB_NAME),
            "modes": ["write", "verify", "delete", "final"],
        },
    )

    sess.finish(
        features={
            "profile": PROFILE,
            "static_lib": True,
            "shared_lib": False,
            "db_basic_test": True,
            "table_test": False,
            "build_mode": mode or ["<upstream default>"],
            "assert_enabled_build": True,
            "installed_headers": True,
            "pkg_config_files": pkg_config,
            "consumer_static_link": True,
            "consumer_link_libraries": linked_with,
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
