#!/usr/bin/env python3
'''BUILDv1-E07 build Rollup native parser + Node JS distribution from frozen source.'''

import argparse
import json
import os
import shutil
import sys
import tarfile
from pathlib import Path

from buildkit import Session, digest

TASK_ID = 'BUILDv1-E07'
DEFAULT_INPUT = '/workspace/input'
DEFAULT_OUTPUT = '/workspace/output'
CACHE_ROOT = Path('/workspace/cache')

HELP = '''usage: solution/main.py {run,doctor} [--input DIR] [--output DIR] [--jobs N]
       solution/main.py --help

Commands:
  run      extract the frozen source, build the native napi parser + Node JS
           distribution with npm run build:prepare, run the official Node API
           test selection, npm-pack the tree, install the tarball and verify it
           with an independent consumer outside the source tree.
  doctor   report the exact missing source / tool / dependency items and exit
           78 (missing) or 0 (ready) without building anything.

Options:
  --input DIR   read-only input directory (default /workspace/input)
  --output DIR  writable output directory (default /workspace/output)
  --jobs N      build parallelism, capped at 4 by the session (default 4)
'''

NPM_BASE_ENV = {
    'npm_config_audit': 'false',
    'npm_config_fund': 'false',
    'npm_config_update_notifier': 'false',
    'npm_config_progress': 'false',
}

NO_DETECT_MODULE = '--no-experimental-detect-module'


def _safe_extract(archive, destination):
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            parts = Path(member.name).parts
            if not parts or '..' in parts or Path(member.name).is_absolute():
                raise ValueError('unsafe archive member: ' + member.name)
        tar.extractall(destination, filter='data')


def _archive_names(archive):
    with tarfile.open(archive) as tar:
        return [m.name for m in tar.getmembers()]


def dependency_caches(session):
    return session.manifest.get('dependency_caches') or []


def hydrate_dependency_caches(session):
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    hydrated = []
    for entry in dependency_caches(session):
        filename = entry.get('filename')
        if not filename:
            continue
        archive = session.input / filename
        if not archive.is_file():
            continue
        expected = entry.get('sha256')
        marker = CACHE_ROOT / (filename + '.hydrated')
        if marker.is_file() and (not expected or marker.read_text().strip() == expected):
            hydrated.append(filename)
            continue
        if expected and digest(archive) != expected:
            raise ValueError('dependency cache checksum mismatch: ' + str(archive))
        _safe_extract(archive, CACHE_ROOT)
        marker.write_text((expected or '') + '\n')
        hydrated.append(filename)
    return hydrated


def find_npm_cache():
    for candidate in (CACHE_ROOT / 'npm', CACHE_ROOT / 'npm-cache', CACHE_ROOT, CACHE_ROOT / 'cache'):
        if (candidate / '_cacache').is_dir():
            return candidate
    for cacache in CACHE_ROOT.rglob('_cacache'):
        if cacache.is_dir():
            return cacache.parent
    for key in ('npm_config_cache', 'NPM_CONFIG_CACHE'):
        value = os.environ.get(key)
        if value and (Path(value) / '_cacache').is_dir():
            return Path(value)
    default = Path.home() / '.npm'
    return default if (default / '_cacache').is_dir() else None


def find_cargo_home():
    for candidate in (CACHE_ROOT / 'cargo', CACHE_ROOT / 'cargo-home', CACHE_ROOT / '.cargo'):
        if (candidate / 'registry' / 'cache').is_dir():
            return candidate
    for registry in CACHE_ROOT.rglob('registry'):
        if (registry / 'cache').is_dir():
            return registry.parent
    candidates = []
    if os.environ.get('CARGO_HOME'):
        candidates.append(Path(os.environ['CARGO_HOME']))
    candidates.append(Path.home() / '.cargo')
    for home in candidates:
        if (home / 'registry' / 'cache').is_dir():
            return home
    return None


