#!/usr/bin/env python3
"""BUILDv1-B09 (frozen CORE profile).

Bootstrap a *stage1* Rust toolchain (rustc + target std + rustdoc) from the
frozen upstream source archive, install it into --output/install, run the
frozen const-generics UI directory with the newly built compiler, and consume
the installed toolchain from outside the source tree.

All build/configure/install/test/consumer commands go through buildkit.Session
so exit codes and full logs are preserved as evidence.
"""
import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

from buildkit import Session, digest

HERE = Path(__file__).resolve().parent
CONSUMER_SRC = HERE / "consumer"
TRIPLE = "x86_64-unknown-linux-gnu"
DEFAULT_STAGE0_ROOT = Path("/opt/bootstrap/rust")
FROZEN_RELEASE_PREFIX = "1.87.0"

REQUIRED_TOOLS = [
    "bash", "gcc", "g++", "cc", "ld", "ar", "cmake", "ninja",
    "python3", "rustc", "cargo", "rustdoc", "pkg-config", "make", "tar",
]
REQUIRED_SUBMODULE_FILES = [
    "library/backtrace/Cargo.toml",
    "library/stdarch/Cargo.toml",
]
LLVM_SUBMODULE_FILE = "src/llvm-project/llvm/CMakeLists.txt"
DEFAULT_STAGE0_MIN = "1.85.0"


# ---------------------------------------------------------------- toolchain --
def stage0_root():
    explicit = os.environ.get("B09_STAGE0_ROOT", "").strip()
    if explicit:
        return Path(explicit)
    if (DEFAULT_STAGE0_ROOT / "bin" / "rustc").is_file():
        return DEFAULT_STAGE0_ROOT
    return None


def stage0_bin():
    root = stage0_root()
    return str(root / "bin") if root else ""


def which_tool(name):
    sb = stage0_bin()
    path = (sb + os.pathsep if sb else "") + os.environ.get("PATH", "")
    return shutil.which(name, path=path)


def find_llvm_config():
    for name in ("llvm-config", "llvm-config-19", "llvm-config-18", "llvm-config-17"):
        p = which_tool(name)
        if p:
            return p
    for cand in ("/usr/lib/llvm-18/bin/llvm-config", "/usr/lib/llvm-17/bin/llvm-config",
                 "/usr/bin/llvm-config"):
        if Path(cand).is_file():
            return cand
    return None


def ver_tuple(text):
    parts = []
    for chunk in text.split("."):
        num = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(num) if num else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def rustc_version(binary):
    try:
        out = os.popen('"%s" --version' % binary).read()
    except OSError:
        return None
    m = re.search(r"rustc\s+(\d+\.\d+\.\d+)", out)
    return ver_tuple(m.group(1)) if m else None


def required_stage0(src_root):
    f = src_root / "src" / "stage0"
    if f.is_file():
        for t in f.read_text(errors="replace").split():
            if re.fullmatch(r"\d+\.\d+\.\d+", t):
                return t
    return DEFAULT_STAGE0_MIN


# ------------------------------------------------------------------- doctor --
def frozen_source_missing(input_dir):
    """Check the frozen archive/bootstrap context.

    Doctor never treats an un-extracted /workspace/src as a missing source
    item; extraction happens inside run().
    """
    items = []
    manifest_path = input_dir / "manifest.json"
    if not manifest_path.is_file():
        items.append("manifest: %s is missing" % manifest_path)
        return items
    try:
        manifest = json.loads(manifest_path.read_text())
    except ValueError as exc:
        items.append("manifest: %s is not valid JSON (%s)" % (manifest_path, exc))
        return items
    src = manifest.get("source", {})
    archive = input_dir / src.get("filename", "")
    if not src.get("filename"):
        items.append("manifest: source.filename is not declared")
    elif not archive.is_file():
        items.append("source archive: %s is missing" % archive)
    else:
        if src.get("bytes") is not None and archive.stat().st_size != src["bytes"]:
            items.append("source archive size mismatch: %s" % archive)
        if src.get("sha256") and digest(archive) != src["sha256"]:
            items.append("source archive sha256 mismatch: %s" % archive)

    for tool in REQUIRED_TOOLS:
        if not which_tool(tool):
            items.append("tool missing from PATH: %s" % tool)

    rustc = which_tool("rustc")
    if not rustc:
        items.append("stage0 rustc missing: no Rust bootstrap compiler found; "
                     "provision one under /opt/bootstrap/rust or set B09_STAGE0_ROOT")
    else:
        need = ver_tuple(required_stage0(input_dir))
        got = rustc_version(rustc)
        if got is None:
            items.append("stage0 rustc at %s cannot report a version" % rustc)
        elif got < need:
            items.append("stage0 rustc too old at %s: need >= %d.%d.%d, found %d.%d.%d"
                         % ((rustc,) + need + got))
    for extra in ("cargo", "rustdoc"):
        if not which_tool(extra):
            items.append("stage0 %s missing (bootstrap toolchain incomplete)" % extra)
    return items


