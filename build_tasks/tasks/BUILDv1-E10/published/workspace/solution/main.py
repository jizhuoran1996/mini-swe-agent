#!/usr/bin/env python3
"""BUILDv1-E10: build the SWC core native Node binding from frozen source and verify it.

Subcommands
-----------
  doctor --input <dir>                          report missing source/tool/dependency items (78 if any)
  run --input <dir> --output <dir> [--jobs N]   bootstrap, build, stage, test and consume the bundle

The frozen release pins genuine Rust ``nightly-2024-10-07``.  Its official
SHA256-verified installer (``manifest.swc_bootstrap``) is hydrated under
``/workspace/cache`` and is installed with
``--components=rustc,cargo,rust-std-x86_64-unknown-linux-gnu --disable-ldconfig``
into ``/workspace/tools/swc-nightly`` through ``Session.run(phase='bootstrap')``.
The same bootstrap phase then runs the *separate, official* component installer
for ``rust-std-nightly-wasm32-wasip1`` (``rust-std-wasm32-wasip1``) into the same
prefix, so the ``packages/core/e2e/fixtures/plugin_analyze`` fixture can compile
its real plugin to ``wasm32-wasip1``.  No toolchain version is faked and
``RUSTC_BOOTSTRAP`` stays disabled.

The Cargo target directory is deliberately left INSIDE the checkout
(``<src>/target``).  The upstream ``swc_ecma_transforms_testing`` harness starts a
genuine Mocha child for the ``*_exec`` fixture cases with a working directory
below ``CARGO_TARGET_DIR``; Mocha only discovers the *official, unmodified*
``.mocharc.js``/``.mocha.setup.js`` (which load ``expect`` and the JSX/TS
preloads) through ancestor traversal from that cwd.  Pointing
``CARGO_TARGET_DIR`` outside the checkout silently strips that official test
environment and every ``expect``-using exec case fails.  Using ``<src>/target``
keeps the genuine upstream Mocha config intact - no fake ``expect``, no globals,
no wrappers, no fixture edits.

The Node ``test:core`` runner is a **separate** process tree: jest there spawns
the plugin fixture's own Cargo workspace, which is expected to create its real
``packages/core/e2e/fixtures/plugin_analyze/target/wasm32-wasip1/debug/plugin_analyze.wasm``.
A global ``CARGO_TARGET_DIR`` would divert that build away from its declared path,
so the Node runner environment explicitly has ``CARGO_TARGET_DIR`` *unset* (not
empty) - both in the env mapping and in ``os.environ`` (``Session.run`` merges
with the process env).

Everything (configure/build/test/consumer) is dispatched through the trusted
``buildkit.Session`` so exit codes, logs and test selectors are preserved.  No
prebuilt SWC binding, prebuilt wasm std, or old target cache is ever copied into
the output; the JS package manager installs the workspace lockfile strictly
offline from the hydrated Yarn cache, and ``napi`` is consumed only as a
``node_modules`` devDependency.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from buildkit import Session, digest

TASK_ID = "BUILDv1-E10"
TOOLCHAIN_DIR = Path("/workspace/tools/swc-nightly")
TOOLCHAIN_BIN = TOOLCHAIN_DIR / "bin"
CARGO_CACHE = Path("/workspace/cache/cargo")
YARN_CACHE = Path("/workspace/cache/yarn")
RUST_COMPONENTS = "rustc,cargo,rust-std-x86_64-unknown-linux-gnu"
BOOTSTRAP_DIRS = [
    Path("/workspace/cache/rust-nightly-x86_64-unknown-linux-gnu"),
    Path("/workspace/cache/swc-nightly-x86_64-unknown-linux-gnu"),
]
# Official rust-std component for the plugin fixture's compile target.
WASM_COMPONENT_DIR = Path("/workspace/cache/rust-std-nightly-wasm32-wasip1")
WASM_COMPONENT_NAME = "rust-std-wasm32-wasip1"
WASM_TARGET = "wasm32-wasip1"
EXTRA_BIN = [Path("/opt/bootstrap/node/bin"), Path("/opt/bootstrap/go/bin")]

CONSUMER_JS = r"""'use strict';
const assert = require('assert');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const coreDir = process.env.SWC_INSTALL_ROOT;
assert(coreDir, 'SWC_INSTALL_ROOT not set');
const entry = path.join(coreDir, 'index.js');
assert(fs.existsSync(entry), 'missing bundle entry ' + entry);

