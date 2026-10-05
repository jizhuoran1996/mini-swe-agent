#!/usr/bin/env python3
"""BUILDv1-A01 (core profile): build, test, install and independently consume zlib v1.3.1."""
import argparse
import json
import shutil
import sys
from pathlib import Path

from buildkit import Session
from buildkit import digest as sha256_digest

HERE = Path(__file__).resolve().parent
ZLIB_VERSION = "1.3.1"
TOOLS = [
    ("C compiler", ["gcc", "cc"]),
    ("make", ["make"]),
    ("POSIX shell", ["sh"]),
    ("sed", ["sed"]),
    ("awk", ["awk"]),
    ("ar", ["ar"]),
    ("ranlib", ["ranlib"]),
    ("tar", ["tar"]),
]


def make_fixture(path, size=262144):
    """Deterministic binary fixture: pseudo-random bytes plus structured and zero regions."""
    data = bytearray()
    x = 0x12345678
    for i in range(size):
        x = (1103515245 * x + 12345) & 0xFFFFFFFF
        b = (x >> 16) & 0xFF
        if i % 997 < 300:
            b = i & 0xFF
        elif i % 1493 < 200:
            b = 0
        data.append(b)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(data))
    return path


def header_version(header):
    for line in header.read_text(errors="replace").splitlines():
        if line.startswith("#define ZLIB_VERSION"):
            return line.split('"')[1]
    return None


def doctor(input_dir):
    missing = []
    inp = Path(input_dir)
    manifest_path = inp / "manifest.json"
    if not manifest_path.is_file():
        missing.append("source: manifest.json missing at %s" % manifest_path)
        return missing
    try:
        manifest = json.loads(manifest_path.read_text())
    except Exception as exc:
        missing.append("source: manifest.json unreadable: %s" % exc)
        return missing
    source = manifest.get("source", {})
    archive = inp / source.get("filename", "source.tar.gz")
    if not archive.is_file():
        missing.append("source: archive missing at %s" % archive)
    else:
        if sha256_digest(archive) != source.get("sha256"):
            missing.append("source: sha256 mismatch for %s" % archive)
    for label, candidates in TOOLS:
        if not any(shutil.which(name) for name in candidates):
            missing.append("tool: %s (%s) not found on PATH" % (label, " or ".join(candidates)))
    consumer = HERE / "consumer.c"
    if not consumer.is_file():
        missing.append("dependency: consumer source missing at %s" % consumer)
    return missing


def cmd_doctor(args):
    missing = doctor(args.input)
    if missing:
        for item in missing:
            print("MISSING " + item)
        print("doctor: NOT READY (%d missing items)" % len(missing))
        return 78
    print("doctor: READY (source, tools and consumer dependency present)")
    return 0


def cmd_run(args):
    session = Session(args.input, args.output, args.jobs)
    missing = doctor(args.input)
    if missing:
        for item in missing:
            print("MISSING " + item)
        raise RuntimeError("doctor reported missing items; refusing to run")

    session.prepare()
    src = session.src
    install = session.install
    jobs = str(session.jobs)
    env = {"LC_ALL": "C", "LANG": "C"}

    # 1. configure to a private prefix
    session.run(["./configure", "--prefix=" + str(install)], cwd=src,
                phase="configure", name="configure", env=env)

    # 2. full build (static + shared libraries and the bundled example programs)
    session.run(["make", "-j", jobs], cwd=src, phase="build", name="make_all", env=env)
    session.run(["make", "-j", jobs, "example", "minigzip"], cwd=src, phase="build",
                name="make_programs", env=env, check=False)

    # 3. official upstream self-test used by the core profile
    session.test("teststatic", ["make", "teststatic"], cwd=src, env=env, timeout=1800)

    # 4. install headers, libraries, man page and pkg-config metadata
    session.run(["make", "install"], cwd=src, phase="install", name="make_install", env=env)

    header = install / "include" / "zlib.h"
    static_lib = install / "lib" / "libz.a"
    if not header.is_file() or not static_lib.is_file():
        raise RuntimeError("install prefix is missing zlib.h or libz.a")

    # 5. independent consumer built outside the source tree, statically linked to this round's libz.a
    consumer_dir = session.consumer
    fixture = make_fixture(consumer_dir / "fixture.bin")
    consumer_src = consumer_dir / "consumer.c"
    shutil.copyfile(HERE / "consumer.c", consumer_src)
    consumer_bin = consumer_dir / "consumer_static"
    session.run(["gcc", "-O2", "-Wall", "-I", str(install / "include"),
                 "-o", str(consumer_bin), str(consumer_src), str(static_lib)],
                cwd=consumer_dir, phase="consumer", name="build_consumer_static", env=env)
    run_log = session.run([str(consumer_bin), str(fixture), str(consumer_dir / "roundtrip.gz")],
                          cwd=consumer_dir, phase="consumer", name="run_consumer_static",
                          env=env, timeout=600)
    report = run_log.read_text(errors="replace")
    if "consumer failures: 0" not in report:
        raise RuntimeError("consumer did not report full success:\n" + report[-4000:])

    version = header_version(header)
    if version != ZLIB_VERSION:
        raise RuntimeError("installed header version %r != %r" % (version, ZLIB_VERSION))

    pkgconfig = sorted(str(p.relative_to(install)) for p in install.rglob("zlib.pc"))
    session.write("install_identity.json", {
        "header_version": version,
        "static_lib": str(static_lib.relative_to(install)),
        "static_lib_sha256": sha256_digest(static_lib),
        "pkgconfig_files": pkgconfig,
        "installed_tree": sorted(str(p.relative_to(install)) for p in install.rglob("*") if p.is_file()),
    })
    session.write("consumer_report.json", {
        "static_consumer_source": "solution/consumer.c",
        "compile_argv": ["gcc", "-O2", "-Wall", "-I", "<install>/include", "-o", "consumer_static",
                         "consumer.c", "<install>/lib/libz.a"],
        "fixture_bytes": fixture.stat().st_size,
        "checks": [line for line in report.splitlines() if line.startswith(("ok -", "FAIL -", "consumer failures"))],
        "all_passed": True,
    })

    session.finish(features={
        "profile": "core",
        "static_library": True,
        "official_selector": "teststatic",
        "consumer_static_linked_against_new_libz_a": True,
        "install_archive": "install.tar.gz",
    })
    print("BUILDv1-A01 core: zlib %s built, teststatic run, installed and consumed." % version)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Build, test, install and consume zlib %s (BUILDv1-A01 core profile)." % ZLIB_VERSION)
    sub = parser.add_subparsers(dest="command")
    run = sub.add_parser("run", help="configure, build, run teststatic, install and verify consumers")
    run.add_argument("--input", required=True, help="read-only input directory holding manifest.json and source.tar.gz")
    run.add_argument("--output", required=True, help="writable output directory for logs, artifacts and install prefix")
    run.add_argument("--jobs", type=int, default=4, help="build parallelism (capped at 4)")
    doc = sub.add_parser("doctor", help="list missing source/tool/dependency items (78 if any)")
    doc.add_argument("--input", required=True, help="read-only input directory")
    args = parser.parse_args(argv)
    if args.command == "run":
        return cmd_run(args)
    if args.command == "doctor":
        return cmd_doctor(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
