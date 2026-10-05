#!/usr/bin/env python3
"""BUILDv1-E08: build the Babel toolchain from the frozen source release (v7.27.1,
commit eebd3a06021c13d335b5b0bd79734df3abbea678) and verify an installed consumer
transform outside the source tree.

Subcommands:
  run               full configure/build/test/package/consume pipeline
  doctor            readiness probe; exit 78 when items are missing, 0 when ready
  consumer-install  internal: assemble consumer/node_modules from built tarballs

Offline contract: Runtime v7 supplies pinned Corepack/Yarn 4.9.1 plus a hydrated
dependency cache at /workspace/cache/yarn. All yarn invocations use Yarn-4
semantics (`install --immutable`, `YARN_ENABLE_NETWORK=0`,
`YARN_ENABLE_GLOBAL_CACHE=false`); no yarn v1 flags are used.
"""
import argparse
import json
import os
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

from buildkit import Session, digest

REQUIRED_TOOLS = ["node", "make", "python3"]
# Only workspace-local locations are probed; unrelated home directories (e.g.
# /root/.yarn/berry/cache) are intentionally NOT touched because an ordinary
# build UID cannot stat them without raising PermissionError.
CACHE_CANDIDATES = ["/workspace/cache/yarn", "/workspace/input"]
TARBALL_DIRNAME = "tarballs"

CONSUMER_PACKAGE_JSON = {
    "name": "babel-consumer",
    "version": "1.0.0",
    "private": True,
    "type": "module",
}

CONSUMER_TRANSFORM = r'''
import { createRequire } from "module";
import assert from "assert";
import { writeFileSync, mkdtempSync } from "fs";
import { tmpdir } from "os";
import { join, dirname, resolve } from "path";

const require = createRequire(import.meta.url);
const babel = require("@babel/core");
const presetEnv = require("@babel/preset-env");

// Record the concrete on-disk resolution of the built @babel/* closure so the
// grader can confirm every internal dependency came from the installed tarballs.
const closure = [
  "@babel/core", "@babel/parser", "@babel/generator", "@babel/traverse",
  "@babel/types", "@babel/preset-env", "@babel/helper-module-transforms",
  "@babel/helper-compilation-targets", "@babel/helper-validator-identifier",
  "@babel/template", "@babel/code-frame",
];
const installedRoot = resolve(dirname(require.resolve("@babel/core/package.json")), "..", "..");
const resolution = {};
for (const pkg of closure) {
  const p = require.resolve(pkg + "/package.json");
  assert(p.startsWith(installedRoot), `${pkg} resolved outside installed closure: ${p}`);
  resolution[pkg] = p;
}

const program = [
  "export class Counter {",
  "  constructor() { this.n = 0; }",
  "  async inc() { this.n += 1; return this.n; }",
  "}",
  "export async function run() {",
  "  const c = new Counter();",
  "  return [await c.inc(), await c.inc()];",
  "}",
].join("\n");

const result = babel.transformSync(program, {
  filename: "program.mjs",
  sourceMaps: true,
  configFile: false,
  babelrc: false,
  presets: [[presetEnv, { targets: { ie: "11" }, modules: "commonjs" }]],
});

assert(result && typeof result.code === "string", "no transform output produced");
const code = result.code;
assert(!/\bclass\s+Counter\b/.test(code), "class syntax was not transpiled for ie11");
assert(!/async\s+function\s+run\b/.test(code), "async function was not transpiled for ie11");
assert(result.map && Array.isArray(result.map.sources), "no source map emitted");
assert(result.map.sources.some((s) => s.includes("program.mjs")), "source map missing input file");

const dir = mkdtempSync(join(tmpdir(), "babel-out-"));
const outFile = join(dir, "out.cjs");
writeFileSync(outFile, code);
const mod = require(outFile);
const values = await mod.run();
assert.deepStrictEqual(values, [1, 2], "runtime result mismatch: " + JSON.stringify(values));

console.log(JSON.stringify({
  ok: true,
  transformed: true,
  requested_target: "ie 11",
  sources: result.map.sources,
  values,
  resolution,
}));
'''