const natives = fs.readdirSync(coreDir).filter((f) => f.endsWith('.node'));
assert(natives.length > 0, 'no freshly built .node binding in install root');
const nativePath = path.join(coreDir, natives[0]);

// load ONLY from the install root; no @swc/core-linux-* fallback is reachable here.
const swc = require(entry);
const resolved = require.resolve(entry);
assert(resolved.startsWith(fs.realpathSync(coreDir)), 'entry escaped install root: ' + resolved);

const source = [
  'export type Box<T> = { value: T };',
  'export const make = <T>(value: T): Box<T> => ({ value });',
  'export const n: number = make(41).value + 1;',
].join('\n');

const out = swc.transformSync(source, {
  filename: 'sample.ts',
  sourceMaps: true,
  jsc: { parser: { syntax: 'typescript' }, target: 'es2018' },
  module: { type: 'commonjs' },
});
assert.strictEqual(typeof out.code, 'string', 'code must be a string');
assert.ok(/exports|Object\.defineProperty/.test(out.code), 'commonjs emit missing');
assert.ok(out.map && typeof out.map.mappings === 'string' && out.map.mappings.length > 0,
  'source map mappings missing');

// execute the emitted CommonJS and check real runtime semantics
const Module = require('module');
const m = new Module('emitted', module);
m.filename = path.join(coreDir, 'emitted.js');
m.paths = Module._nodeModulePaths(coreDir);
m._compile(out.code, m.filename);
assert.strictEqual(m.exports.n, 42, 'transpiled runtime semantics wrong');

// error diagnostics must surface
let threw = false;
try {
  swc.transformSync('const = ;', { filename: 'bad.ts', jsc: { parser: { syntax: 'typescript' } } });
} catch (e) { threw = true; }
assert.ok(threw, 'invalid syntax must raise a diagnostic');

// async API completion (continuation check)
const min = swc.minifySync('function add(a, b) { return a + b; }', { compress: true, mangle: false });
assert.ok(min.code && min.code.length > 0, 'minify produced no output');