def extracted_tree_missing(src_root):
    """Requirements that only apply once the archive is extracted."""
    items = []
    for rel in REQUIRED_SUBMODULE_FILES:
        if not (src_root / rel).is_file():
            items.append("submodule content missing: %s" % rel)
    llvm_src = src_root / LLVM_SUBMODULE_FILE
    if not llvm_src.is_file() and not find_llvm_config():
        items.append("LLVM: neither %s nor a usable llvm-config is present" % LLVM_SUBMODULE_FILE)
    vendor = src_root / "vendor"
    if not vendor.is_dir() or not any(vendor.iterdir()):
        items.append("cargo vendor directory missing or empty: %s" % vendor)
    if not (src_root / ".cargo" / "config.toml").is_file():
        items.append("source cargo config missing: %s" % (src_root / ".cargo" / "config.toml"))
    return items


# -------------------------------------------------------------------- build --
def build_env(extra=None):
    env = os.environ.copy()
    sb = stage0_bin()
    if sb:
        env["PATH"] = sb + os.pathsep + env.get("PATH", "")
    env.setdefault("RUST_BACKTRACE", "1")
    env["RUST_TEST_THREADS"] = "2"
    env["CARGO_NET_OFFLINE"] = "true"
    cargo_home = Path("/workspace/cache/cargo-home")
    cargo_home.mkdir(parents=True, exist_ok=True)
    env["CARGO_HOME"] = str(cargo_home)
    if extra:
        env.update({str(k): str(v) for k, v in extra.items()})
    return env


def ensure_cargo_source_replacement(src_root, env):
    """Verify offline vendored-source replacement before any compilation.

    The env argument is the exact environment handed to subprocesses; the
    frozen source's own `.cargo/config.toml` must already declare the
    vendored-source replacement.
    """
    cfg = src_root / ".cargo" / "config.toml"
    text = cfg.read_text(errors="replace")
    if "[source.crates-io]" not in text or "vendored-sources" not in text:
        raise RuntimeError("frozen source .cargo/config.toml does not declare "
                           "vendored-source replacement; refusing to build on a network path")
    if env.get("CARGO_NET_OFFLINE") != "true":
        raise RuntimeError("offline Cargo mode not enforced for build subprocesses")


def bootstrap_toml(install_dir, jobs, llvm_config, source_llvm, stage0):
    """Emit only fields the frozen 1.87.0 bootstrap accepts.

    `[build]` in Rust 1.87 accepts: build, description, host, target,
    build-dir, cargo, rustc, rustfmt, cargo-clippy, docs, ..., jobs, ...
    There is NO `rustdoc` key in `[build]`; stage0 rustdoc is discovered from
    the stage0 toolchain / PATH. `change-id` is omitted because it accepts
    only an integer (or absence).
    """
    j = max(1, min(int(jobs), 4))
    lines = [
        'profile = "compiler"',
        "",
        "[build]",
        'build = "%s"' % TRIPLE,
        'host = ["%s"]' % TRIPLE,
        'target = ["%s"]' % TRIPLE,
        "extended = false",
        "docs = false",
        "jobs = %d" % j,
    ]
    if stage0 is not None:
        lines += [
            'rustc = "%s"' % (stage0 / "bin" / "rustc"),
            'cargo = "%s"' % (stage0 / "bin" / "cargo"),
        ]
    lines += [
        "",
        "[install]",
        'prefix = "%s"' % install_dir,
        'sysconfdir = "%s/etc"' % install_dir,
        "",
        "[llvm]",
        "download-ci-llvm = false",
        'targets = "X86"',
        "link-jobs = 1",
        "",
        "[rust]",
        "download-rustc = false",
        "incremental = false",
        "debuginfo-level = 0",
        "debuginfo-level-std = 0",
        "debuginfo-level-tools = 0",
    ]
    # Only use a system LLVM when the frozen source submodule is absent, so the
    # official submodule is compiled whenever the full source ships it.
    if llvm_config and not source_llvm:
        lines += ["", "[target.%s]" % TRIPLE, 'llvm-config = "%s"' % llvm_config]
    return "\n".join(lines) + "\n"


def compiletest_counts(text):
    return {
        "passed": sum(int(m) for m in re.findall(r"test result: \w+\. (\d+) passed", text)),
        "failed": sum(int(m) for m in re.findall(r"(\d+) failed", text)),
        "ignored": sum(int(m) for m in re.findall(r"(\d+) ignored", text)),
    }


