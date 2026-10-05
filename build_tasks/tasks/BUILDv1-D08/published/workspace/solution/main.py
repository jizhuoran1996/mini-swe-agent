#!/usr/bin/env python3
"""BUILDv1-D08 core profile.

Build the etcd release toolset (etcd, etcdctl, etcdutl) from the frozen
v3.5.21 source archive using the official scripts/build.sh, execute the
declared MVCC TestStore* tests with JSON evidence, package the binaries,
and independently consume them (put/get, conditional txn, snapshot,
restore, continuation) with the packaged etcdctl/etcdutl.
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


def tool_env(extra=None):
    e = {
        'GOTOOLCHAIN': 'local',
        'GOPROXY': 'off',
        'GOFLAGS': '-mod=mod',
        'GOMODCACHE': os.environ.get('GOMODCACHE', '/workspace/gomodcache'),
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
    out = {}
    try:
        with tarfile.open(archive) as t:
            for m in t.getmembers():
                if not m.isfile():
                    continue
                parts = m.name.split('/')
                if len(parts) == 2 and parts[1] in ('.go-version', 'go.mod'):
                    fh = t.extractfile(m)
                    if fh:
                        out[parts[1]] = fh.read().decode('utf-8', 'replace')
                if len(out) >= 2:
                    break
    except Exception as exc:  # noqa: BLE001 - report concretely
        out['error'] = str(exc)
    return out


def inventory(args):
    """Return (missing list, notes dict) describing exact blocking items."""
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
    else:
        try:
            d = buildkit.digest(arc)
        except Exception as exc:  # noqa: BLE001
            missing.append('source archive unreadable: %s' % exc)
        else:
            if d != src.get('sha256'):
                missing.append('source archive sha256 mismatch: got %s' % d)
            else:
                notes['source_archive'] = str(arc)
                parsed = peek_tar(arc)
                if parsed.get('.go-version'):
                    notes['go_version_file'] = parsed['.go-version'].strip()
                if parsed.get('go.mod'):
                    notes['go_mod_head'] = parsed['go.mod'][:400]
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
        missing.append(
            'installed Go %d.%d.%d < required %d.%d.%d (from .go-version)'
            % (have + need))
    env = tool_env()
    gmc = Path(env['GOMODCACHE'])
    alt = Path(env['GOPATH']) / 'pkg' / 'mod'
    populated = (gmc.is_dir() and any(gmc.iterdir())) or (alt.is_dir() and any(alt.iterdir()))
    notes['gomodcache'] = str(gmc)
    notes['gomodcache_populated'] = populated
    if not populated:
        missing.append(
            'missing Go module cache contents (GOMODCACHE=%s); '
            'etcd is unvendored and an offline GOPROXY=off build cannot resolve modules'
            % gmc)
    return missing, notes


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
        print(json.dumps({'ready': False, 'missing': missing, 'notes': notes},
                         indent=2))
        return 78
    s = buildkit.Session(args.input, args.output, args.jobs)
    s.prepare()
    env = tool_env()

    # 1. Official build of the three release binaries.
    s.run(['./scripts/build.sh'], cwd=s.src, phase='build', name='etcd_build',
          env=env, timeout=7200)
    for b in BINARIES:
        p = s.src / 'bin' / b
        if not p.is_file():
            raise RuntimeError('build did not produce %s' % p)
    for b in BINARIES:
        s.run(['go', 'version', '-m', str(s.src / 'bin' / b)], cwd=s.src,
              phase='manifest', name='modinfo_%s' % b, env=env, timeout=180)

    # 2. Official MVCC test selection with JSON evidence preserved.
    log = s.test('mvcc_storage_TestStore',
                 ['go', 'test', '-json', '-count=1', '-timeout=10m',
                  '-run', MVCC_RE, './storage/mvcc'],
                 cwd=s.src / 'server', parser='auto', env=env, timeout=1800)
    summary = summarise_go_json(log)
    s.write('mvcc_test_summary.json', summary)
    if summary['failed_count'] or summary['passed_count'] == 0:
        raise RuntimeError('MVCC selection did not pass: ' + json.dumps(summary))

    # 3. Package the release toolset into output/install and an archive.
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
                       'official_tests': 'server/storage/mvcc TestStore*',
                       'consumer': 'put/get/txn/snapshot/restore/continuation',
                       'release': RELEASE})
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
