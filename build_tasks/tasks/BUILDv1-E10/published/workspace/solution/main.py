#!/usr/bin/env python3
"""BUILDv1-E10 - build SWC core native Node bindings from source and verify.

Subcommands:
  doctor --input <dir>                      report missing source/tool/dependency items (78 if any)
  run --input <dir> --output <dir> [--jobs] build, test, install and consume the native bundle

All build / configure / install / test / consumer work is dispatched through the trusted
`buildkit.Session` helper so that every command exit code, log digest and test selector is
preserved.  The build only proceeds when the offline dependency snapshot is actually present;
otherwise it fails with a machine-readable unmet-dependency report instead of fabricating a
successful build.

The `napi` CLI is treated as an ordinary devDependency installed by the frozen JS workspace
lockfile (invoked through `yarn run` / `npx --no-install` from `node_modules/.bin`); we never
require a preinstalled global `napi` binary.
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
TARGET_BINDING = "swc.linux-x64-gnu.node"
INSTALLED_LAYOUT = ("index.js", "binding.js", "package.json")
YARN_CACHE_DEFAULT = Path("/workspace/cache/yarn")
CARGO_CACHE_DEFAULT = Path("/workspace/cache/cargo")

CONSUMER_JS = r"""'use strict';
const assert = require('assert');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const Module = require('module');

const corePath = require.resolve('@swc/core');
const coreDir = fs.realpathSync(path.dirname(corePath));
const expected = process.env.SWC_EXPECT_INSTALL;
if (expected) {
  const realExpected = fs.realpathSync(expected);
  assert(coreDir.startsWith(realExpected),
    '@swc/core loaded from outside INSTALL_ROOT: ' + coreDir + ' vs ' + realExpected);
}

const nativeFiles = fs.readdirSync(coreDir).filter((f) => f.endsWith('.node'));
assert(nativeFiles.length > 0, 'no local .node binding next to ' + corePath);
const nativePath = path.join(coreDir, nativeFiles[0]);

const swc = require('@swc/core');
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

const m = new Module('emitted', module);
m.filename = path.join(coreDir, 'emitted.js');
m.paths = Module._nodeModulePaths(coreDir);
m._compile(out.code, m.filename);
assert.strictEqual(m.exports.n, 42, 'transpiled runtime semantics wrong');

let threw = false;
try {
  swc.transformSync('const = ;', {
    filename: 'bad.ts', jsc: { parser: { syntax: 'typescript' } },
  });
} catch (e) {
  threw = true;
}
assert.ok(threw, 'invalid syntax must surface an error diagnostic');

