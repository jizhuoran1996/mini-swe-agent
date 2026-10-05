#!/usr/bin/env python3
"""BUILDv1-C08: Mesa LLVMpipe + EGL CPU software graphics stack builder."""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from buildkit import Session, digest

TESTS = [
    "util_tests",
    "process",
    "process_with_overrides",
    "lp_test_format",
    "lp_test_arit",
    "lp_test_blend",
    "lp_test_lerp",
    "lp_test_conv",
    "lp_test_printf",
]

REQUIRED_TOOLS = ["meson", "ninja", "python3", "pkg-config", "cc", "c++",
                  "gcc", "g++", "bison", "flex"]
REQUIRED_PKGS = ["libdrm", "expat", "zlib"]
LLVM_CANDS = ["llvm-config", "llvm-config-18", "llvm-config-17",
              "llvm-config-19", "llvm-config-20"]

EGL_C = r'''
#include <EGL/egl.h>
#include <GLES2/gl2.h>
#include <stdio.h>
#include <string.h>
int main(void) {
    EGLDisplay dpy = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    if (dpy == EGL_NO_DISPLAY) { printf("FAIL: eglGetDisplay\n"); return 1; }
    EGLint maj = 0, min = 0;
    if (!eglInitialize(dpy, &maj, &min)) { printf("FAIL: eglInitialize\n"); return 1; }
    printf("EGL_VERSION=%d.%d\n", maj, min);
    printf("EGL_VENDOR=%s\n", eglQueryString(dpy, EGL_VENDOR));
    EGLint cfg_attrs[] = {
        EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
        EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
        EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8,
        EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8,
        EGL_NONE
    };
    EGLConfig cfg; EGLint n = 0;
    if (!eglChooseConfig(dpy, cfg_attrs, &cfg, 1, &n) || n < 1) {
        printf("FAIL: eglChooseConfig n=%d\n", n); return 1;
    }
    EGLint pb[] = { EGL_WIDTH, 64, EGL_HEIGHT, 64, EGL_NONE };
    EGLSurface surf = eglCreatePbufferSurface(dpy, cfg, pb);
    if (surf == EGL_NO_SURFACE) { printf("FAIL: pbuffer\n"); return 1; }
    EGLint ctx_attrs[] = { EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE };
    EGLContext ctx = eglCreateContext(dpy, cfg, EGL_NO_CONTEXT, ctx_attrs);
    if (ctx == EGL_NO_CONTEXT) { printf("FAIL: createContext\n"); return 1; }
    if (!eglMakeCurrent(dpy, surf, surf, ctx)) {
        printf("FAIL: makeCurrent\n"); return 1;
    }
    printf("GL_VERSION=%s\n", (const char *)glGetString(GL_VERSION));
    printf("GL_RENDERER=%s\n", (const char *)glGetString(GL_RENDERER));
    printf("GL_VENDOR=%s\n", (const char *)glGetString(GL_VENDOR));
    glViewport(0, 0, 64, 64);
    glClearColor(0.25f, 0.5f, 0.75f, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT);
    glFinish();
    unsigned char px[4] = {0, 0, 0, 0};
    glReadPixels(0, 0, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, px);
    printf("READBACK=%u,%u,%u,%u\n", px[0], px[1], px[2], px[3]);
    if (px[0] < 40 || px[0] > 96)   { printf("FAIL: red\n"); return 2; }
    if (px[1] < 100 || px[1] > 155) { printf("FAIL: green\n"); return 2; }
    if (px[2] < 165 || px[2] > 220) { printf("FAIL: blue\n"); return 2; }
    if (px[3] != 255)               { printf("FAIL: alpha\n"); return 2; }
    if (!strstr((const char *)glGetString(GL_RENDERER), "llvmpipe")) {
        printf("FAIL: not llvmpipe\n"); return 3;
    }
    eglMakeCurrent(dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    eglDestroyContext(dpy, ctx);
    eglDestroySurface(dpy, surf);
    eglTerminate(dpy);
    printf("EGL_OFFSCREEN_OK\n");
    return 0;
}
'''


def _libdirs(install):
    out = []
    for c in ("lib", "lib64", "lib/x86_64-linux-gnu"):
        p = install / c
        if p.is_dir():
            out.append(p)
    return out


def _pcdirs(install):
    return [p / "pkgconfig" for p in _libdirs(install) if (p / "pkgconfig").is_dir()]


