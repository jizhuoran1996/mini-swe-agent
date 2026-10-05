#!/usr/bin/env python3
"""TypeScript v5.9.3 source build, official compiler test subset and consumer driver."""
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import buildkit

TEST_SELECTOR = "compiler/"
HYDRATED_NPM_CACHE = Path("/workspace/cache/npm")

HELP = """TypeScript v5.9.3 source build driver

usage:
  main.py --help
  main.py doctor --input <dir>
  main.py run --input <dir> --output <dir> [--jobs N]

actions:
  doctor   verify the frozen source archive, bootstrap tools and the offline
           npm package cache; exit 0 when ready, 78 when items are missing
  run      extract the source, npm ci --offline, build the compiler, run the
           official compiler test subset, pack the npm artifact and verify a
           fresh consumer

options:
  --input DIR   directory holding manifest.json and source.tar.gz
  --output DIR  writable output directory (logs, install, artifacts)
  --jobs N      build jobs (<=4)
"""


def opts(rest):
    out = {}
    i = 0
    while i < len(rest):
        key = rest[i]
        if key.startswith("--"):
            name = key[2:].replace("-", "_")
            if i + 1 < len(rest) and not rest[i + 1].startswith("--"):
                out[name] = rest[i + 1]
                i += 2
            else:
                out[name] = True
                i += 1
        else:
            i += 1
    return out


def npm_cache(input_dir, manifest):
    """Locate the offline npm package cache hydrated by the controller."""
    deps = manifest.get("dependencies") or {}
    rels = []
    for key in ("bundle", "npm_cache", "cache"):
        if deps.get(key):
            rels.append(deps[key])
    rels += ["cache/npm", "npm-cache"]
    for rel in rels:
        candidate = input_dir / rel
        if candidate.is_dir():
            return candidate
    if HYDRATED_NPM_CACHE.is_dir():
        return HYDRATED_NPM_CACHE
    return None


def find_node_modules_bundle(input_dir, manifest):
    deps = manifest.get("dependencies") or {}
    rels = []
    if deps.get("node_modules"):
        rels.append(deps["node_modules"])
    rels += ["node_modules", "node_modules.tgz", "node_modules.tar.gz", "deps/node_modules"]
    for rel in rels:
        candidate = input_dir / rel
        if candidate.exists():
            return candidate
    return None


def doctor(rest):
    o = opts(rest)
    input_dir = Path(o.get("input", "input")).resolve()
    manifest_path = input_dir / "manifest.json"
    items = []
    manifest = {}
    if not manifest_path.is_file():
        items.append("manifest.json missing at %s" % manifest_path)
    else:
        manifest = json.loads(manifest_path.read_text())
        src = manifest.get("source", {})
        archive = input_dir / str(src.get("filename", ""))
        if not archive.is_file():
            items.append("source archive missing: %s" % archive)
        elif buildkit.digest(archive) != src.get("sha256"):
            items.append("source archive checksum mismatch: %s" % archive)
    for tool in ("node", "npm"):
        if not shutil.which(tool):
            items.append("bootstrap tool missing: %s" % tool)
    node = shutil.which("node")
    if node:
        ver = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip()
        match = re.match(r"v(\d+)\.(\d+)", ver)
        if match and (int(match.group(1)), int(match.group(2))) < (14, 17):
            items.append("node too old: %s (need >= 14.17)" % ver)
    cache = npm_cache(input_dir, manifest)
    bundle = find_node_modules_bundle(input_dir, manifest)
    if cache is None and bundle is None:
        items.append("offline npm package cache missing: expected %s "
                     "(hydrated from manifest.dependency_caches) or a node_modules "
                     "payload under %s" % (HYDRATED_NPM_CACHE, input_dir))
    if items:
        print("doctor: NOT READY")
        for item in items:
            print("  missing: " + item)
        return 78
    print("doctor: ready")
    print("  source: %s" % (input_dir / str(manifest.get('source', {}).get('filename', ''))))
    print("  node: %s" % node)
    print("  npm: %s" % shutil.which("npm"))
    print("  npm cache: %s" % (cache if cache is not None else "(using node_modules payload)"))
    return 0


def install_dependencies(session, env):
    src = session.src
    hereby = src / "node_modules" / ".bin" / "hereby"
    if hereby.exists():
        return
    cache = npm_cache(session.input, session.manifest)
    if cache is not None:
        if not (src / "package-lock.json").is_file():
            raise RuntimeError("package-lock.json missing from extracted source tree")
        session.run(["npm", "ci", "--offline", "--no-audit", "--no-fund",
                     "--cache", str(cache)],
                    cwd=src, phase="bootstrap", name="npm_ci", env=env, timeout=3600)
    else:
        bundle = find_node_modules_bundle(session.input, session.manifest)
        if bundle is None:
            raise RuntimeError("no offline npm cache or node_modules payload; run doctor first")
        target = src / "node_modules"
        if bundle.is_dir():
            shutil.copytree(bundle, target, dirs_exist_ok=True)
        else:
            with tarfile.open(bundle) as archive:
                archive.extractall(src)
    if not hereby.exists():
        raise RuntimeError("hereby was not installed into node_modules/.bin")


def build_compiler(session, env):
    session.run(["npm", "run", "clean"], cwd=session.src, phase="build", name="clean", env=env)
    session.run(["npm", "run", "build"], cwd=session.src, phase="build", name="build",
                env=env, timeout=10800)