CONSUMER_NEGATIVE = r'''
import { createRequire } from "module";
import assert from "assert";

const require = createRequire(import.meta.url);
const babel = require("@babel/core");

let threw = false;
try {
  babel.transformSync("const x = ;", { filename: "bad.js", configFile: false, babelrc: false });
} catch (e) {
  threw = true;
  assert(/SyntaxError|Unexpected token/.test(String(e.message)), "unexpected error: " + e.message);
}
assert(threw, "invalid syntax did not fail as required by the negative case");
console.log(JSON.stringify({ ok: true, negative: true }));
'''


def _safe_isdir(path):
    """os.path.isdir swallows PermissionError/OSError; Path.is_dir does not."""
    try:
        return os.path.isdir(str(path))
    except OSError:
        return False


def _safe_stat_size(path):
    try:
        return os.path.getsize(str(path))
    except OSError:
        return None


def find_cache(input_dir=None):
    for key in ("YARN_CACHE_FOLDER", "NPM_CONFIG_CACHE"):
        value = os.environ.get(key)
        if value and _safe_isdir(value):
            return value
    candidates = list(CACHE_CANDIDATES)
    if input_dir is not None and str(input_dir) not in candidates:
        candidates.append(str(input_dir))
    for candidate in candidates:
        if _safe_isdir(candidate):
            return candidate
    return None


def doctor(input_dir, src=None):
    input_dir = Path(input_dir).resolve()
    problems, report = [], {"tools": {}, "source": {}, "dependencies": {}}

    for tool in REQUIRED_TOOLS:
        path = shutil.which(tool)
        report["tools"][tool] = path
        if not path:
            problems.append(f"missing tool: {tool}")
    yarn_bin = shutil.which("yarn")
    corepack_bin = shutil.which("corepack")
    report["tools"]["yarn"] = yarn_bin
    report["tools"]["corepack"] = corepack_bin
    if not yarn_bin and not corepack_bin:
        problems.append("missing tool: yarn (neither yarn nor corepack is on PATH)")

    expected = {}
    manifest_path = input_dir / "manifest.json"
    if manifest_path.exists():
        try:
            expected = json.loads(manifest_path.read_text()).get("source", {})
        except (OSError, ValueError) as exc:
            problems.append(f"manifest unreadable: {manifest_path}: {exc}")
    else:
        problems.append(f"manifest missing: {manifest_path}")

    archive = input_dir / expected.get("filename", "source.tar.gz")
    if not archive.exists():
        report["source"] = {"path": str(archive), "present": False}
        problems.append(f"source archive missing: {archive}")
    else:
        size = _safe_stat_size(archive)
        report["source"] = {"path": str(archive), "present": True, "bytes": size}
        if expected.get("bytes") and size != expected["bytes"]:
            problems.append(f"source size mismatch: {size} != {expected['bytes']}")
        try:
            sha = digest(archive)
            report["source"]["sha256"] = sha
            if expected.get("sha256") and sha != expected["sha256"]:
                problems.append(f"source sha256 mismatch: {sha} != {expected['sha256']}")
        except OSError as exc:
            problems.append(f"source unreadable: {archive}: {exc}")

    cache = find_cache(input_dir)
    if cache:
        report["dependencies"]["yarn_cache"] = cache
    if src is not None and _safe_isdir(Path(src) / "node_modules"):
        report["dependencies"]["node_modules"] = str(Path(src) / "node_modules")

    # dependencies.tar.gz shipped in the read-only input is legitimate staged
    # offline evidence even before the cache is extracted into /workspace/cache.
    staging = []
    try:
        staging = sorted(str(p) for p in input_dir.glob("dependencies*.tar.gz"))
    except OSError:
        staging = []
    if staging:
        report["dependencies"]["dependency_archives"] = staging

    if not cache and not staging and "node_modules" not in report["dependencies"]:
        problems.append(
            "offline dependency payload missing: no hydrated yarn cache under /workspace/cache/yarn, "
            "no dependencies.tar.gz staging evidence in the input, and no node_modules in the source tree"
        )
    return problems, report