def npm_cache_expected(session):
    if find_npm_cache() is not None:
        return True
    for entry in dependency_caches(session):
        archive = session.input / (entry.get('filename') or '')
        if archive.is_file():
            try:
                names = _archive_names(archive)
            except Exception:
                continue
            if any(Path(n).name == '_cacache' for n in names):
                return True
    return False


def cargo_cache_expected(session):
    if find_cargo_home() is not None:
        return True
    for entry in dependency_caches(session):
        archive = session.input / (entry.get('filename') or '')
        if archive.is_file():
            try:
                names = _archive_names(archive)
            except Exception:
                continue
            for n in names:
                if n.endswith('/registry/cache') or n.endswith('registry/cache'):
                    return True
    return False


def doctor(session):
    missing = []
    man = session.manifest.get('source', {})
    archive = session.input / man.get('filename', 'source.tar.gz')
    if not archive.is_file():
        missing.append('missing source archive: ' + str(archive))
    elif man.get('sha256') and digest(archive) != man.get('sha256'):
        missing.append('source archive checksum mismatch: ' + str(archive))
    for tool in ('node', 'npm', 'cargo', 'rustc'):
        if not shutil.which(tool):
            missing.append('missing executable on PATH: ' + tool)
    if not dependency_caches(session):
        missing.append('manifest declares no dependency_caches; offline build impossible')
    else:
        if not npm_cache_expected(session):
            missing.append('missing npm offline cache (_cacache); hydrate dependencies.tar.gz into /workspace/cache/npm')
        if not cargo_cache_expected(session):
            missing.append('Rust cargo registry cache still being prepared: no registry/cache in dependencies.tar.gz, in CARGO_HOME, or in ~/.cargo')
    print('doctor: ' + ('READY' if not missing else 'MISSING'))
    for item in missing:
        print('  - ' + item)
    return 78 if missing else 0


def build_env(session, npm_cache, cargo_home):
    env = dict(NPM_BASE_ENV)
    if npm_cache is not None:
        env['npm_config_cache'] = str(npm_cache)
    env['CARGO_NET_OFFLINE'] = 'true'
    env['CARGO_TERM_COLOR'] = 'never'
    env['CARGO_BUILD_JOBS'] = str(session.jobs)
    env['BUILD_JOBS'] = str(session.jobs)
    if cargo_home is not None:
        env['CARGO_HOME'] = str(cargo_home)
    if shutil.which('rustup'):
        env['RUSTUP_TOOLCHAIN'] = os.environ.get('RUSTUP_TOOLCHAIN', 'stable')
    return env


def test_env(session, npm_cache, cargo_home):
    env = build_env(session, npm_cache, cargo_home)
    existing = os.environ.get('NODE_OPTIONS', '').strip()
    if NO_DETECT_MODULE not in existing.split():
        env['NODE_OPTIONS'] = (existing + ' ' + NO_DETECT_MODULE).strip()
    else:
        env['NODE_OPTIONS'] = existing
    return env


CJS_CONSUMER = r'''const assert = require('assert');
const fs = require('fs');
const path = require('path');

async function main() {
  const rollupDir = path.dirname(require.resolve('rollup/package.json'));
  const natives = fs.readdirSync(path.join(rollupDir, 'dist')).filter(f => f.endsWith('.node'));
  assert.ok(natives.length > 0, 'fresh native .node missing from installed rollup dist');

  const { rollup } = require('rollup');
  const bundle = await rollup({ input: path.join(__dirname, 'entry.js'), onwarn() {} });
  const { output } = await bundle.generate({ format: 'cjs', sourcemap: true, exports: 'named' });
  const chunk = output.find(o => o.type === 'chunk');
  assert.ok(!chunk.code.includes('should-not-appear'), 'tree-shaking failed: unused export retained');
  assert.ok(chunk.code.includes('42'), 'used export missing from bundle');
  assert.ok(chunk.map && chunk.map.sources.length >= 1, 'source map missing or empty');
  fs.writeFileSync(path.join(__dirname, 'api-out.cjs'), chunk.code);
  const mod = require('./api-out.cjs');
  assert.strictEqual(mod.answer, 49, 'runtime semantic mismatch: ' + mod.answer);

  const multi = await rollup({
    input: [path.join(__dirname, 'entry.js'), path.join(__dirname, 'entry2.js')],
    onwarn() {},
  });
  const multiOut = await multi.generate({ format: 'cjs', exports: 'named' });
  assert.ok(multiOut.output.length >= 3, 'expected two entry chunks plus a shared chunk');
  console.log('consumer.cjs OK native=' + natives.join(','));
}

main().catch(error => { console.error(error); process.exit(1); });
'''

