#!/usr/bin/env python3
"""BUILDv1-D08 core profile.

Builds the etcd release toolset (etcd, etcdctl, etcdutl) from the frozen
v3.5.21 source archive with the upstream build script shipped in that
revision, runs the declared `TestStore*` MVCC selection from the module that
owns the mvcc package with `go test -json`, packages the binaries, and
consumes them from outside the source tree.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import buildkit

TASK = 'BUILDv1-D08'
RELEASE = 'v3.5.21'
VER_RE = re.compile(r'go(\d+)\.(\d+)(?:\.(\d+))?')
BINARIES = ('etcd', 'etcdctl', 'etcdutl')
MVCC_RE = ('^(TestStoreRev|TestStorePut|TestStoreRange|TestStoreDeleteRange|'
           'TestStoreCompact|TestStoreRestore)$')
SCRIPT_CANDIDATES = ('scripts/build.sh', 'build.sh')
MVCC_GO_RE = re.compile(r'(^|/)mvcc/[^/]+\.go$')
TEST_MARKERS = ('func TestStorePut', 'func TestStoreRev', 'func TestStoreRange',
                'func TestStoreRestore')


def tool_env(extra=None):
    e = {
        'GOTOOLCHAIN': 'local',
        'GOPROXY': 'off',
        'GOMODCACHE': os.environ.get('GOMODCACHE', '/workspace/cache/go-mod'),
        'GOCACHE': os.environ.get('GOCACHE', '/workspace/gocache'),
        'GOPATH': os.environ.get('GOPATH', '/workspace/gopath'),
    }
    if extra:
        e.update(extra)
    return e


def parse_ver(text):
    m = VER_RE.search(text or '')
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))


def peek_tar(archive):
    small, names = {}, set()
    try:
        with tarfile.open(archive) as t:
            for m in t.getmembers():
                if not m.isfile():
                    continue
                parts = m.name.split('/')
                rel = '/'.join(parts[1:]) if len(parts) > 1 else m.name
                names.add(rel)
                if rel in ('.go-version', 'go.mod', 'server/go.mod'):
                    fh = t.extractfile(m)
                    if fh:
                        small[rel] = fh.read().decode('utf-8', 'replace')
    except Exception as exc:  # noqa: BLE001
        small['error'] = str(exc)
    return small, names


def inventory(args):
    missing, notes = [], {}
    inp = Path(args.input)
    mf = inp / 'manifest.json'
    if not mf.is_file():
        missing.append('missing manifest: %s' % mf)
        return missing, notes
    manifest = json.loads(mf.read_text())
    src = manifest.get('source', {})
    arc = inp / src.get('filename', '')
    if not arc.is_file():
        missing.append('missing source archive: %s' % arc)
        return missing, notes
    try:
        d = buildkit.digest(arc)
    except Exception as exc:  # noqa: BLE001
        missing.append('source archive unreadable: %s' % exc)
        return missing, notes
    if d != src.get('sha256'):
        missing.append('source archive sha256 mismatch: got %s' % d)
        return missing, notes
    notes['source_archive'] = str(arc)

    small, names = peek_tar(arc)
    if small.get('.go-version'):
        notes['go_version_file'] = small['.go-version'].strip()
    if small.get('go.mod'):
        notes['go_mod_head'] = small['go.mod'][:400]
    found = [c for c in SCRIPT_CANDIDATES if c in names]
    notes['build_scripts_present'] = found
    if not found:
        missing.append('no upstream build script in archive (looked for %s)'
                       % ', '.join(SCRIPT_CANDIDATES))
    if 'server/go.mod' not in names:
        missing.append('missing server/go.mod in source archive')

    mvcc_go = sorted(n for n in names if MVCC_GO_RE.search(n))
    notes['mvcc_go_files_found'] = len(mvcc_go)
    notes['mvcc_go_sample'] = mvcc_go[:5]
    if not mvcc_go:
        missing.append('no Go sources for the mvcc package in archive '
                       '(no path matching */mvcc/*.go)')

    go = shutil.which('go')
    if not go:
        missing.append('missing go compiler on PATH')
        notes['go_version_installed'] = None
    else:
        r = subprocess.run([go, 'version'], capture_output=True, text=True)
        notes['go_version_installed'] = r.stdout.strip()
    need = parse_ver(notes.get('go_version_file', ''))
    have = parse_ver(notes.get('go_version_installed') or '')
    if need and have and have < need:
        missing.append('installed Go %d.%d.%d < required %d.%d.%d (from .go-version)'
                       % (have + need))
    env = tool_env()
    gmc = Path(env['GOMODCACHE'])
    alt = Path(env['GOPATH']) / 'pkg' / 'mod'
    populated = (gmc.is_dir() and any(gmc.iterdir())) or (alt.is_dir() and any(alt.iterdir()))
    notes['gomodcache'] = str(gmc)
    notes['gomodcache_populated'] = populated
    if not populated:
        missing.append(
            'missing Go module cache contents (GOMODCACHE=%s); etcd is unvendored '
            'and an offline GOPROXY=off build cannot resolve modules' % gmc)
    return missing, notes


def locate_build_script(src):
    for cand in SCRIPT_CANDIDATES:
        if (src / cand).is_file():
            return cand
    raise RuntimeError('source tree has no build script (%s)' % ', '.join(SCRIPT_CANDIDATES))


def _dir_has_mvcc_tests(d):
    try:
        gofiles = [p for p in d.glob('*.go') if p.is_file()]
    except OSError:
        return False
    if not gofiles:
        return False
    blob = ''
    for f in gofiles[:60]:
        try:
            blob += f.read_text(errors='replace')
        except OSError:
            continue
    return any(marker in blob for marker in TEST_MARKERS)


def discover_mvcc(src):
    """Locate the mvcc package directory and its Go module root.

    The upstream layout places it at server/mvcc, but the path is discovered
    from the extracted tree so the official selection does not depend on a
    hard-coded layout assumption.
    """
    candidates, seen = [], set()
    for p in (src / 'server' / 'storage' / 'mvcc', src / 'server' / 'mvcc',
              src / 'storage' / 'mvcc', src / 'mvcc'):
        if p.is_dir() and p not in seen:
            seen.add(p); candidates.append(p)
    try:
        for p in src.rglob('mvcc'):
            if p.is_dir() and p.name == 'mvcc' and p not in seen:
                seen.add(p); candidates.append(p)
    except OSError:
        pass
    scored = []
    for d in candidates:
        if not list(d.glob('*.go')):
            continue
        scored.append((2 if _dir_has_mvcc_tests(d) else 1, d))
    scored.sort(key=lambda t: (-t[0], len(str(t[1]))))
    diag = {
        'standard_path': str(src / 'server' / 'storage' / 'mvcc'),
        'standard_path_exists': (src / 'server' / 'storage' / 'mvcc').is_dir(),
        'standard_go_files': [p.name for p in (src / 'server' / 'storage' / 'mvcc').glob('*.go')]
            if (src / 'server' / 'storage' / 'mvcc').is_dir() else [],
        'candidate_mvcc_dirs': [str(d.relative_to(src)) for d in candidates],
        'chosen': str(scored[0][1].relative_to(src)) if scored else None,
    }
    return (scored[0][1] if scored else None), diag


def module_root(pkg, stop):
    d = pkg
    while True:
        if (d / 'go.mod').is_file():
            return d
        if d == stop or d.parent == d:
            return None
        d = d.parent


def summarise_go_json(path):
    passed, failed, skipped = set(), set(), set()
    for line in Path(path).read_text(errors='replace').splitlines():
        line = line.strip()
        if not line.startswith('{'):
            continue
        try:
            ev = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        t, a = ev.get('Test'), ev.get('Action')
        if not t:
            continue
        if a == 'pass':
            passed.add(t)
        elif a == 'fail':
            failed.add(t)
        elif a == 'skip':
            skipped.add(t)
    return {'passed': sorted(passed), 'failed': sorted(failed),
            'skipped': sorted(skipped), 'passed_count': len(passed),
            'failed_count': len(failed), 'skipped_count': len(skipped)}


def cmd_doctor(args):
    missing, notes = inventory(args)
    print(json.dumps({'task_id': TASK, 'input': str(Path(args.input).resolve()),
                      'ready': not missing, 'missing': missing, 'notes': notes},
                     indent=2))
    return 78 if missing else 0


def cmd_run(args):
    if not args.output:
        print('--output is required for run', file=sys.stderr)
        return 2
    missing, notes = inventory(args)
    if missing:
        print(json.dumps({'ready': False, 'missing': missing, 'notes': notes}, indent=2))
        return 78
    s = buildkit.Session(args.input, args.output, args.jobs)
    s.prepare()
    env = tool_env()

    # 1. Upstream build of the three release binaries.
    script = locate_build_script(s.src)
    s.run(['bash', script], cwd=s.src, phase='build', name='etcd_build',
          env=env, timeout=7200)
    for b in BINARIES:
        p = s.src / 'bin' / b
        if not p.is_file():
            raise RuntimeError('build did not produce %s' % p)
        s.run(['go', 'version', '-m', str(p)], cwd=s.src, phase='manifest',
              name='modinfo_%s' % b, env=env, timeout=180)

    # 2. Official MVCC selection with preserved JSON evidence.
    pkg, diag = discover_mvcc(s.src)
    s.write('mvcc_discovery.json', diag)
    if pkg is None:
        raise RuntimeError('mvcc package not found in source tree: '
                           + json.dumps(diag))
    root = module_root(pkg, s.src)
    if root is None:
        raise RuntimeError('no go.mod found above mvcc package %s' % pkg)
    rel = '.' if pkg == root else './' + pkg.relative_to(root).as_posix()
    log = s.test('mvcc_storage_TestStore',
                 ['go', 'test', '-json', '-count=1', '-timeout=10m',
                  '-run', MVCC_RE, rel],
                 cwd=root, parser='auto', env=env, timeout=1800)
    summary = summarise_go_json(log)
    summary['package'] = str(pkg.relative_to(s.src))
    summary['module_root'] = str(root.relative_to(s.src))
    s.write('mvcc_test_summary.json', summary)
    if summary['failed_count'] or summary['passed_count'] == 0:
        raise RuntimeError('MVCC selection did not pass: ' + json.dumps(summary))

    # 3. Package the release toolset.
    for b in BINARIES:
        shutil.copy2(s.src / 'bin' / b, s.install / b)
    for extra in ('LICENSE', 'NOTICE', 'etcd.conf.yml.sample'):
        p = s.src / extra
        if p.is_file():
            shutil.copy2(p, s.install / extra)
    archive = s.output / ('etcd-%s-linux-amd64.tar.gz' % RELEASE)
    with tarfile.open(archive, 'w:gz') as t:
        for p in sorted(s.install.rglob('*')):
            if p.is_file() and not p.is_symlink():
                t.add(p, arcname=str(Path('etcd') / p.relative_to(s.install)))

    # 4. Independent consumer verification against the packaged binaries.
    report = s.consumer / 'report.json'
    s.run([sys.executable, str(Path(__file__).resolve().parent / 'consumer.py'),
           '--bindir', str(s.install), '--workdir', str(s.consumer / 'work'),
           '--report', str(report)],
          cwd=s.consumer, phase='consumer',
          name='consumer_put_get_txn_snapshot_restore', env=env, timeout=900)
    if report.is_file():
        shutil.copy2(report, s.output / 'consumer_report.json')

    s.finish(features={'artifacts': list(BINARIES),
                       'official_tests': 'mvcc TestStore* selection',
                       'mvcc_package': summary['package'],
                       'mvcc_module_root': summary['module_root'],
                       'consumer': 'put/get/txn/snapshot/restore/continuation',
                       'release': RELEASE, 'build_script': script})
    return 0


def main():
    ap = argparse.ArgumentParser(prog='BUILDv1-D08')
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('run', 'doctor'):
        p = sub.add_parser(name)
        p.add_argument('--input', required=True)
        p.add_argument('--output')
        p.add_argument('--jobs', type=int, default=4)
    a = ap.parse_args()
    if a.cmd == 'doctor':
        return cmd_doctor(a)
    return cmd_run(a)


if __name__ == '__main__':
    sys.exit(main())