def provenance_check(installed_rustc, stage0_root_path, vv_text):
    """Confirm the installed rustc is the newly built source compiler.

    Official channel strings are 'dev'/'beta'/etc, so we never grep for a
    literal 'stage1' token. Instead we require the frozen release line, the
    host triple, and a binary digest different from the stage0 bootstrap.
    """
    if not installed_rustc.is_file():
        raise RuntimeError("installed rustc not found at %s" % installed_rustc)
    rel = re.search(r"^release:\s*(\S+)", vv_text, re.M)
    if not rel:
        raise RuntimeError("rustc -vV missing release line:\n" + vv_text)
    if not rel.group(1).startswith(FROZEN_RELEASE_PREFIX):
        raise RuntimeError("installed rustc release %r is not the frozen %s line"
                           % (rel.group(1), FROZEN_RELEASE_PREFIX))
    if TRIPLE not in vv_text:
        raise RuntimeError("installed rustc host triple mismatch:\n" + vv_text)
    if stage0_root_path is not None:
        stage0_rustc = stage0_root_path / "bin" / "rustc"
        if stage0_rustc.is_file() and digest(stage0_rustc) == digest(installed_rustc):
            raise RuntimeError("installed rustc is byte-identical to stage0; "
                               "the source build was not installed")


# ---------------------------------------------------------------------- run --
def cmd_run(args):
    input_dir = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()
    jobs = max(1, min(int(args.jobs), 4))

    missing = frozen_source_missing(input_dir)
    if missing:
        print("run: frozen archive/bootstrap not ready")
        for item in missing:
            print("  MISSING:", item)
        return 78

    sess = Session(input_dir, output_dir, jobs)
    sess.prepare()

    tree_missing = extracted_tree_missing(sess.src)
    if tree_missing:
        print("run: extracted source is missing required submodule/dependency payload")
        for item in tree_missing:
            print("  MISSING:", item)
        return 78

    stage0 = stage0_root()
    env = build_env()
    ensure_cargo_source_replacement(sess.src, env)

    source_llvm = (sess.src / LLVM_SUBMODULE_FILE).is_file()
    llvm_config = find_llvm_config()
    (sess.src / "bootstrap.toml").write_text(
        bootstrap_toml(sess.install, jobs, llvm_config, source_llvm, stage0))

    # 1) build stage1 compiler + target std + rustdoc from frozen source.
    sess.run([sys.executable, "x.py", "build", "--stage", "1", "-j", str(jobs)],
             cwd=sess.src, phase="configure+build", name="x_py_build_stage1",
             env=env, timeout=10800)

    # 2) install the stage1 toolchain. Only newly built stage1 rustc/std/rustdoc
    #    are installed; stage0 rustc/cargo/rustdoc are build dependencies and
    #    are never copied into the delivered install tree.
    sess.run([sys.executable, "x.py", "install", "--stage", "1"],
             cwd=sess.src, phase="install", name="x_py_install_stage1",
             env=env, timeout=2700)

    # 3) official frozen const-generics UI directory, forced rerun, on stage1.
    log = sess.test("ui_const_generics",
                    [sys.executable, "x.py", "test", "--stage", "1",
                     "tests/ui/const-generics", "--force-rerun"],
                    cwd=sess.src, parser="auto", env=env, timeout=5400)
    counts = compiletest_counts(log.read_text(errors="replace"))
    sess.write("official_test_report.json", {
        "selector": "tests/ui/const-generics", "stage": 1,
        "counts": counts, "log": str(log.name)})
    if counts["passed"] <= 0:
        raise RuntimeError("no const-generics UI cases passed; refusing to claim coverage")

    # 4) consume the installed toolchain strictly outside the source tree.
    consumer = Path("/workspace/consumer")
    consumer.mkdir(parents=True, exist_ok=True)
    if CONSUMER_SRC.is_dir():
        for item in CONSUMER_SRC.iterdir():
            target = consumer / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)

    rustc = sess.install / "bin" / "rustc"
    rustdoc = sess.install / "bin" / "rustdoc"
    cenv = {"LD_LIBRARY_PATH": str(sess.install / "lib")}

    vv = sess.run([str(rustc), "-vV"], cwd=consumer, phase="consumer",
                  name="rustc_vV", env=cenv, timeout=300)
    provenance_check(rustc, stage0, vv.read_text(errors="replace"))

    sysroot_log = sess.run([str(rustc), "--print", "sysroot"], cwd=consumer,
                           phase="consumer", name="rustc_sysroot", env=cenv, timeout=300)
    sysroot = sysroot_log.read_text(errors="replace").strip()
    if str(sess.install) not in sysroot:
        raise RuntimeError("sysroot %r does not point at the delivered install" % sysroot)
    std_rlib = Path(sysroot) / "lib" / "rustlib" / TRIPLE / "lib"
    if not std_rlib.is_dir() or not any(std_rlib.glob("libstd*")):
        raise RuntimeError("installed sysroot lacks target std for %s: %s" % (TRIPLE, std_rlib))

    # positive consumer: generics, collections, threads, file IO.
    sess.run([str(rustc), "--edition", "2021", "-O", "good.rs", "-o", "good"],
             cwd=consumer, phase="consumer", name="consumer_build_good", env=cenv, timeout=600)
    sess.run([str(consumer / "good")], cwd=consumer, phase="consumer",
             name="consumer_run_good", env=cenv, timeout=300)

    # negative consumer: must be rejected by the delivered compiler.
    bad = sess.run([str(rustc), "--edition", "2021", "bad.rs", "-o", "bad"],
                   cwd=consumer, phase="consumer", name="consumer_build_bad",
                   env=cenv, timeout=600, check=False)
    bad_text = bad.read_text(errors="replace")
    if sess.commands[-1]["exit_code"] == 0:
        raise RuntimeError("delivered rustc accepted a borrow-check violation")
    if "E0505" not in bad_text and "borrow" not in bad_text.lower():
        raise RuntimeError("negative consumer failed for an unrelated reason:\n" + bad_text[-4000:])

    # cross-crate ABI consumer: build a lib, link a dependent binary.
    sess.run([str(rustc), "--edition", "2021", "--crate-type", "lib",
              "--crate-name", "calc", "calc.rs", "-o", "libcalc.rlib"],
             cwd=consumer, phase="consumer", name="consumer_build_calc_lib", env=cenv, timeout=600)
    sess.run([str(rustc), "--edition", "2021", "use_calc.rs", "--extern",
              "calc=libcalc.rlib", "-o", "use_calc"],
             cwd=consumer, phase="consumer", name="consumer_build_use_calc", env=cenv, timeout=600)
    sess.run([str(consumer / "use_calc")], cwd=consumer, phase="consumer",
             name="consumer_run_use_calc", env=cenv, timeout=300)

    # rustdoc consumer: generate browsable HTML and assert expected items.
    doc_out = consumer / "doc_out"
    sess.run([str(rustdoc), "--edition", "2021", "--crate-name", "consumer_doc",
              "lib_doc.rs", "-o", str(doc_out)],
             cwd=consumer, phase="consumer", name="consumer_rustdoc", env=cenv, timeout=600)
    index = doc_out / "consumer_doc" / "index.html"
    if not index.is_file():
        raise RuntimeError("rustdoc did not produce %s" % index)
    html = index.read_text(errors="replace")
    if "add" not in html or "Consumer arithmetic helpers" not in html:
        raise RuntimeError("rustdoc output is missing expected documented items")

    if not any(p.is_file() for p in sess.install.rglob("rustc")):
        raise RuntimeError("no rustc was installed; stage1 install produced nothing")

    sess.finish(features={
        "profile": "core", "stage": 1, "host_triple": TRIPLE,
        "release_prefix": FROZEN_RELEASE_PREFIX,
        "llvm_mode": "source-llvm" if source_llvm else "system-llvm-config",
        "llvm_config": llvm_config or "",
        "official_test": "tests/ui/const-generics",
        "official_counts": counts,
    })
    print("BUILDv1-B09 core: stage1 toolchain built, installed, tested and consumed")
    return 0


def cmd_doctor(args):
    missing = frozen_source_missing(Path(args.input).resolve())
    if missing:
        print("doctor: NOT READY")
        for item in missing:
            print("  MISSING:", item)
        return 78
    print("doctor: READY")
    print("  frozen source archive: present and verified")
    print("  stage0 bootstrap toolchain: present at %s" % stage0_root())
    print("  build tools: present")
    print("  llvm at build time: %s" % (find_llvm_config() or "source submodule"))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="BUILDv1-B09 core: bootstrap a stage1 Rust toolchain from frozen source.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="build, install, test and consume the stage1 toolchain")
    run.add_argument("--input", default="/workspace/input")
    run.add_argument("--output", default="/workspace/output")
    run.add_argument("--jobs", type=int, default=4)
    run.set_defaults(func=cmd_run)
    doc = sub.add_parser("doctor", help="report missing source/tool/dependency items")
    doc.add_argument("--input", default="/workspace/input")
    doc.set_defaults(func=cmd_doctor)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
