#!/usr/bin/env python3
"""BUILDv1-C06: headless Blender (CPU Cycles) source-build driver.

Subcommands:
  --help / -h   Usage information, no build performed.
  doctor        Inspect the locked manifest, the source archive, the prepared
dependency cache (/workspace/cache/blender_modules) and required tools.
Exit 0 when everything needed to build is present; exit 78 otherwise.
  run           Configure with the official headless preset, compile, install,
freeze the exact CTest inventory, run the frozen CORE tests
(C/C++ GTest targets + bmesh_bevel + bmesh_boolean + blendfile_liblink
+ blendfile_relationships + the complete cycles_mesh_cpu group), then
drive two independent consumer Blender processes from the installed tree.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tarfile
from pathlib import Path

import buildkit

TASK_ID = "BUILDv1-C06"

# Declared offline dependency cache (see contract.dependency_caches).
CACHE_DIR = Path("/workspace/cache/blender_modules")

# Bootstrap tools that must be resolvable on PATH to configure and build.
REQUIRED_TOOLS = ("cmake", "ninja", "gcc", "g++", "python3")

# Exact official python / file-geometry CTest targets frozen for CORE.
REQUIRED_PY_TARGETS = (
    "bmesh_bevel",
    "bmesh_boolean",
    "blendfile_liblink",
    "blendfile_relationships",
)
# Complete CPU Cycles render group.
CYCLES_GROUP = "cycles_mesh_cpu"


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


def _find_in_cache(rel):
    """Locate a path under the cache, tolerating an optional top-level prefix."""
    direct = CACHE_DIR / rel
    if direct.exists():
        return direct
    if CACHE_DIR.is_dir():
        for child in CACHE_DIR.iterdir():
            if child.is_dir():
                alt = child / rel
                if alt.exists():
                    return alt
    return None


def _check_cache(manifest):
    gitlinks = manifest.get("blender_gitlinked_inputs")
    if not gitlinks:
        return ["manifest:blender_gitlinked_inputs:not_declared"]
    if not CACHE_DIR.is_dir():
        return [f"cache_dir:missing:{CACHE_DIR}"]
    missing = []
    for gl in gitlinks:
        rel = gl.get("path")
        if not rel:
            missing.append(f"gitlink:missing_path:{gl}")
            continue
        found = _find_in_cache(rel)
        if found is None:
            missing.append(
                f"cache:missing:{CACHE_DIR / rel} "
                f"(gitlink {gl.get('repository')}@{gl.get('commit')}, "
                f"archive_sha256={gl.get('archive_sha256')})"
            )
            continue
        if found.is_dir():
            try:
                entries = list(found.iterdir())
            except OSError:
                entries = [found]
            if not entries:
                missing.append(f"cache:empty:{found}")
    return missing


def _check_lfs(manifest, sample=5):
    lfs = manifest.get("blender_lfs_objects") or []
    missing = []
    checked = 0
    for obj in lfs:
        if checked >= sample:
            break
        module = obj.get("module", "")
        rel = obj.get("path", "")
        declared_bytes = obj.get("bytes")
        mod_dir = _find_in_cache(module) if module else None
        if mod_dir is None:
            missing.append(f"lfs:module_missing:{module}")
            checked += 1
            continue
        full = mod_dir / rel
        if not full.is_file():
            missing.append(f"lfs:missing:{full}")
            checked += 1
            continue
        if declared_bytes and full.stat().st_size != declared_bytes:
            missing.append(
                f"lfs:size_mismatch:{full} (declared {declared_bytes}, "
                f"got {full.stat().st_size})"
            )
        checked += 1
    return missing


def doctor(input_dir):
    report = {
        "task": TASK_ID,
        "input": str(input_dir),
        "cache_dir": str(CACHE_DIR),
        "ready": False,
        "missing": [],
    }
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
    missing += _check_cache(manifest)
    missing += _check_lfs(manifest)

    report["source"] = manifest["source"]
    report["gitlinked_inputs"] = [
        {"path": gl.get("path"), "commit": gl.get("commit")}
        for gl in manifest.get("blender_gitlinked_inputs") or []
        if isinstance(gl, dict)
    ]
    report["lfs_object_count"] = len(manifest.get("blender_lfs_objects") or [])
    report["source_archive_present"] = archive is not None
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


def _materialize_cache(src, manifest):
    """Wire the prepared gitlink data into the freshly extracted source tree.

