#!/usr/bin/env python3
"""BUILDv1-C06: headless Blender (CPU Cycles) source-build driver.

  --help / -h   usage, no build
  doctor        verify manifest, source archive, prepared dependency cache
                (/workspace/cache/blender_modules) and required bootstrap
                tools against the real frozen release contents
  run           configure -- official headless preset + explicit LIBDIR +
                WITH_LIBS_PRECOMPILED=ON -- compile, install, freeze the
                exact CTest inventory, run the frozen CORE tests, then drive
                independent consumer Blender processes from the install tree.
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

TASK_ID = "BUILDv1-C06"
CACHE_DIR = Path("/workspace/cache/blender_modules")
REQUIRED_TOOLS = ("cmake", "ninja", "gcc", "g++", "python3")
LIBS_GITLINK_PATH = "lib/linux_x64"
REQUIRED_PY_TARGETS = (
    "bmesh_bevel", "bmesh_boolean", "blendfile_liblink", "blendfile_relationships",
)
CYCLES_GROUP = "cycles_mesh_cpu"
LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/"

# Real anchors inside lib/linux_x64 from the frozen lib-linux_x64 gitlink.
LIBS_ANCHOR_FILES = (
    ("epoxy/lib/libepoxy.a",
     "453c3b98a968ee3f3edf5f11090aea771042e2b2fa2cc42c8975dd7a154d0f97"),
)
LIBS_ANCHOR_DIRS = ("epoxy", "python")


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


def _check_gitlink_presence(manifest):
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


def _check_libs_bundle():
    libdir = _find_in_cache(LIBS_GITLINK_PATH)
    if libdir is None or not libdir.is_dir():
        return [
            f"cache:libs_bundle_missing:{CACHE_DIR / LIBS_GITLINK_PATH} "
            "(the precompiled dependency bundle is required)"
        ]
    problems = []
    for anchor_rel, want_sha in LIBS_ANCHOR_FILES:
        path = libdir / anchor_rel
        if not path.is_file():
            problems.append(f"cache:libs_anchor_missing:{path}")
            continue
        got = buildkit.digest(path)
        if got.lower() != want_sha.lower():
            problems.append(
                f"cache:libs_anchor_sha_mismatch:{path} (want {want_sha}, got {got})"
            )
    for anchor in LIBS_ANCHOR_DIRS:
        path = libdir / anchor
        if not path.is_dir():
            problems.append(f"cache:libs_dir_missing:{path}")
    return problems


def _lfs_records(manifest):
    recs = manifest.get("blender_lfs_objects")
    return recs if isinstance(recs, list) else []


def _lfs_get(rec, keys):
    for key in keys:
        val = rec.get(key)
        if val not in (None, ""):
            return val
    return None


def _lfs_candidates(rec, manifest):
    rel = _lfs_get(rec, ("path", "filename", "name", "file", "lfs_path"))
    if not rel:
        return []
    module = _lfs_get(rec, ("module", "repository", "repo", "gitlink", "target"))
    cands = []
    if module:
        cands.append(CACHE_DIR / module / rel)
    for gl in manifest.get("blender_gitlinked_inputs") or []:
        p = gl.get("path") if isinstance(gl, dict) else None
        if p:
            cands.append(CACHE_DIR / p / rel)
    cands.append(CACHE_DIR / rel)
    return cands


def _lfs_resolve(rec, manifest):
    for cand in _lfs_candidates(rec, manifest):
        if cand.is_file():
            return cand
    return None


def _check_lfs(manifest, sample_limit=8):
    records = _lfs_records(manifest)
    missing_sample = []
    problem_sample = []
    missing_count = 0
    problem_count = 0
    verified = 0
    hashed = 0
    size_checked = 0
    for rec in records:
        if not isinstance(rec, dict):
            continue
        path = _lfs_resolve(rec, manifest)
        if path is None:
            missing_count += 1
            if len(missing_sample) < sample_limit:
                cands = _lfs_candidates(rec, manifest)
                missing_sample.append(str(cands[0]) if cands else "<unknown>")
            continue
        want_bytes = _lfs_get(rec, ("bytes", "size", "size_bytes"))
        if isinstance(want_bytes, int):
            size_checked += 1
            got_bytes = path.stat().st_size
            if got_bytes != want_bytes:
                problem_count += 1
                if len(problem_sample) < sample_limit:
                    problem_sample.append(
                        f"lfs:size:{path} (want {want_bytes}, got {got_bytes})"
                    )
                continue
        with path.open("rb") as stream:
            head = stream.read(len(LFS_POINTER_PREFIX))
        if head == LFS_POINTER_PREFIX:
            problem_count += 1
            if len(problem_sample) < sample_limit:
                problem_sample.append(f"lfs:pointer:{path}")
            continue
        want_sha = _lfs_get(rec, ("sha256", "oid_sha256", "oid", "sha", "hash"))
        if isinstance(want_sha, str) and len(want_sha) == 64:
            hashed += 1
            got = buildkit.digest(path)
            if got.lower() != want_sha.lower():
                problem_count += 1
                if len(problem_sample) < sample_limit:
                    problem_sample.append(
                        f"lfs:sha:{path} (want {want_sha}, got {got})"
                    )
                continue
        verified += 1
    return {
        "declared": len(records),
        "verified": verified,
        "hashed": hashed,
        "size_checked": size_checked,
        "missing_count": missing_count,
        "problem_count": problem_count,
        "missing_sample": missing_sample,
        "problem_sample": problem_sample,
    }


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
    except Exception as exc:
        report["missing"] = [f"manifest:{exc}"]
        print(json.dumps(report, indent=2))
        return 78

    arc_missing, archive = _check_archive(input_dir, manifest)
    missing = list(arc_missing)
    missing += _check_tools()
    missing += _check_gitlink_presence(manifest)
    missing += _check_libs_bundle()

    lfs_summary = _check_lfs(manifest)
    if lfs_summary["missing_count"]:
        missing += [f"lfs:missing:{p}" for p in lfs_summary["missing_sample"]]
        extra = lfs_summary["missing_count"] - len(lfs_summary["missing_sample"])
        if extra > 0:
            missing.append(f"lfs:missing:+{extra} more")
    if lfs_summary["problem_count"]:
        missing += [f"lfs:bad:{p}" for p in lfs_summary["problem_sample"]]
        extra = lfs_summary["problem_count"] - len(lfs_summary["problem_sample"])
        if extra > 0:
            missing.append(f"lfs:bad:+{extra} more")

    report["source"] = manifest["source"]
    report["gitlinked_inputs"] = [
        {"path": gl.get("path"), "commit": gl.get("commit")}
        for gl in manifest.get("blender_gitlinked_inputs") or []
        if isinstance(gl, dict)
    ]
    report["lfs"] = lfs_summary
    report["source_archive_present"] = archive is not None
    report["missing"] = missing
    report["ready"] = not missing
    print(json.dumps(report, indent=2))
    return 0 if not missing else 78


def _cmake_configure_argv(src, build, install):
    libdir = src / "lib" / "linux_x64"
    return [
        "cmake", "-S", str(src), "-B", str(build), "-G", "Ninja",
        "-C", str(src / "build_files/cmake/config/blender_headless.cmake"),
        f"-DCMAKE_INSTALL_PREFIX={install}",
        f"-DLIBDIR={libdir}",
        "-DWITH_LIBS_PRECOMPILED=ON",
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
        if "tests/gtests" in exe:
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

    libdir = src / "lib" / "linux_x64"
    if not libdir.is_dir() or not any(libdir.iterdir()):
        raise RuntimeError(f"materialized precompiled library bundle is empty: {libdir}")

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
        "libs_precompiled": True,
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
    p_doc.add_argument("--input", required=True)
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
