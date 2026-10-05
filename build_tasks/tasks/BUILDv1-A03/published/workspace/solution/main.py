#!/usr/bin/env python3
"""BUILDv1-A03 (core profile).

Build libarchive + bsdtar from the frozen upstream release, run the official
CTest suites, install into a private prefix and independently consume the
freshly built artifacts from outside the source tree.
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

HERE = Path(__file__).resolve().parent

REQUIRED_TOOLS = ("cmake", "ctest", "make", "ninja", "gcc", "pkg-config")
REQUIRED_HEADERS = ("zlib.h", "bzlib.h", "lzma.h", "zstd.h")
HEADER_DIRS = (
    "/usr/include",
    "/usr/local/include",
    "/usr/include/x86_64-linux-gnu",
)

# Explicit, prefix-relative install dirs. The build container exports an empty
# CMAKE_INSTALL_LIBDIR, which makes libarchive derive an absolute
# "/pkgconfig" destination and breaks installation outside the prefix.
INSTALL_DIRS = {
    "CMAKE_INSTALL_BINDIR": "bin",
    "CMAKE_INSTALL_SBINDIR": "sbin",
    "CMAKE_INSTALL_LIBEXECDIR": "libexec",
    "CMAKE_INSTALL_LIBDIR": "lib",
    "CMAKE_INSTALL_INCLUDEDIR": "include",
    "CMAKE_INSTALL_OLDINCLUDEDIR": "include",
    "CMAKE_INSTALL_DATAROOTDIR": "share",
    "CMAKE_INSTALL_DATADIR": "share",
    "CMAKE_INSTALL_MANDIR": "share/man",
    "CMAKE_INSTALL_DOCDIR": "share/doc/libarchive",
    "CMAKE_INSTALL_SYSCONFDIR": "etc",
    "CMAKE_INSTALL_LOCALSTATEDIR": "var",
    "CMAKE_INSTALL_SHAREDSTATEDIR": "com",
    "CMAKE_INSTALL_PKGCONFIGDIR": "lib/pkgconfig",
}

BIG = bytes((i * 7 + 3) % 256 for i in range(65536))
FIXTURE = {
    "hello.txt": b"hello libarchive\n",
    "data/big.bin": BIG,
    "data/nested/x.txt": b"nested\n",
}
# bsdtar creates a directory entry for every directory it recurses into.
EXPECTED_DIRS = ("data", "data/nested")
EXPECTED_FILES = {
    "hello.txt": FIXTURE["hello.txt"],
    "data/big.bin": FIXTURE["data/big.bin"],
    "data/nested/x.txt": FIXTURE["data/nested/x.txt"],
}
EXPECTED_LINKS = {"symlink": "hello.txt", "hardlink": "hello.txt"}


def fnv1a(data, h=1469598103934665603):
    for byte in data:
        h ^= byte
        h = (h * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return "%016x" % h


def _norm(name):
    """Upstream tar readers may expose a directory as "data" or "data/" (or a
    deeply nested "data/nested" vs "data/nested/"). Normalise an optional
    single trailing slash so member lookup is format-stable."""
    return name[:-1] if name.endswith("/") and len(name) > 1 else name


def missing_items(input_dir):
    """Exact list of missing source / tool / dependency items."""
    missing = []
    manifest = input_dir / "manifest.json"
    if not manifest.is_file():
        missing.append("source:manifest.json")
    else:
        try:
            data = json.loads(manifest.read_text())
            archive = input_dir / data["source"]["filename"]
            if not archive.is_file():
                missing.append("source:" + str(archive))
            elif buildkit.digest(archive) != data["source"]["sha256"]:
                missing.append("source:sha256-mismatch:" + str(archive))
        except Exception as exc:  # noqa: BLE001 - report, never crash doctor
            missing.append("source:manifest-unreadable:%s" % exc)
    for tool in REQUIRED_TOOLS:
        if shutil.which(tool) is None:
            missing.append("tool:" + tool)
    for header in REQUIRED_HEADERS:
        if not any((Path(d) / header).is_file() for d in HEADER_DIRS):
            missing.append("dependency:" + header)
    return missing


def cmd_doctor(args):
    input_dir = Path(args.input).resolve()
    missing = missing_items(input_dir)
    report = {
        "task_id": "BUILDv1-A03",
        "profile": "core",
        "input": str(input_dir),
        "ready": not missing,
        "missing": missing,
    }
    print(json.dumps(report, indent=2))
    return 0 if not missing else 78


def _bsdtar(session, install, cons, argv, name, check=True, timeout=1800):
    env = {
        "LD_LIBRARY_PATH": str(install / "lib"),
        "TMPDIR": str(cons / "tmp"),
    }
    return session.run(
        [str(install / "bin" / "bsdtar")] + argv,
        cwd=cons,
        phase="consumer",
        name=name,
        env=env,
        timeout=timeout,
        check=check,
    )


def _last_exit(session):
    return session.commands[-1]["exit_code"]


def _parse_consumer(text):
    entries = {}
    total = None
    for line in text.splitlines():
        fields = line.split("\t")
        if fields[0] == "ENTRY" and len(fields) >= 7:
            entries[_norm(fields[1])] = {
                "kind": fields[2],
                "size": int(fields[3]),
                "hardlink": fields[4],
                "symlink": fields[5],
                "fnv": fields[6],
            }
        elif fields[0] == "TOTAL" and len(fields) >= 2:
            total = int(fields[1])
    return entries, total


def cmd_run(args):
    session = buildkit.Session(args.input, args.output, args.jobs)
    session.prepare()

    src, build = session.src, session.build
    install, cons = session.install, session.consumer
    jobs = session.jobs
    tjobs = min(2, jobs)

    (cons / "tmp").mkdir(parents=True, exist_ok=True)

    # Pin every CMAKE_INSTALL_* component dir to a prefix-relative value both in
    # the cache (command line) and in the process environment, so an inherited
    # empty CMAKE_INSTALL_LIBDIR can never produce an absolute destination.
    install_env = dict(INSTALL_DIRS)

    # ---------------------------------------------------------------- build
    session.run(
        [
            "cmake", "-S", str(src), "-B", str(build),
            "-DCMAKE_BUILD_TYPE=Release",
            "-DCMAKE_INSTALL_PREFIX=" + str(install),
            "-DCMAKE_INSTALL_RPATH=" + str(install / "lib"),
        ]
        + ["-D%s=%s" % (k, v) for k, v in sorted(INSTALL_DIRS.items())]
        + [
            "-DENABLE_TEST=ON",
            "-DENABLE_TAR=ON",
            "-DENABLE_CPIO=OFF",
            "-DENABLE_CAT=OFF",
            "-DENABLE_UNZIP=OFF",
            "-DENABLE_WERROR=OFF",
        ],
        cwd=src,
        phase="configure",
        name="cmake_configure",
        env=install_env,
        timeout=2400,
    )
    session.run(
        ["cmake", "--build", str(build), "--parallel", str(jobs)],
        cwd=build,
        phase="build",
        name="cmake_build",
        env=install_env,
        timeout=7200,
    )

    # ------------------------------------------------- official inventory
    inv_log = session.run(
        ["ctest", "--test-dir", str(build), "-N"],
        cwd=build,
        phase="inventory",
        name="ctest_inventory",
        timeout=600,
    )
    inv_text = inv_log.read_text(errors="replace")
    names = re.findall(r"Test\s+#\d+:\s+(\S+)", inv_text)
    session.write(
        "test_inventory.json",
        {
            "tool": "ctest -N",
            "discovered": len(names),
            "names": names,
            "source_log": str(inv_log.relative_to(session.output)),
        },
    )
    if not names:
        raise RuntimeError("empty official test inventory from ctest -N")

    # ---------------------------------------------------- official tests
    session.test(
        "ctest_official_suite",
        [
            "ctest", "--test-dir", str(build),
            "--output-on-failure", "--parallel", str(tjobs),
        ],
        cwd=build,
        parser="ctest_cases",
        env={"TMPDIR": str(cons / "tmp")},
        timeout=9600,
    )

    # ------------------------------------------------------------- install
    session.run(
        ["cmake", "--install", str(build)],
        cwd=build,
        phase="install",
        name="cmake_install",
        env=install_env,
        timeout=900,
    )

    bsdtar = install / "bin" / "bsdtar"
    header = install / "include" / "archive.h"
    libs = sorted(p for p in (install / "lib").glob("libarchive.so*"))
    pcfile = install / "lib" / "pkgconfig" / "libarchive.pc"
    if not bsdtar.is_file() or not header.is_file() or not libs or not pcfile.is_file():
        raise RuntimeError("install prefix is missing required artifacts")
    # Nothing may have leaked outside the private prefix.
    if Path("/pkgconfig").exists():
        raise RuntimeError("installation leaked outside the prefix: /pkgconfig")

    ver_log = _bsdtar(session, install, cons, ["--version"], "bsdtar_version", timeout=120)
    version_line = next(
        (ln.strip() for ln in ver_log.read_text(errors="replace").splitlines() if ln.strip()),
        "",
    )

    # ------------------------------------------------------- CLI fixture
    fixture = cons / "fixture"
    if fixture.exists():
        shutil.rmtree(fixture)
    for rel, payload in FIXTURE.items():
        target = fixture / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    if (fixture / "symlink").is_symlink() or (fixture / "symlink").exists():
        (fixture / "symlink").unlink()
    os.symlink("hello.txt", fixture / "symlink")
    hard = fixture / "hardlink"
    if hard.exists() or hard.is_symlink():
        hard.unlink()
    os.link(fixture / "hello.txt", hard)
    os.chmod(fixture / "hello.txt", 0o640)

    tar_archive = cons / "fixture.tar.gz"
    zip_archive = cons / "fixture.zip"
    _bsdtar(
        session, install, cons,
        ["-czf", str(tar_archive), "-C", str(fixture),
         "hello.txt", "data", "symlink", "hardlink"],
        "fixture_create_tar",
    )
    _bsdtar(
        session, install, cons,
        ["--format", "zip", "-cf", str(zip_archive), "-C", str(fixture),
         "hello.txt", "data"],
        "fixture_create_zip",
    )

    extract = cons / "extract"
    extract_zip = cons / "extract_zip"
    for path in (extract, extract_zip):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)
    _bsdtar(session, install, cons, ["-xpf", str(tar_archive), "-C", str(extract)],
            "fixture_extract_tar")
    _bsdtar(session, install, cons, ["-xpf", str(zip_archive), "-C", str(extract_zip)],
            "fixture_extract_zip")

    for rel, payload in FIXTURE.items():
        if (extract / rel).read_bytes() != payload:
            raise RuntimeError("tar restore mismatch: " + rel)
        if (extract_zip / rel).read_bytes() != payload:
            raise RuntimeError("zip restore mismatch: " + rel)
    if os.readlink(extract / "symlink") != "hello.txt":
        raise RuntimeError("symlink target not restored")
    if os.stat(extract / "hardlink").st_ino != os.stat(extract / "hello.txt").st_ino:
        raise RuntimeError("hardlink not preserved through bsdtar round trip")
    if (os.stat(extract / "hello.txt").st_mode & 0o777) != 0o640:
        raise RuntimeError("declared permissions not restored")

    # ------------------------------------------------- negative: corrupt
    good = tar_archive.read_bytes()
    corrupt = cons / "corrupt.tar.gz"
    corrupt.write_bytes(good[: max(64, len(good) * 3 // 5)])
    corrupt_out = cons / "corrupt_out"
    if corrupt_out.exists():
        shutil.rmtree(corrupt_out)
    corrupt_out.mkdir(parents=True)
    _bsdtar(session, install, cons, ["-xzf", str(corrupt), "-C", str(corrupt_out)],
            "corrupt_archive_must_fail", check=False, timeout=300)
    if _last_exit(session) == 0:
        raise RuntimeError("corrupt archive was extracted without an error")

    # -------------------------------------------------- C API consumer
    source = HERE / "consumer.c"
    if not source.is_file():
        raise RuntimeError("missing consumer source: " + str(source))
    shutil.copyfile(source, cons / "consumer.c")
    session.run(
        [
            "gcc", "-O2", "-Wall", "-Wextra", "-o", str(cons / "archive_consumer"),
            str(cons / "consumer.c"),
            "-I" + str(install / "include"),
            "-L" + str(install / "lib"),
            "-larchive",
            "-Wl,-rpath," + str(install / "lib"),
        ],
        cwd=cons,
        phase="consumer",
        name="consumer_compile",
        timeout=600,
    )
    api_env = {"LD_LIBRARY_PATH": str(install / "lib")}
    api_log = session.run(
        [str(cons / "archive_consumer"), str(tar_archive)],
        cwd=cons, phase="consumer", name="consumer_read_fixture",
        env=api_env, timeout=300,
    )
    entries, total = _parse_consumer(api_log.read_text(errors="replace"))

    # Members may be reported as "data" or "data/"; _norm() folds the optional
    # trailing slash while the type/kind assertion below stays strict.
    for name, payload in EXPECTED_FILES.items():
        entry = entries.get(_norm(name))
        if entry is None:
            raise RuntimeError("API consumer did not see member: " + name)
        if entry["kind"] != "file":
            raise RuntimeError("API member is not a regular file: %s (%s)" % (name, entry["kind"]))
        if entry["size"] != len(payload):
            raise RuntimeError("API member size mismatch: %s (%d != %d)"
                               % (name, entry["size"], len(payload)))
        if entry["fnv"] != fnv1a(payload):
            raise RuntimeError("API consumer content mismatch: " + name)
    for dirname in EXPECTED_DIRS:
        entry = entries.get(_norm(dirname))
        if entry is None or entry["kind"] != "dir":
            raise RuntimeError("API consumer did not see directory entry: " + dirname)
    for link_name, target in EXPECTED_LINKS.items():
        entry = entries.get(_norm(link_name))
        if entry is None:
            raise RuntimeError("API consumer did not see link entry: " + link_name)
        if link_name == "symlink":
            if entry["kind"] != "symlink" or entry["symlink"] != target:
                raise RuntimeError("API consumer symlink target mismatch: %r" % (entry,))
        else:
            if entry["kind"] != "hardlink" or entry["hardlink"] != target:
                raise RuntimeError("API consumer hardlink target mismatch: %r" % (entry,))
    expected_names = set(EXPECTED_DIRS) | set(EXPECTED_FILES) | set(EXPECTED_LINKS)
    if set(entries) != expected_names:
        raise RuntimeError("archive member set mismatch: %r" % sorted(entries))
    if total != len(expected_names):
        raise RuntimeError("unexpected entry count: %r" % total)

    session.run(
        [str(cons / "archive_consumer"), str(corrupt)],
        cwd=cons, phase="consumer", name="consumer_corrupt_must_fail",
        env=api_env, timeout=300, check=False,
    )
    if _last_exit(session) == 0:
        raise RuntimeError("API consumer accepted a corrupt archive")
    session.run(
        [str(cons / "archive_consumer"), str(cons / "does-not-exist.tar")],
        cwd=cons, phase="consumer", name="consumer_missing_must_fail",
        env=api_env, timeout=300, check=False,
    )
    if _last_exit(session) == 0:
        raise RuntimeError("API consumer accepted a missing archive")

    features = {
        "profile": "core",
        "programs": ["bsdtar"],
        "library": libs[-1].name,
        "pkg_config": str(pcfile.relative_to(install)),
        "version_line": version_line,
        "compression_backends": [
            token for token in ("zlib", "bz2lib", "liblzma", "libzstd")
            if token in version_line
        ],
        "verified_formats": ["pax/ustar tar via gzip", "zip"],
        "consumer_checks": [
            "bsdtar round trip: content, symlink target, hardlink inode, mode 0640",
            "C API member enumeration: regular files, directories, symlink and hardlink",
            "C API content digests (FNV-1a) and member sizes",
            "corrupt archive and missing archive both rejected",
        ],
    }
    session.write("feature_report.json", features)
    session.finish(features=features)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="solution/main.py",
        description="libarchive core-profile source build, test, install and consume",
    )
    sub = parser.add_subparsers(dest="command")

    run_parser = sub.add_parser("run", help="build, test, install and verify")
    run_parser.add_argument("--input", required=True)
    run_parser.add_argument("--output", required=True)
    run_parser.add_argument("--jobs", type=int, default=4)

    doc_parser = sub.add_parser("doctor", help="report missing source/tool/dependency items")
    doc_parser.add_argument("--input", required=True)

    args = parser.parse_args(argv)
    if args.command == "run":
        return cmd_run(args)
    if args.command == "doctor":
        return cmd_doctor(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