The locked `lib/linux_x64`, `release/datafiles/assets` and `tests/data` inputs
are shipped as dependency data under /workspace/cache/blender_modules (they
are update=none git submodules and therefore absent from the primary source
tarball).  They are attached to the source tree via symlinks or, when the
filesystem forbids that, a physical copy.
"""
    for gl in manifest.get("blender_gitlinked_inputs", []):
        rel = gl.get("path")
        if not rel:
            continue
        cache_entry = _find_in_cache(rel)
        if cache_entry is None:
            raise FileNotFoundError(f"cache entry missing for gitlink: {rel}")
        dst = src / rel
        if dst.is_symlink() or dst.is_file():
            dst.unlink()
        elif dst.is_dir():
            shutil.rmtree(dst, ignore_errors=True)
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            dst.symlink_to(cache_entry.resolve(), target_is_directory=cache_entry.is_dir())
        except OSError:
            if cache_entry.is_dir():
                shutil.copytree(cache_entry, dst, symlinks=True)
            else:
                shutil.copy2(cache_entry, dst)


def _discover_ctest_inventory(session):
    log = session.run(
        ["ctest", "--test-dir", str(session.build), "--show-only=json-v1"],
        cwd=session.src, phase="discover", name="ctest_inventory", timeout=900)
    return json.loads(log.read_text())


def _freeze_selectors(inventory, session):
    """Return (python_targets, gtest_names, py_present, cycles_present)."""
    tests = inventory.get("tests") or []
    build_str = str(session.build)
    py_exact = set(REQUIRED_PY_TARGETS)
    python_targets = []
    gtest_names = []
    py_present = set()
    cycles_present = False
    for t in tests:
        name = t.get("name")
        if not name:
            continue
        if name in py_exact:
            python_targets.append(name)
            py_present.add(name)
            continue
        if (name == CYCLES_GROUP or name.startswith(CYCLES_GROUP + "_")
                or name.startswith(CYCLES_GROUP + "/")
                or name.startswith(CYCLES_GROUP + ".")):
            python_targets.append(name)
            cycles_present = True
            continue
        cmd = t.get("command") or []
        if not cmd:
            continue
        exe = cmd[0]
        if "tests/gtests" in exe or "tests\\\\gtests" in exe:
            gtest_names.append(name)
            continue
        if build_str in exe and os.path.basename(exe).endswith("_test"):
            gtest_names.append(name)
    return python_targets, gtest_names, py_present, cycles_present


def _regex_for(names):
    return "^(" + "|".join(re.escape(n) for n in names) + ")$"


def _find_blender(install):
    for p in install.rglob("blender"):
        if p.is_file() and os.access(p, os.X_OK):
            return p
    return None


def run_pipeline(input_dir, output_dir, jobs):
    rc = doctor(input_dir)
    if rc != 0:
        sys.stderr.write(
            "Refusing to build: required source / tool / dependency items are "
            "missing (see doctor output above).  Materialize them and retry.\n"
        )
        return 78

    manifest = _manifest(input_dir)
    session = buildkit.Session(input_dir, output_dir, jobs=jobs)
    src = session.prepare()
    test_jobs = min(int(jobs), 2)

    _materialize_cache(src, manifest)

    session.run(_cmake_configure_argv(src, session.build, session.install),
                cwd=src, phase="configure", name="cmake_configure", timeout=5400)
    session.run(["cmake", "--build", str(session.build), "--parallel", str(session.jobs)],
                cwd=src, phase="build", name="cmake_build", timeout=14400)

    inventory = _discover_ctest_inventory(session)
    session.write("ctest_inventory.json", inventory)

    python_targets, gtests, py_present, cycles_present = _freeze_selectors(inventory, session)
    missing_reqs = [n for n in REQUIRED_PY_TARGETS if n not in py_present]
    if not cycles_present:
        missing_reqs.append(CYCLES_GROUP)
    if missing_reqs:
        raise RuntimeError(
            f"required official test targets were not registered by CTest: {missing_reqs}"
        )
    if not gtests:
        raise RuntimeError("no C/C++ GTest targets were registered by CTest")

    all_names = sorted(set(python_targets + gtests))
    session.write("frozen_selectors.json", all_names)

    session.run(["cmake", "--build", str(session.build), "--target", "install"],
                cwd=src, phase="install", name="cmake_install", timeout=5400)

    session.test("blender_core",
                 ["ctest", "--test-dir", str(session.build), "-R", _regex_for(all_names),
                  "--no-tests=error", "--output-on-failure", "-j", str(test_jobs)],
                 cwd=src, parser="ctest_cases", timeout=7200)

    blender = _find_blender(session.install)
    if blender is None:
        raise RuntimeError("blender executable not found in install tree")

    workdir = session.consumer / "scene"
    workdir.mkdir(parents=True, exist_ok=True)

    # Prove the packaged Python runtime is importable from the SDK alone.
    session.run(
        [str(blender), "--background", "--factory-startup", "--python-expr",
         "import bpy, sys; print('BVPYVERSION', bpy.app.version_string); "
         "print('PYVER', sys.version)"],
        cwd=workdir, phase="consumer", name="runtime_check", timeout=600)

    pkg_root = Path(__file__).resolve().parent
    produce = pkg_root / "consumer" / "scene_produce.py"
    verify = pkg_root / "consumer" / "scene_verify.py"

    session.run([str(blender), "--background", "--factory-startup",
                 "--python", str(produce), "--", str(workdir)],
                cwd=workdir, phase="consumer", name="blender_produce", timeout=1800)
    session.run([str(blender), "--background", "--factory-startup",
                 "--python", str(verify), "--", str(workdir)],
                cwd=workdir, phase="consumer", name="blender_verify", timeout=1800)

    png = workdir / "frame.png"
    second = workdir / "frame2.png"
    if not png.is_file() or png.stat().st_size == 0:
        raise RuntimeError("consumer render output missing or empty")
    if not second.is_file() or second.stat().st_size == 0:
        raise RuntimeError("reload render output missing or empty")

    session.finish(features={
        "app": "blender",
        "headless": True,
        "cycles_device": "CPU",
        "gtest": True,
        "python_targets": list(REQUIRED_PY_TARGETS) + [CYCLES_GROUP],
        "gtest_target_count": len(gtests),
        "consumer": "fresh_scene_save_reload+cycles_cpu_frame",
    })
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="main.py",
        description=f"{TASK_ID}: headless Blender CPU source-build driver.",
    )
    sub = parser.add_subparsers(dest="command")

    p_doc = sub.add_parser("doctor", help="report missing source/tool/dependency items")
    p_doc.add_argument("--input", required=True,
                       help="directory holding manifest.json and the source archive")

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