console.log(JSON.stringify({
  core: corePath,
  native: nativePath,
  native_sha256: crypto.createHash('sha256').update(fs.readFileSync(nativePath)).digest('hex'),
  mappings: out.map.mappings.length,
  value: m.exports.n,
}));
"""


def which(name):
    return shutil.which(name)


def _first_existing(cands, test=None):
    for candidate in cands:
        if candidate is None:
            continue
        try:
            if test is None:
                if candidate.exists():
                    return candidate
            elif test(candidate):
                return candidate
        except OSError:
            continue
    return None


def cargo_home():
    env_home = os.environ.get("CARGO_HOME")
    cands = []
    if env_home:
        cands.append(Path(env_home))
    cands.append(CARGO_CACHE_DEFAULT)
    try:
        cands.append(Path.home() / ".cargo")
    except RuntimeError:
        pass
    cands += [Path("/usr/local/cargo"), Path("/root/.cargo")]
    found = _first_existing(cands, test=lambda p: (p / "registry").is_dir())
    if found is not None:
        return found
    # Fall back to the first candidate so callers get a concrete path even when empty.
    for candidate in cands:
        if candidate is not None:
            return candidate
    return Path("~/.cargo").expanduser()


def yarn_cache():
    env_cache = os.environ.get("YARN_CACHE_FOLDER")
    cands = []
    if env_cache:
        cands.append(Path(env_cache))
    cands.append(YARN_CACHE_DEFAULT)
    try:
        home = Path.home()
    except RuntimeError:
        home = None
    if home is not None:
        cands += [home / ".yarn" / "berry" / "cache", home / ".cache" / "yarn"]
    cands += [Path("/usr/local/share/.cache/yarn")]
    return _first_existing(cands, test=lambda p: p.is_dir() and any(p.iterdir()))


def pnpm_store():
    env_store = os.environ.get("PNPM_STORE_DIR")
    cands = []
    if env_store:
        cands.append(Path(env_store))
    try:
        home = Path.home()
    except RuntimeError:
        home = None
    if home is not None:
        cands.append(home / ".local" / "share" / "pnpm" / "store")
    cands.append(Path("/usr/local/share/pnpm/store"))
    return _first_existing(cands, test=lambda p: p.is_dir() and any(p.iterdir()))


def npm_cache():
    try:
        home = Path.home()
    except RuntimeError:
        home = None
    cands = []
    if home is not None:
        cands.append(home / ".npm" / "_cacache")
    cands.append(Path("/usr/local/share/.npm/_cacache"))
    return _first_existing(cands, test=lambda p: p.is_dir() and any(p.iterdir()))


def pick_package_manager():
    for name in ("yarn", "pnpm", "npm"):
        if which(name):
            return name
    return None


def js_cache_present():
    return yarn_cache() or pnpm_store() or npm_cache()


def cargo_registry_present(cache_root):
    for sub in ("registry/cache", "registry/index", "registry/src"):
        base = cache_root / sub
        if base.is_dir() and any(base.iterdir()):
            return True
    return False


def unmet_dependencies(input_dir):
    """Return a list of missing source/tool/dependency items for the frozen source build."""
    missing = []
    inp = Path(input_dir)
    manifest_path = inp / "manifest.json"
    if not manifest_path.is_file():
        return ["source: manifest.json not found at %s" % manifest_path]
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError) as exc:
        return ["source: manifest.json unreadable (%s)" % exc]

    source = manifest.get("source", {})
    archive = inp / source.get("filename", "source.tar.gz")
    if not archive.is_file():
        missing.append("source: source archive missing at %s" % archive)
    else:
        try:
            got = digest(archive)
        except OSError as exc:
            missing.append("source: source archive unreadable (%s)" % exc)
        else:
            want = source.get("sha256")
            if want and got != want:
                missing.append("source: source archive sha256 mismatch got=%s want=%s" % (got, want))

    for tool in ("cargo", "rustc", "node"):
        if not which(tool):
            missing.append("tool: %s not on PATH" % tool)
    if pick_package_manager() is None:
        missing.append("tool: no JavaScript package manager (yarn/pnpm/npm) on PATH")

    home = cargo_home()
    if not cargo_registry_present(home):
        missing.append("dependency: offline cargo registry cache empty/absent under %s" % home)
    if js_cache_present() is None:
        missing.append("dependency: no offline JS package cache (yarn %s / pnpm store / npm cacache)" % YARN_CACHE_DEFAULT)
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


def _stage_install(session, core_dir):
    session.install.mkdir(parents=True, exist_ok=True)
    staged = []
    for entry in sorted(core_dir.iterdir()):
        if entry.is_file() and entry.suffix in (".js", ".cjs", ".mjs", ".node", ".ts", ".json"):
            shutil.copy2(entry, session.install / entry.name)
            staged.append(entry.name)
    for wanted in INSTALLED_LAYOUT:
        if wanted not in staged:
            raise RuntimeError("staged bundle is missing required runtime file %s" % wanted)
    natives = [n for n in staged if n.endswith(".node")]
    if not natives:
        raise RuntimeError("staged bundle is missing the freshly built native binding")
    session.write("bundle_manifest.json", {
        "task_id": TASK_ID,
        "binding_file": natives[0],
        "binding_sha256": digest(session.install / natives[0]),
        "files": staged,
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
    pm = pick_package_manager()
    cache = yarn_cache()

    env = {
        "CARGO_BUILD_JOBS": str(session.jobs),
        "CARGO_NET_OFFLINE": "true",
        "CARGO_HOME": str(cargo_home()),
        "RUST_BACKTRACE": "1",
        "NODE_ENV": "production",
        "YARN_ENABLE_NETWORK": "0",
        "YARN_ENABLE_TELEMETRY": "0",
    }
    if cache is not None:
        env["YARN_CACHE_FOLDER"] = str(cache)

    # configure: install the frozen JS dependency tree strictly offline
    if pm == "yarn":
        session.run([pm, "install", "--immutable"], cwd=src, phase="configure", name="yarn_install", env=env, timeout=3600)
    elif pm == "pnpm":
        session.run([pm, "install", "--frozen-lockfile", "--offline"], cwd=src, phase="configure", name="pnpm_install", env=env, timeout=3600)
    else:
        session.run([pm, "ci", "--offline", "--no-audit", "--no-fund"], cwd=src, phase="configure", name="npm_ci", env=env, timeout=3600)

    # build: root script -> packages/core -> tsc declarations + napi release build of binding_core_node
    # napi-rs is a workspace devDependency, so the script resolves it through node_modules/.bin;
    # we never require a globally installed `napi` binary.
    session.run([pm, "run", "build"], cwd=src, phase="build", name="swc_build", env=env, timeout=10800)

    core_dir = src / "packages" / "core"
    natives = sorted(core_dir.glob("*.node"))
    if not natives:
        raise RuntimeError("build produced no native binding under %s" % core_dir)
    native_name = _stage_install(session, core_dir)
    session.write("install_layout.json", {
        "task_id": TASK_ID,
        "install_root": str(session.install),
        "native_binding": native_name,
        "source_commit": session.manifest["source"].get("commit"),
        "source_ref": session.manifest["source"].get("release_ref"),
    })

    # official test selection (bounded, non-empty, skipped/failed evidence preserved)
    test_env = dict(env, RUST_TEST_THREADS="2")
    session.test(
        "cargo_swc_ecma_transforms",
        ["cargo", "test", "--offline", "--locked", "-j", "2", "-p", "swc_ecma_transforms", "--all-features"],
        cwd=src, parser="auto", env=test_env, timeout=10800,
    )
    session.test(
        "packages_core_rstest",
        [pm, "run", "test:core"],
        cwd=src, parser="auto", env=test_env, timeout=5400,
    )

    # independent consumer outside the source tree loads the freshly built bundle explicitly
    consumer = session.consumer
    (consumer / "node_modules" / "@swc").mkdir(parents=True, exist_ok=True)
    link = consumer / "node_modules" / "@swc" / "core"
    if link.is_symlink():
        link.unlink()
    elif link.exists():
        shutil.rmtree(link)
    os.symlink(session.install, link)
    (consumer / "package.json").write_text(json.dumps({"name": "swc-core-consumer", "private": True}, indent=2) + "\n")
    (consumer / "consume.js").write_text(CONSUMER_JS)
    session.write("consumer_source.js", CONSUMER_JS)
    session.run(
        ["node", "consume.js"], cwd=consumer, phase="consumer", name="swc_consumer",
        env=dict(env, SWC_EXPECT_INSTALL=str(session.install), NODE_PATH=str(consumer / "node_modules")),
        timeout=600,
    )

    session.finish(features={
        "profile": "core",
        "target": "linux-x86_64-gnu",
        "native_binding": native_name,
        "bound_tests": ["cargo_swc_ecma_transforms", "packages_core_rstest"],
        "consumer": "node transform/sourcemap/diagnostic verification from INSTALL_ROOT",
    })
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="solution/main.py",
        description="BUILDv1-E10 source build of SWC core native Node bindings (frozen core profile)",
    )
    sub = parser.add_subparsers(dest="command")
    run = sub.add_parser("run", help="build, test, install and consume the SWC core native bundle")
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