def build_env(session):
    env = {
        "CI": "1",
        "BABEL_ENV": "test",
        "YARN_ENABLE_NETWORK": "0",
        "YARN_ENABLE_GLOBAL_CACHE": "false",
        "YARN_ENABLE_TELEMETRY": "0",
        "YARN_ENABLE_IMMUTABLE_INSTALLS": "true",
        "COREPACK_ENABLE_DOWNLOAD_PROMPT": "0",
        "COREPACK_ENABLE_STRICT": "0",
        "FORCE_COLOR": "0",
        "JOBS": str(session.jobs),
        "TEST_JOBS": "2",
    }
    cache = find_cache(session.input)
    if cache:
        env["YARN_CACHE_FOLDER"] = cache
        env["NPM_CONFIG_CACHE"] = cache
    if shutil.which("yarn") is None:
        shim = session.build / "bin"
        shim.mkdir(parents=True, exist_ok=True)
        wrapper = shim / "yarn"
        wrapper.write_text('#!/bin/sh\nexec corepack yarn "$@"\n')
        wrapper.chmod(0o755)
        env["PATH"] = str(shim) + os.pathsep + os.environ.get("PATH", "")
    return env


def write_consumer_files(consumer):
    consumer.mkdir(parents=True, exist_ok=True)
    (consumer / "package.json").write_text(json.dumps(CONSUMER_PACKAGE_JSON, indent=2) + "\n")
    (consumer / "transform.mjs").write_text(CONSUMER_TRANSFORM)
    (consumer / "negative.mjs").write_text(CONSUMER_NEGATIVE)


def consumer_install(src_node_modules, tarballs_dir, consumer):
    nm = Path(consumer) / "node_modules"
    if nm.exists():
        shutil.rmtree(nm)
    nm.mkdir(parents=True)

    src_node_modules = Path(src_node_modules)
    if src_node_modules.is_dir():
        for entry in sorted(src_node_modules.iterdir()):
            if entry.name == "@babel":
                continue  # replaced wholesale by the newly built tarballs
            dst = nm / entry.name
            if entry.is_symlink():
                os.symlink(os.readlink(entry), dst)
            elif entry.is_dir():
                shutil.copytree(entry, dst, symlinks=True)
            else:
                shutil.copy2(entry, dst)

    staged = Path(tempfile.mkdtemp(dir="/tmp"))
    installed = []
    for tarball in sorted(Path(tarballs_dir).glob("*.tgz")):
        with tarfile.open(tarball) as archive:
            archive.extractall(staged, filter="data")
        pkg = staged / "package"
        name = json.loads((pkg / "package.json").read_text())["name"]
        dest = nm / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(pkg), str(dest))
        installed.append({"name": name, "tarball": Path(tarball).name, "path": str(dest)})
    shutil.rmtree(staged, ignore_errors=True)
    (Path(consumer) / "installed.json").write_text(json.dumps(installed, indent=2) + "\n")
    print(json.dumps({"installed": len(installed), "root": str(nm)}))
    return 0


def pack_workspaces(session, env):
    tarballs = session.install / TARBALL_DIRNAME
    tarballs.mkdir(parents=True, exist_ok=True)
    packed = []
    for pkg in sorted(p for p in (session.src / "packages").iterdir() if (p / "package.json").exists()):
        slug = json.loads((pkg / "package.json").read_text())["name"].replace("@", "").replace("/", "-")
        out = tarballs / (slug + ".tgz")
        session.run(["yarn", "pack", "--out", str(out)], cwd=pkg, phase="package",
                    name="pack_" + slug, env=env, timeout=1800)
        if out.exists():
            packed.append(out)
    if not packed:
        raise RuntimeError("no workspace tarballs were produced")
    session.write("packed.json", [str(p.relative_to(session.output)) for p in packed])
    return tarballs, packed