def pack(session, output_dir, env):
    src = session.src
    hereby = str(src / "node_modules" / ".bin" / "hereby")
    session.run([hereby, "LKG"], cwd=src, phase="package", name="lkg", env=env, timeout=3600)
    artifacts = output_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    session.run(["npm", "pack", "--ignore-scripts", "--pack-destination", str(artifacts)],
                cwd=src, phase="package", name="npm_pack", env=env)
    tarballs = sorted(artifacts.glob("*.tgz"))
    if not tarballs:
        raise RuntimeError("npm pack produced no tarball")
    tgz = tarballs[-1]
    dest = session.install / "typescript"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    with tarfile.open(tgz) as archive:
        archive.extractall(dest)
    session.write("artifact.json", {"tarball": str(tgz), "bytes": tgz.stat().st_size,
                                    "sha256": buildkit.digest(tgz)})
    return tgz


def record_inventory(session):
    root = session.src / "tests" / "cases" / "compiler"
    entries = sorted(p.name for p in root.glob("*") if p.is_file()) if root.is_dir() else []
    session.write("test_inventory.json", {"selector": TEST_SELECTOR, "root": str(root),
                                          "discovered": len(entries), "entries": entries[:8000]})
    if not entries:
        raise RuntimeError("official compiler test discovery is empty at %s" % root)
    return len(entries)


def run_tests(session, env):
    discovered = record_inventory(session)
    hereby = str(session.src / "node_modules" / ".bin" / "hereby")
    session.test("compiler_subset",
                 [hereby, "runtests-parallel", "--light=false", "--tests=" + TEST_SELECTOR],
                 cwd=session.src, env=env, timeout=10800)
    return discovered


def verify_consumer(session, tgz, env):
    consumer = session.consumer
    (consumer / "package.json").write_text(json.dumps(
        {"name": "ts-consumer", "version": "1.0.0", "private": True}, indent=2))
    cache = npm_cache(session.input, session.manifest)
    install = ["npm", "install", "--offline", "--no-audit", "--no-fund",
               "--no-package-lock", str(tgz)]
    if cache is not None:
        install += ["--cache", str(cache)]
    session.run(install, cwd=consumer, phase="consumer", name="install_tgz", env=env)
    resolve_js = consumer / "resolve.js"
    resolve_js.write_text("console.log(require.resolve('typescript'));\n")
    log = session.run(["node", str(resolve_js)], cwd=consumer, phase="consumer", name="resolve", env=env)
    resolved = ""
    for line in log.read_text(errors="replace").splitlines():
        if line.strip():
            resolved = line.strip()
    if not resolved or "consumer" not in resolved:
        raise RuntimeError("consumer did not resolve the freshly installed package: %r" % resolved)

    proj = consumer / "proj"
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "tsconfig.json").write_text(json.dumps({
        "compilerOptions": {"target": "es2019", "module": "commonjs", "strict": True,
                            "declaration": True, "outDir": "dist", "rootDir": "."},
        "files": ["util.ts", "index.ts"]}, indent=2))
    (proj / "util.ts").write_text(
        "export interface Box<T> { readonly value: T }\n"
        "export function wrap<T>(v: T): Box<T> { return { value: v }; }\n"
        "export function double(n: number): number { return n * 2; }\n")
    (proj / "index.ts").write_text(
        'import { wrap, double } from "./util";\n'
        "const result = wrap(double(21));\n"
        "console.log(JSON.stringify(result));\n")
    tsc = str(consumer / "node_modules" / ".bin" / "tsc")
    session.run([tsc, "-p", str(proj)], cwd=proj, phase="consumer", name="tsc_positive", env=env)
    run_log = session.run(["node", str(proj / "dist" / "index.js")], cwd=proj,
                          phase="consumer", name="run_positive", env=env)
    if '{"value":42}' not in run_log.read_text(errors="replace"):
        raise RuntimeError("compiled program produced unexpected output")
    if not (proj / "dist" / "util.d.ts").is_file():
        raise RuntimeError("declaration emit missing")

    (proj / "error.ts").write_text('const value: number = "not a number";\nexport { value };\n')
    neg_log = session.run([tsc, "--noEmit", "--strict", "--target", "es2019", str(proj / "error.ts")],
                          cwd=proj, phase="consumer", name="tsc_negative", env=env, check=False)
    record = session.commands[-1]
    neg_text = neg_log.read_text(errors="replace")
    if record["exit_code"] == 0 or "TS2322" not in neg_text:
        raise RuntimeError("negative consumer case did not report TS2322 with a failing exit code")
    session.write("consumer.json", {"resolved_typescript": resolved, "tarball": str(tgz),
                                    "positive_output": '{"value":42}',
                                    "negative_diagnostic": "TS2322",
                                    "negative_exit_code": record["exit_code"]})


def run(rest):
    o = opts(rest)
    input_dir = Path(o.get("input", "input")).resolve()
    output_dir = Path(o.get("output", "output")).resolve()
    jobs = min(int(o.get("jobs", 4)), 4)
    session = buildkit.Session(input_dir, output_dir, jobs)
    session.prepare()
    cache = npm_cache(input_dir, session.manifest)
    env = {"NODE_OPTIONS": "--max-old-space-size=4096", "BUILD_JOBS": str(jobs),
           "TEST_JOBS": "2", "npm_config_offline": "true"}
    if cache is not None:
        env["npm_config_cache"] = str(cache)
    install_dependencies(session, env)
    build_compiler(session, env)
    tgz = pack(session, output_dir, env)
    discovered = run_tests(session, env)
    verify_consumer(session, tgz, env)
    session.finish(features={"target": "typescript-5.9.3", "selector": TEST_SELECTOR,
                             "build_jobs": jobs, "test_jobs": 2,
                             "npm_cache": str(cache) if cache else None,
                             "compiler_test_files_discovered": discovered,
                             "tarball": str(tgz)})
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stdout.write(HELP)
        return 0
    action = argv[0]
    if action == "doctor":
        return doctor(argv[1:])
    if action == "run":
        return run(argv[1:])
    sys.stderr.write("unknown action: %s\n" % action)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