def doctor_missing(input_dir):
    input_dir = Path(input_dir)
    missing = []
    manifest_path = input_dir / "manifest.json"
    source = None
    if not manifest_path.is_file():
        missing.append({"kind": "source", "item": str(manifest_path),
                        "hint": "manifest.json not mounted"})
    else:
        try:
            source = json.loads(manifest_path.read_text()).get("source")
        except ValueError as exc:
            missing.append({"kind": "source", "item": str(manifest_path),
                            "hint": "manifest.json unreadable: %s" % exc})
    if source:
        arch = input_dir / source["filename"]
        if not arch.is_file():
            missing.append({"kind": "source", "item": str(arch),
                            "hint": "source archive not found"})
        else:
            try:
                if digest(arch) != source["sha256"]:
                    missing.append({"kind": "source", "item": str(arch),
                                    "hint": "sha256 mismatch"})
            except OSError as exc:
                missing.append({"kind": "source", "item": str(arch),
                                "hint": str(exc)})
    for tool in REQUIRED_TOOLS:
        if shutil.which(tool) is None:
            missing.append({"kind": "tool", "item": tool,
                            "hint": "not found on PATH"})
    if not any(shutil.which(t) for t in LLVM_CANDS):
        missing.append({"kind": "dependency", "item": "llvm-config",
                        "hint": "LLVM dev package required for llvmpipe"})
    if shutil.which("pkg-config"):
        for pkg in REQUIRED_PKGS:
            r = subprocess.run(["pkg-config", "--exists", pkg],
                               capture_output=True)
            if r.returncode != 0:
                missing.append({"kind": "dependency", "item": pkg,
                                "hint": "pkg-config module missing"})
    return missing


def meson_setup_argv(session):
    return [
        "meson", "setup", str(session.build), str(session.src),
        "--prefix=" + str(session.install),
        "--wrap-mode=nodownload",
        "--buildtype=release",
        "-Dgallium-drivers=llvmpipe",
        "-Dvulkan-drivers=",
        "-Dplatforms=",
        "-Dglx=disabled",
        "-Degl=enabled",
        "-Dllvm=enabled",
        "-Dbuild-tests=true",
        "-Dgallium-va=disabled",
        "-Dgallium-vdpau=disabled",
        "-Dgallium-xa=disabled",
        "-Dgallium-nine=false",
        "-Dgallium-opencl=disabled",
        "-Dgallium-rusticl=false",
        "-Dopengl=true",
        "-Dgles1=disabled",
        "-Dgles2=enabled",
    ]


def discover_tests(session):
    """Return list of (full_name, leaf_name) for every registered meson test."""
    names = []
    # Canonical source of truth: introspection JSON.
    log = session.run(["meson", "introspect", str(session.build), "--tests"],
                      cwd=session.build, phase="test_discovery",
                      name="meson_introspect_tests", timeout=600, check=False)
    text = log.read_text(errors="replace")
    start, end = text.find("["), text.rfind("]")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start:end + 1])
        except ValueError:
            data = None
        if isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict):
                    n = entry.get("name")
                    if isinstance(n, str) and n:
                        names.append((n, n.split(":")[-1]))
    if not names:
        # `meson test --list` prints TestSerialisation reprs in some releases.
        log = session.run(["meson", "test", "-C", str(session.build), "--list"],
                          cwd=session.build, phase="test_discovery",
                          name="meson_test_list", timeout=600)
        text = log.read_text(errors="replace")
        for match in re.finditer(r"name='([^']+)'", text):
            n = match.group(1)
            names.append((n, n.split(":")[-1]))
        if not names:
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                match = re.fullmatch(r"[A-Za-z0-9_.:+-]+", line)
                if match:
                    n = match.group(0)
                    names.append((n, n.split(":")[-1]))
    seen, unique = set(), []
    for full, base in names:
        if full not in seen:
            seen.add(full)
            unique.append((full, base))
    return unique


def _normalize(name):
    return name.lower().replace("_", "-")


def _resolve_selector(selector, entries):
    leaf = selector.split(":")[-1]
    for full, base in entries:
        if base == selector or full == selector:
            return full
    target = _normalize(leaf)
    for full, base in entries:
        if _normalize(base) == target or _normalize(full) == target:
            return full
    return None


