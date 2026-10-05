#!/usr/bin/env python3
"""BUILDv1-C06: headless Blender (CPU Cycles) source-build driver.

Subcommands:
  --help / -h          Usage information, no build performed.
  doctor               Report exact missing source / tool / dependency items.
  run                  Configure, compile, install, test and consume the app.

Exit codes:
  doctor: 0 when everything required is present, 78 when anything is missing.
  run:    0 on success, 78 when doctor reports missing prerequisites.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tarfile
from pathlib import Path

import buildkit

TASK_ID = "BUILDv1-C06"

# Blender's prebuilt third-party libraries live in the lib/linux_x64 git
# submodule (see .gitmodules, update=none).  A from-source build needs these
# directories; they are not shipped inside the source tarball.
DEP_SUBDIRS = (
    "openexr", "openimageio", "opencolorio", "opensubdiv", "openvdb",
    "png", "jpeg", "boost", "python", "ffmpeg",
)

REQUIRED_TOOLS = ("cmake", "ninja", "gcc", "g++", "python3")

# Official CTest selectors for the frozen CORE profile (geometry / file / CPU).
TEST_SELECTOR = (
    "(blender_test_(bmesh_bevel|bmesh_boolean|mesh_join|mesh_validate|"
    "blendfile_liblink|blendfile_relationships))|(cycles_mesh_cpu)"
)


def _manifest(input_dir):
    path = Path(input_dir) / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"manifest.json not found under {input_dir}")
    return json.loads(path.read_text())


def _check_archive(input_dir, manifest):
    archive = Path(input_dir) / manifest["source"]["filename"]
    if not archive.is_file():
        return [f"source_archive:missing:{archive}"], None
    got = buildkit.digest(archive)
    want = manifest["source"]["sha256"]
    if got != want:
        return [f"source_archive:sha256_mismatch:{got}!={want}"], archive
    return [], archive


def _check_tools():
    return [f"tool:missing:{t}" for t in REQUIRED_TOOLS if shutil.which(t) is None]


def _check_dep_bundle(archive):
    if archive is None:
        return []
    with tarfile.open(archive) as tf:
        names = tf.getnames()
    top = None
    for n in names:
        parts = n.split("/")
        if len(parts) >= 2:
            top = parts[0]
            break
    if not top:
        return ["source_archive:unexpected_layout"]
    prefix = f"{top}/lib/linux_x64/"
    found = set()
    for n in names:
        if n.startswith(prefix):
            rest = n[len(prefix):].strip("/")
            if rest and "/" not in rest:
                found.add(rest)
    present = [d for d in DEP_SUBDIRS if d in found]
    if present:
        return []
    return [
        "dependency_bundle:missing:lib/linux_x64 "
        "(Blender prebuilt third-party libraries submodule with update=none; "
        "materialize it before invoking the build)"
    ]


def doctor(input_dir):
    report = {"task": TASK_ID, "input": str(input_dir), "ready": False, "missing": []}
    try:
        manifest = _manifest(input_dir)
    except Exception as exc:  # pragma: no cover - defensive
        report["missing"] = [f"manifest:{exc}"]
        print(json.dumps(report, indent=2))
        return 78
    missing = []
    arc_missing, archive = _check_archive(input_dir, manifest)
    missing += arc_missing
    missing += _check_tools()
    missing += _check_dep_bundle(archive)
    report["source"] = manifest["source"]
    report["missing"] = missing
    report["ready"] = not missing
    print(json.dumps(report, indent=2))
    return 0 if not missing else 78


def _cmake_configure_argv(src, build, install):
    return [
        "cmake", "-S", str(src), "-B", str(build), "-G", "Ninja",
        "-C", str(src / "build_files/cmake/config/blender_headless.cmake"),
        f"-DCMAKE_INSTALL_PREFIX={install}",
        "-DWITH_GTESTS=ON",
        "-DWITH_CYCLES=ON",
        "-DCYCLES_TEST_DEVICES=CPU",
        "-DWITH_CYCLES_DEVICE_CUDA=OFF",
        "-DWITH_CYCLES_DEVICE_OPTIX=OFF",
        "-DWITH_CYCLES_DEVICE_HIP=OFF",
        "-DWITH_CYCLES_DEVICE_ONEAPI=OFF",
        "-DWITH_CYCLES_CUDA_BINARIES=OFF",
        "-DWITH_CYCLES_HIP_BINARIES=OFF",
        "-DWITH_GPU_RENDER_TESTS=OFF",
        "-DWITH_GPU_COMPOSITOR_TESTS=OFF",
    ]


def run_pipeline(input_dir, output_dir, jobs):
    rc = doctor(input_dir)
    if rc != 0:
        sys.stderr.write(
            "Refusing to build: required source / tool / dependency items are "
            "missing (see doctor output above).  Materialize them and retry.\n"
        )
        return 78

    session = buildkit.Session(input_dir, output_dir, jobs=jobs)
    src = session.prepare()
    test_jobs = min(int(jobs), 2)

    session.run(_cmake_configure_argv(src, session.build, session.install),
                cwd=src, phase="configure", name="cmake_configure", timeout=5400)
    session.run(["cmake", "--build", str(session.build), "--parallel", str(session.jobs)],
                cwd=src, phase="build", name="cmake_build", timeout=14400)

    # Freeze the official CTest inventory before executing it.
    session.run(["ctest", "--test-dir", str(session.build), "-N"],
                cwd=src, phase="discover", name="ctest_discovery", timeout=900, check=False)

    session.run(["cmake", "--build", str(session.build), "--target", "install"],
                cwd=src, phase="install", name="cmake_install", timeout=5400)

    session.test("blender_target_sel",
                 ["ctest", "--test-dir", str(session.build), "-R", TEST_SELECTOR,
                  "--output-on-failure", "-j", str(test_jobs)],
                 cwd=src, parser="ctest_cases", timeout=7200)

    blender = next(
        (p for p in session.install.rglob("blender")
         if p.is_file() and os.access(p, os.X_OK)), None)
    if blender is None:
        raise RuntimeError("blender executable not found in install tree")

    workdir = session.consumer / "scene"
    workdir.mkdir(parents=True, exist_ok=True)
    consumer_dir = Path(__file__).resolve().parent / "consumer"
    produce = consumer_dir / "scene_produce.py"
    verify = consumer_dir / "scene_verify.py"

    session.run([str(blender), "--background", "--factory-startup",
                 "--python", str(produce), "--", str(workdir)],
                cwd=workdir, phase="consumer", name="blender_produce", timeout=1800)
    session.run([str(blender), "--background", "--factory-startup",
                 "--python", str(verify), "--", str(workdir)],
                cwd=workdir, phase="consumer", name="blender_verify", timeout=1800)

    png = workdir / "frame.png"
    if not png.is_file() or png.stat().st_size == 0:
        raise RuntimeError("consumer render output missing or empty")

    session.finish(features={
        "app": "blender",
        "headless": True,
        "cycles_device": "CPU",
        "gtest": True,
        "consumer": "scene_roundtrip+cycles_frame",
    })
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="main.py",
        description=f"{TASK_ID}: headless Blender CPU source-build driver.",
    )
    sub = parser.add_subparsers(dest="command")

    p_doc = sub.add_parser("doctor", help="report missing source/tool/dependency items")
    p_doc.add_argument("--input", required=True, help="directory holding manifest.json and source archive")

    p_run = sub.add_parser("run", help="configure, build, install, test and consume")
    p_run.add_argument("--input", required=True)
    p_run.add_argument("--output", required=True)
    p_run.add_argument("--jobs", type=int, default=4)

    args = parser.parse_args(argv)
    if args.command == "doctor":
        return doctor(args.input)
    if args.command == "run":
        return run_pipeline(args.input, args.output, min(args.jobs, 4))
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