ESM_CONSUMER = r'''import assert from 'node:assert';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const dir = path.dirname(fileURLToPath(import.meta.url));
const { rollup } = await import('rollup');

const bundle = await rollup({ input: path.join(dir, 'entry.js'), onwarn() {} });
const { output } = await bundle.generate({ format: 'es' });
const chunk = output.find(o => o.type === 'chunk');
assert.ok(chunk.code.includes('42'), 'used export missing from ESM bundle');
assert.ok(!chunk.code.includes('should-not-appear'), 'tree-shaking failed in ESM path');
console.log('consumer.mjs OK');
'''

CLI_VERIFY = r'''const assert = require('assert');
const fs = require('fs');
const path = require('path');

const mod = require('./cli-out.cjs');
assert.strictEqual(mod.answer, 49, 'CLI output runtime mismatch: ' + mod.answer);
assert.ok(fs.existsSync(path.join(__dirname, 'cli-out.cjs.map')), 'CLI source map missing');
console.log('cli verify OK');
'''


def _write_consumer_files(consumer):
    files = {
        'lib.js': 'export function used() { return 42; }\nexport function unused() { return 99; }\n',
        'shared.js': 'export function shared() { return 7; }\n',
        'entry.js': "import { used } from './lib.js';\nimport { shared } from './shared.js';\nexport const answer = used() + shared();\n",
        'entry2.js': "import { shared } from './shared.js';\nexport const second = shared() * 2;\n",
        'consumer.cjs': CJS_CONSUMER,
        'consumer.mjs': ESM_CONSUMER,
        'verify_cli.cjs': CLI_VERIFY,
    }
    for name, content in files.items():
        (consumer / name).write_text(content)


def _reset(path):
    if path.exists():
        for child in list(path.iterdir()):
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    else:
        path.mkdir(parents=True)