def build_consumer(session):
    cdir = session.consumer / "egl_offscreen"
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "consumer.c").write_text(EGL_C)
    libdirs = _libdirs(session.install)
    pcdirs = _pcdirs(session.install)
    ld_path = ":".join(str(p) for p in libdirs)
    pc_path = ":".join(str(p) for p in pcdirs)
    inc = session.install / "include"
    env = {
        "PKG_CONFIG_PATH": pc_path,
        "LD_LIBRARY_PATH": ld_path,
        "LIBRARY_PATH": ld_path,
        "CPATH": str(inc),
    }
    argv = ["gcc", "-O2", "-Wall", "-o", "egl_consumer", "consumer.c",
            "-I" + str(inc)]
    for d in libdirs:
        argv.append("-L" + str(d))
    argv += ["-lEGL", "-lGLESv2"]
    session.run(argv, cwd=cdir, phase="consumer_build",
                name="egl_consumer_build", env=env, timeout=600)
    run_env = dict(env)
    run_env.update({
        "EGL_PLATFORM": "surfaceless",
        "EGL_LOG_LEVEL": "warning",
        "LIBGL_ALWAYS_SOFTWARE": "1",
        "GALLIUM_DRIVER": "llvmpipe",
        "MESA_LOADER_DRIVER_OVERRIDE": "llvmpipe",
        "MESA_NO_ERROR": "0",
    })
    session.run([str(cdir / "egl_consumer")], cwd=cdir, phase="consumer_run",
                name="egl_consumer_run", env=run_env, timeout=300)


def do_run(inp, out, jobs, build):
    missing = doctor_missing(inp)
    session = Session(inp, out, jobs)
    session.write("doctor.json", {"missing": missing, "ready": not missing,
                                  "jobs": session.jobs})
    if missing:
        print(json.dumps({"ready": False, "missing": missing}, indent=2))
        return 78
    if not build:
        print(json.dumps({"ready": True, "missing": []}, indent=2))
        return 0
    session.prepare()
    session.run(meson_setup_argv(session), cwd=session.src, phase="configure",
                name="meson_setup", timeout=1800)
    session.run(["meson", "compile", "-C", str(session.build),
                 "-j", str(session.jobs)],
                cwd=session.build, phase="build", name="meson_compile",
                timeout=10800)
    entries = discover_tests(session)
    available_base = sorted({b for _, b in entries})
    resolved = []
    unavailable = []
    for sel in TESTS:
        match = _resolve_selector(sel, entries)
        if match:
            resolved.append((sel, match))
        else:
            unavailable.append(sel)
    session.write("test_discovery.json", {
        "available": available_base,
        "resolved": [{"selector": s, "meson_name": m} for s, m in resolved],
        "unavailable": unavailable,
    })
    if not resolved:
        raise RuntimeError(
            "no frozen selectors resolve to upstream tests; available="
            + repr(available_base))
    session.run(["meson", "install", "-C", str(session.build)],
                cwd=session.build, phase="install", name="meson_install",
                timeout=900)
    test_env = {
        "GALLIUM_DRIVER": "llvmpipe",
        "MESA_LOADER_DRIVER_OVERRIDE": "llvmpipe",
        "LIBGL_ALWAYS_SOFTWARE": "1",
    }
    for selector, meson_name in resolved:
        session.test(selector,
                     ["meson", "test", "-C", str(session.build),
                      "--print-errorlogs",
                      "--num-processes", str(min(session.jobs, 2)),
                      meson_name],
                     cwd=session.build, timeout=1800, env=test_env)
    build_consumer(session)
    session.finish(features={
        "profile": "core",
        "gallium_drivers": ["llvmpipe"],
        "egl": True,
        "gles2": True,
        "vulkan": False,
        "zink": False,
        "frozen_selectors": TESTS,
        "resolved_selectors": [s for s, _ in resolved],
        "unavailable_selectors": unavailable,
        "consumer": "egl_offscreen_readback",
    })
    print("BUILDv1-C08 complete")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mesa-cpu-stack")
    sub = ap.add_subparsers(dest="cmd")
    d = sub.add_parser("doctor", help="check source/tool/dependency readiness")
    d.add_argument("--input", required=True)
    d.add_argument("--output", default="/workspace/output")
    r = sub.add_parser("run", help="build, install, test and verify")
    r.add_argument("--input", required=True)
    r.add_argument("--output", required=True)
    r.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args(argv)
    if args.cmd is None:
        ap.print_help()
        return 0
    if args.cmd == "doctor":
        return do_run(args.input, args.output, 4, build=False)
    return do_run(args.input, args.output, args.jobs, build=True)


if __name__ == "__main__":
    sys.exit(main())