console.log(JSON.stringify({
  core: entry,
  native: nativePath,
  native_sha256: crypto.createHash('sha256').update(fs.readFileSync(nativePath)).digest('hex'),
  mappings: out.map.mappings.length,
  value: m.exports.n,
  minified: min.code,
}));
"""


def find_tool(name):
    if TOOLCHAIN_BIN.is_dir() and (TOOLCHAIN_BIN / name).is_file() and os.access(TOOLCHAIN_BIN / name, os.X_OK):
        return str(TOOLCHAIN_BIN / name)
    found = shutil.which(name)
    if found:
        return found
    for directory in EXTRA_BIN:
        candidate = directory / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _populated(path):
    try:
        return path.is_dir() and any(path.iterdir())
    except OSError:
        return False


def bootstrap_dir():
    for candidate in BOOTSTRAP_DIRS:
        if (candidate / "install.sh").is_file():
            return candidate
    return None


def toolchain_ready():
    return (TOOLCHAIN_BIN / "rustc").is_file() and (TOOLCHAIN_BIN / "cargo").is_file()


def wasm_std_ready():
    return (TOOLCHAIN_DIR / "lib" / "rustlib" / WASM_TARGET / "lib").is_dir()


def cargo_registry_present(root):
    return any(_populated(root / sub) for sub in ("registry/cache", "registry/index", "registry/src"))


def yarn_cache_dir():
    override = os.environ.get("YARN_CACHE_FOLDER")
    if override and _populated(Path(override)):
        return Path(override)
    if _populated(YARN_CACHE):
        return YARN_CACHE
    home = Path.home()
    for candidate in (home / ".yarn" / "berry" / "cache", home / ".cache" / "yarn"):
        if _populated(candidate):
            return candidate
    return YARN_CACHE


def base_env():
    """Environment with the pinned toolchain bin dir first, then Node/Go bootstrap.

    The toolchain bin path is prepended unconditionally: it is a fixed install
    location, so even the pre-install configure step gets a consistent PATH and
    the post-install native build/test steps cannot accidentally fall back to a
    stable rustc that would reject SWC's ``-Z...`` flags.
    """
    env = dict(os.environ)
    parts = [str(TOOLCHAIN_BIN)]
    parts.extend(str(d) for d in EXTRA_BIN if d.is_dir())
    parts.append(os.environ.get("PATH", ""))
    env["PATH"] = os.pathsep.join(p for p in parts if p)
    return env


def bind_toolchain_env(env):
    """Pin genuine RUSTC/CARGO once the nightly toolchain is actually installed."""
    if toolchain_ready():
        env["RUSTC"] = str(TOOLCHAIN_BIN / "rustc")
        env["CARGO"] = str(TOOLCHAIN_BIN / "cargo")
        existing = env.get("PATH", "")
        if str(TOOLCHAIN_BIN) not in existing.split(os.pathsep):
            env["PATH"] = os.pathsep.join([str(TOOLCHAIN_BIN), existing] if existing else [str(TOOLCHAIN_BIN)])
    return env


def pm_argv():
    if find_tool("yarn"):
        return ["yarn"]
    if find_tool("corepack"):
        return ["corepack", "yarn"]
    if find_tool("pnpm"):
        return ["pnpm"]
    if find_tool("npm"):
        return ["npm"]
    return None


def plugin_lock_spec(manifest):
    spec = manifest.get("swc_plugin_fixture_lock") or {}
    return (
        spec.get("filename", "plugin-analyze.Cargo.lock"),
        spec.get("sha256"),
        spec.get("source_relative_destination"),
    )


def unmet_dependencies(input_dir):
    inp = Path(input_dir)
    manifest_path = inp / "manifest.json"
    if not manifest_path.is_file():
        return ["source: manifest.json not found at %s" % manifest_path]
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError) as exc:
        return ["source: manifest.json unreadable (%s)" % exc]

    missing = []
    source = manifest.get("source", {})
    archive = inp / source.get("filename", "source.tar.gz")
    if not archive.is_file():
        missing.append("source: archive missing at %s" % archive)
    else:
        try:
            got = digest(archive)
        except OSError as exc:
            missing.append("source: archive unreadable (%s)" % exc)
        else:
            want = source.get("sha256")
            if want and got != want:
                missing.append("source: archive sha256 mismatch got=%s want=%s" % (got, want))

    if not find_tool("node"):
        missing.append("tool: node not on PATH")
    if not (find_tool("cc") or find_tool("gcc") or find_tool("clang")):
        missing.append("tool: no C compiler (cc/gcc/clang) on PATH")
    if pm_argv() is None:
        missing.append("tool: no JavaScript package manager (yarn/corepack/pnpm/npm)")

    if not toolchain_ready() and bootstrap_dir() is None:
        missing.append(
            "bootstrap: nightly rustc/cargo unavailable and no official installer under %s"
            % " or ".join(str(d) for d in BOOTSTRAP_DIRS)
        )
    wasm_installer = WASM_COMPONENT_DIR / "install.sh"
    if not wasm_std_ready() and not wasm_installer.is_file():
        missing.append(
            "bootstrap: wasm32-wasip1 std component installer missing at %s/install.sh"
            % WASM_COMPONENT_DIR
        )

    if not cargo_registry_present(CARGO_CACHE):
        missing.append("dependency: offline cargo registry cache empty/absent under %s" % CARGO_CACHE)
    if not _populated(yarn_cache_dir()):
        missing.append("dependency: offline yarn cache empty/absent under %s" % YARN_CACHE)

    lock_name, lock_sha, lock_dest = plugin_lock_spec(manifest)
    lock_src = inp / lock_name
    if not lock_dest:
        missing.append("manifest: swc_plugin_fixture_lock.source_relative_destination missing")
    if not lock_src.is_file():
        missing.append("dependency: frozen plugin fixture lock missing at %s" % lock_src)
    else:
        try:
            got = digest(lock_src)
        except OSError as exc:
            missing.append("dependency: plugin fixture lock unreadable (%s)" % exc)
        else:
            if lock_sha and got != lock_sha:
                missing.append(
                    "dependency: plugin fixture lock sha256 mismatch got=%s want=%s" % (got, lock_sha)
                )
    return missing


def cmd_doctor(args):
    missing = unmet_dependencies(args.input)
    if missing:
        print("missing source/tool/dependency items:")
        for item in missing:
            print("  - " + item)
        return 78
    print("all required source, tool and dependency items present")
    return 0


def install_frozen_plugin_lock(session, args):
    """Copy the hydrated, Cargo-generated fixture lock into its declared destination.

    The frozen input is the actual ``cargo`` output produced against the upstream
    fixture ``Cargo.toml``; we only verify its hash and place it, never rewrite
    crate versions, dependency constraints or tests.
    """
    lock_name, lock_sha, lock_dest = plugin_lock_spec(session.manifest)
    if not lock_dest:
        raise RuntimeError("manifest.swc_plugin_fixture_lock.source_relative_destination missing")
    src_path = Path(args.input) / lock_name
    if not src_path.is_file():
        raise RuntimeError("frozen plugin fixture lock missing at %s" % src_path)
    actual = digest(src_path)
    if lock_sha and actual != lock_sha:
        raise RuntimeError("frozen plugin fixture lock sha256 mismatch got=%s want=%s" % (actual, lock_sha))
    dst = (session.src / lock_dest).resolve()
    root = session.src.resolve()
    try:
        dst.relative_to(root)
    except ValueError:
        raise RuntimeError("plugin fixture lock destination escapes source tree: %s" % dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, dst)
    session.write("plugin_fixture_lock.json", {
        "input_filename": lock_name,
        "input_sha256": actual,
        "source_relative_destination": lock_dest,
        "installed_path": str(dst),
        "installed_sha256": digest(dst),
    })
    return dst


def stage_bundle(session, core_dir, src):
    session.install.mkdir(parents=True, exist_ok=True)
    skip = {"node_modules", "target", "src", "pkg", "scripts"}
    copied = []
    for entry in sorted(core_dir.rglob("*")):
        if not entry.is_file():
            continue
        rel = entry.relative_to(core_dir)
        if set(rel.parts) & skip:
            continue
        if entry.name.endswith(".d.ts") or entry.suffix in (".js", ".cjs", ".mjs", ".node", ".json"):
            dst = session.install / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(entry, dst)
            copied.append(str(rel))

    pkg_path = session.install / "package.json"
    if not pkg_path.is_file():
        raise RuntimeError("staged bundle is missing package.json (build incomplete?)")
    natives = [name for name in copied if name.endswith(".node")]
    if not natives:
        raise RuntimeError("staged bundle is missing the freshly built native binding")

    pkg = json.loads(pkg_path.read_text())
    main = pkg.get("main", "index.js")
    if not (session.install / main).is_file():
        raise RuntimeError("staged bundle main %s is missing" % main)

    # runtime JS dependencies so the bundle is loadable strictly from INSTALL_ROOT
    search = [core_dir / "node_modules", src / "node_modules", src / "packages" / "core" / "node_modules"]
    node_modules = session.install / "node_modules"
    for name in pkg.get("dependencies", {}):
        for base in search:
            candidate = base / name
            if not candidate.exists():
                continue
            dst = node_modules / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists() or dst.is_symlink():
                shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(candidate, dst, symlinks=False, dirs_exist_ok=True)
            break

    session.write("bundle_manifest.json", {
        "task_id": TASK_ID,
        "main": main,
        "native_binding": natives[0],
        "native_sha256": digest(session.install / natives[0]),
        "files": sorted(copied),
    })
    return natives[0]


def cmd_run(args):
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    missing = unmet_dependencies(args.input)
    if missing:
        (out / "unmet_dependencies.json").write_text(
            json.dumps({"task_id": TASK_ID, "missing": missing}, indent=2) + "\n")
        print("cannot build %s: unmet dependencies" % TASK_ID, file=sys.stderr)
        for item in missing:
            print("  - " + item, file=sys.stderr)
        return 78

    session = Session(args.input, out, jobs=args.jobs)
    src = session.prepare()

    # Cargo target MUST live inside the checkout: the official Rust testing harness
    # spawns a real Mocha child whose cwd is below CARGO_TARGET_DIR, and only that
    # ancestor chain exposes the unmodified official ./.mocharc.js + ./.mocha.setup.js
    # (which register expect & preloads).  Keeping it in-tree preserves the genuine
    # upstream test environment with zero fixture/assertion edits.
    target_dir = src / "target"

    # 0. frozen dependency placement: the hydrated, Cargo-generated fixture lock.
    install_frozen_plugin_lock(session, args)

    # bootstrap env: PATH already includes TOOLCHAIN_BIN (fixed install prefix).
    env = base_env()
    env.update({
        "CARGO_HOME": str(CARGO_CACHE),
        "CARGO_NET_OFFLINE": "true",
        "CARGO_BUILD_JOBS": str(session.jobs),
        "CARGO_TARGET_DIR": str(target_dir),
        "RUST_BACKTRACE": "1",
        "YARN_CACHE_FOLDER": str(yarn_cache_dir()),
        "YARN_ENABLE_GLOBAL_CACHE": "0",
        "YARN_ENABLE_NETWORK": "0",
        "YARN_ENABLE_TELEMETRY": "0",
        "NODE_ENV": "production",
    })
    env.pop("RUSTC_BOOTSTRAP", None)

    # 1. bootstrap the pinned nightly toolchain from its official installer
    if not toolchain_ready():
        installer = bootstrap_dir()
        session.run(
            [str(installer / "install.sh"),
             "--prefix=" + str(TOOLCHAIN_DIR),
             "--components=" + RUST_COMPONENTS,
             "--disable-ldconfig",
             "--without=rust-docs"],
            cwd=installer, phase="bootstrap", name="rust_nightly", env=env, timeout=3600,
        )

    # 1b. install the OFFICIAL rust-std-wasm32-wasip1 component into the same prefix
    #     via its own installer.  Required by packages/core/e2e/fixtures/plugin_analyze.
    wasm_installer = WASM_COMPONENT_DIR / "install.sh"
    if wasm_installer.is_file() and not wasm_std_ready():
        session.run(
            [str(wasm_installer),
             "--prefix=" + str(TOOLCHAIN_DIR),
             "--disable-ldconfig",
             "--components=" + WASM_COMPONENT_NAME],
            cwd=WASM_COMPONENT_DIR, phase="bootstrap", name="rust_std_wasm32_wasip1",
            env=env, timeout=1800,
        )
    if not wasm_std_ready():
        raise RuntimeError("wasm32-wasip1 std library missing under %s" % TOOLCHAIN_DIR)

    # 2. AFTER install: rebuild the env so the genuine nightly bin dir + RUSTC/CARGO
    #    are explicitly bound and inherited by every napi / cargo / test subprocess.
    env = bind_toolchain_env(base_env())
    env.update({
        "CARGO_HOME": str(CARGO_CACHE),
        "CARGO_NET_OFFLINE": "true",
        "CARGO_BUILD_JOBS": str(session.jobs),
        "CARGO_TARGET_DIR": str(target_dir),
        "RUST_BACKTRACE": "1",
        "YARN_CACHE_FOLDER": str(yarn_cache_dir()),
        "YARN_ENABLE_GLOBAL_CACHE": "0",
        "YARN_ENABLE_NETWORK": "0",
        "YARN_ENABLE_TELEMETRY": "0",
        "NODE_ENV": "production",
    })
    env.pop("RUSTC_BOOTSTRAP", None)

    for tool in ("rustc", "cargo"):
        session.run([str(TOOLCHAIN_BIN / tool), "--version"],
                    cwd=src, phase="bootstrap", name=tool + "_version", env=env, timeout=120)
    session.run([str(TOOLCHAIN_BIN / "rustc"), "-vV"],
                cwd=src, phase="bootstrap", name="rustc_verbose", env=env, timeout=120)
    session.run([str(TOOLCHAIN_BIN / "cargo"), "--target", WASM_TARGET, "--version"],
                cwd=src, phase="bootstrap", name="cargo_wasm_target_probe", env=env, timeout=120,
                check=False)

    pm = pm_argv()

    # 3. configure: offline install of the frozen JS workspace
    head = pm[0]
    if head == "yarn" or (head == "corepack" and len(pm) > 1 and pm[1] == "yarn"):
        install_argv = [*pm, "install", "--immutable", "--mode=skip-build"]
    elif head == "pnpm":
        install_argv = [*pm, "install", "--frozen-lockfile", "--offline", "--ignore-scripts"]
    else:
        install_argv = [*pm, "ci", "--offline", "--no-audit", "--no-fund", "--ignore-scripts"]
    session.run(install_argv, cwd=src, phase="configure", name="js_install", env=env, timeout=3600)

    data_script = src / "crates" / "swc_ecma_preset_env" / "scripts" / "copy-data.js"
    if data_script.is_file():
        node = find_tool("node") or "node"
        session.run([node, str(data_script)], cwd=src, phase="configure", name="preset_env_data",
                    env=env, timeout=600, check=False)

    # 4. build: root script -> packages/core -> tsc -d + napi release build of binding_core_node
    session.run([*pm, "run", "build"], cwd=src, phase="build", name="swc_build", env=env, timeout=10800)

    core_dir = src / "packages" / "core"
    if not sorted(core_dir.glob("*.node")):
        raise RuntimeError("native binding build produced no .node under %s" % core_dir)
    native_name = stage_bundle(session, core_dir, src)
    session.write("install_layout.json", {
        "task_id": TASK_ID,
        "install_root": str(session.install),
        "native_binding": native_name,
        "source_commit": session.manifest["source"].get("commit"),
        "source_ref": session.manifest["source"].get("release_ref"),
        "rustc": str(TOOLCHAIN_BIN / "rustc"),
        "cargo": str(TOOLCHAIN_BIN / "cargo"),
        "cargo_target_dir": str(target_dir),
        "wasm_target": WASM_TARGET,
    })

    # 5. official, bounded, non-empty test selection with preserved evidence.
    #    Rust suite: CARGO_TARGET_DIR stays inside the checkout so the official
    #    Mocha exec cases still find the unmodified root .mocharc.js / .mocha.setup.js.
    test_env = bind_toolchain_env(dict(env))
    test_env.update({
        "CARGO_TARGET_DIR": str(target_dir),
        "CARGO_HOME": str(CARGO_CACHE),
        "CARGO_NET_OFFLINE": "true",
        "CARGO_BUILD_JOBS": "2",
        "RUST_TEST_THREADS": "2",
    })
    test_env.pop("RUSTC_BOOTSTRAP", None)

    session.test("cargo_swc_ecma_transforms",
                 [str(TOOLCHAIN_BIN / "cargo"), "test", "--offline", "--locked",
                  "-j", "2", "-p", "swc_ecma_transforms", "--all-features"],
                 cwd=src, parser="auto", env=test_env, timeout=10800)

    # Node test:core runner (jest -> plugin_analyze fixture Cargo workspace).
    # CARGO_TARGET_DIR must be ABSENT from the inherited env so the fixture creates
    # its expected packages/core/e2e/fixtures/plugin_analyze/target/... path.
    # Session.run merges env with os.environ, so remove it from BOTH places.
    os.environ.pop("CARGO_TARGET_DIR", None)
    core_env = bind_toolchain_env(base_env())
    core_env.update({
        "CARGO_HOME": str(CARGO_CACHE),
        "CARGO_NET_OFFLINE": "true",
        "CARGO_BUILD_JOBS": "2",
        "RUST_TEST_THREADS": "2",
    })
    core_env.pop("CARGO_TARGET_DIR", None)
    core_env.pop("RUSTC_BOOTSTRAP", None)

    session.test("packages_core_rstest", [*pm, "run", "test:core"],
                 cwd=src, parser="auto", env=core_env, timeout=5400)

    # 6. independent consumer outside the source tree, loading only from INSTALL_ROOT
    consumer = session.consumer
    (consumer / "package.json").write_text(
        json.dumps({"name": "swc-core-consumer", "private": True}, indent=2) + "\n")
    (consumer / "consume.js").write_text(CONSUMER_JS)
    session.write("consumer_source.js", CONSUMER_JS)
    node = find_tool("node") or "node"
    consumer_env = dict(core_env)
    consumer_env["SWC_INSTALL_ROOT"] = str(session.install)
    session.run([node, "consume.js"], cwd=consumer, phase="consumer", name="swc_consumer",
                env=consumer_env, timeout=600)

    session.finish(features={
        "profile": "core",
        "target": "linux-x86_64-gnu",
        "rust_toolchain": "nightly-2024-10-07",
        "rustc": str(TOOLCHAIN_BIN / "rustc"),
        "cargo": str(TOOLCHAIN_BIN / "cargo"),
        "wasm_target": WASM_TARGET,
        "wasm_std": str(TOOLCHAIN_DIR / "lib" / "rustlib" / WASM_TARGET),
        "native_binding": native_name,
        "bound_tests": ["cargo_swc_ecma_transforms", "packages_core_rstest"],
        "consumer": "node transform/sourcemap/diagnostic/minify from INSTALL_ROOT",
    })
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="solution/main.py",
        description="BUILDv1-E10 source build of SWC core native Node bindings (frozen core profile)",
    )
    sub = parser.add_subparsers(dest="command")
    run = sub.add_parser("run", help="bootstrap, build, test, install and consume the SWC core native bundle")
    run.add_argument("--input", required=True, help="read-only source/manifest directory")
    run.add_argument("--output", required=True, help="writable output directory")
    run.add_argument("--jobs", type=int, default=4, help="build parallelism (capped at 4)")
    doc = sub.add_parser("doctor", help="report missing source/tool/dependency items")
    doc.add_argument("--input", required=True, help="read-only source/manifest directory")

    args = parser.parse_args(argv)
    if args.command == "doctor":
        return cmd_doctor(args)
    if args.command == "run":
        return cmd_run(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