def run(session):
    session.prepare()
    src = session.src
    hydrated = hydrate_dependency_caches(session)
    npm_cache = find_npm_cache()
    cargo_home = find_cargo_home()
    if npm_cache is None:
        raise RuntimeError('npm offline cache unavailable; run doctor for the exact missing item')
    if cargo_home is None:
        raise RuntimeError('Rust cargo registry cache still being prepared; no registry/cache found')
    env = build_env(session, npm_cache, cargo_home)
    t_env = test_env(session, npm_cache, cargo_home)
    session.write('caches.json', {
        'hydrated_archives': hydrated,
        'npm_cache': str(npm_cache),
        'cargo_home': str(cargo_home),
        'node_options_for_tests': t_env.get('NODE_OPTIONS'),
    })

    session.run(['npm', 'ci', '--offline', '--no-audit', '--no-fund', '--ignore-scripts'],
                cwd=src, phase='deps', name='npm_ci', env=env, timeout=2400)
    session.run(['npm', 'run', 'build:prepare'],
                cwd=src, phase='build', name='build_prepare', env=env, timeout=7200)

    dist = src / 'dist'
    natives = sorted(p.name for p in dist.glob('*.node'))
    js_entries = [p for p in ('rollup.js', 'es/rollup.js', 'bin/rollup') if (dist / p).is_file()]
    if not natives:
        raise RuntimeError('build did not produce a dist/*.node native parser artifact')
    if len(js_entries) < 3:
        raise RuntimeError('build is missing JS entry points: ' + str(js_entries))
    session.write('build_artifacts.json', {
        'natives': natives,
        'js_entries': js_entries,
        'dist_files': sorted(str(p.relative_to(dist)) for p in dist.rglob('*') if p.is_file()),
    })

    session.test('test:only', ['npm', 'run', 'test:only'], cwd=src, env=t_env, timeout=7200)
    session.test('test:options', ['npm', 'run', 'test:options'], cwd=src, env=t_env, timeout=1800)
    session.test('test:package', ['npm', 'run', 'test:package'], cwd=src, env=t_env, timeout=900)

    pack_dir = session.output / 'pack'
    _reset(pack_dir)
    session.run(['npm', 'pack', '--ignore-scripts', '--pack-destination', str(pack_dir)],
                cwd=src, phase='package', name='npm_pack', env=env, timeout=900)
    tarballs = sorted(pack_dir.glob('rollup-*.tgz'))
    if not tarballs:
        raise RuntimeError('npm pack produced no tarball')
    tarball = tarballs[-1]
    session.write('pack.json', {
        'tarball': str(tarball.relative_to(session.output)),
        'bytes': tarball.stat().st_size,
        'sha256': digest(tarball),
    })

    _reset(session.install)
    (session.install / 'package.json').write_text(json.dumps(
        {'name': 'rollup-install-root', 'version': '1.0.0', 'private': True}))
    session.run(['npm', 'install', '--offline', '--no-audit', '--no-fund', '--no-save',
                 '--ignore-scripts', str(tarball)],
                cwd=session.install, phase='install', name='install_tgz', env=env, timeout=900)

    _reset(session.consumer)
    _write_consumer_files(session.consumer)
    (session.consumer / 'package.json').write_text(json.dumps(
        {'name': 'rollup-consumer', 'version': '1.0.0', 'private': True, 'type': 'commonjs'}))
    session.run(['npm', 'install', '--offline', '--no-audit', '--no-fund', '--no-save',
                 '--ignore-scripts', str(tarball)],
                cwd=session.consumer, phase='consumer_install', name='consumer_install_tgz',
                env=env, timeout=900)
    session.run(['node', 'consumer.cjs'], cwd=session.consumer, phase='consumer',
                name='consumer_api_cjs', env=env, timeout=300)
    session.run(['node', 'consumer.mjs'], cwd=session.consumer, phase='consumer',
                name='consumer_api_esm', env=env, timeout=300)
    session.run(['node', 'node_modules/rollup/dist/bin/rollup', 'entry.js', '--format', 'cjs',
                 '--file', 'cli-out.cjs', '--sourcemap'],
                cwd=session.consumer, phase='consumer', name='consumer_cli', env=env, timeout=300)
    session.run(['node', 'verify_cli.cjs'], cwd=session.consumer, phase='consumer',
                name='consumer_cli_verify', env=env, timeout=120)

    session.finish(features={
        'task': TASK_ID,
        'native_parser': natives,
        'js_entries': js_entries,
        'tarball_sha256': digest(tarball),
        'build_baseline': 'npm run build:prepare',
        'npm_cache': str(npm_cache),
        'cargo_home': str(cargo_home),
        'node_options_for_tests': t_env.get('NODE_OPTIONS'),
        'consumer': 'require + import + CLI verified from /workspace/consumer outside src',
    })
    return 0


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ('-h', '--help', 'help'):
        sys.stdout.write(HELP)
        return 0
    command = argv[0]
    if command not in ('run', 'doctor'):
        sys.stderr.write('unknown command: ' + command + '\n' + HELP)
        return 2
    parser = argparse.ArgumentParser(prog='solution/main.py', add_help=False)
    parser.add_argument('--input', default=DEFAULT_INPUT)
    parser.add_argument('--output', default=DEFAULT_OUTPUT)
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args(argv[1:])
    try:
        session = Session(args.input, args.output, args.jobs)
    except Exception as error:
        sys.stderr.write(command + ': cannot read input: ' + str(error) + '\n')
        return 78
    if command == 'doctor':
        return doctor(session)
    return run(session)


if __name__ == '__main__':
    sys.exit(main())