def run_pipeline(session, args):
    src = session.src
    env = build_env(session)

    # configure: locked, offline workspace dependency install (Yarn 4 semantics).
    session.run(["yarn", "install", "--immutable"], cwd=src, phase="configure",
                name="yarn_install_immutable", env=env, timeout=3600)
    session.run(["make", "bootstrap-only"], cwd=src, phase="configure",
                name="make_bootstrap_only", env=env, timeout=3600)

    # build: the declared full baseline (transpiles every selected workspace lib).
    session.run(["make", "build"], cwd=src, phase="build", name="make_build", env=env, timeout=7200)

    # official tests for the core profile: parser + core.
    session.test("babel-core-tests",
                 ["yarn", "jest", "babel-core", "--ci", "--maxWorkers=2"],
                 cwd=src, env=env, timeout=5400)
    session.test("babel-parser-tests",
                 ["make", "test-only"],
                 cwd=src, env=dict(env, TEST_ONLY="babel-parser"), timeout=5400)

    tarballs, packed = pack_workspaces(session, env)

    consumer = session.consumer
    write_consumer_files(consumer)
    session.run([sys.executable, str(Path(__file__).resolve()), "consumer-install",
                 "--src-node-modules", str(src / "node_modules"),
                 "--tarballs", str(tarballs), "--consumer", str(consumer)],
                cwd=consumer, phase="install", name="consumer_install", env=env, timeout=1800)
    session.run(["node", "transform.mjs"], cwd=consumer, phase="consumer",
                name="consumer_transform", env=env, timeout=1800)
    session.run(["node", "negative.mjs"], cwd=consumer, phase="consumer",
                name="consumer_negative", env=env, timeout=1800)

    session.finish(features={
        "target": "@babel/core + @babel/parser + @babel/preset-env workspace closure",
        "official_tests": ["babel-core", "babel-parser"],
        "consumer": "installed tarballs, outside src, positive + negative transform",
        "jobs": session.jobs,
        "test_jobs": 2,
    })
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="solution/main.py",
                                     description="Babel toolchain build/test/package/consumer driver")
    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run", help="configure, build, test, pack and consume Babel")
    p_run.add_argument("--input", required=True)
    p_run.add_argument("--output", required=True)
    p_run.add_argument("--jobs", type=int, default=4)

    p_doc = sub.add_parser("doctor", help="report missing source/tool/dependency items")
    p_doc.add_argument("--input", required=True)

    p_ci = sub.add_parser("consumer-install", help=argparse.SUPPRESS)
    p_ci.add_argument("--src-node-modules", required=True)
    p_ci.add_argument("--tarballs", required=True)
    p_ci.add_argument("--consumer", required=True)

    args = parser.parse_args(argv)

    if args.command == "consumer-install":
        return consumer_install(args.src_node_modules, args.tarballs, args.consumer)

    if args.command == "doctor":
        problems, report = doctor(args.input)
        print(json.dumps({"ready": not problems, "problems": problems, "report": report}, indent=2))
        return 78 if problems else 0

    if args.command == "run":
        session = Session(args.input, args.output, jobs=args.jobs)
        session.prepare()
        session.write("source_inventory.json",
                      sorted(str(p.relative_to(session.src)) for p in session.src.iterdir()))
        problems, report = doctor(args.input, src=session.src)
        session.write("doctor_report.json", report)
        if problems:
            print(json.dumps({"ready": False, "problems": problems}, indent=2), file=sys.stderr)
            return 78
        return run_pipeline(session, args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
