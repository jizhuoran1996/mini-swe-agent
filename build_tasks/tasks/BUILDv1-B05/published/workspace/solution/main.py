#!/usr/bin/env python3
"""BUILDv1-B05 (CORE profile).

Build Node.js from the frozen v22.16.0 source archive with a fixed, local
small-icu configuration, run the official stream + message test sub-systems
using the *installed* node binary (via ``--shell``), install the runtime and
verify it from a consumer located outside the source tree.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import sys
import tarfile
import time
from pathlib import Path

TOOLS = ('gcc', 'g++', 'make', 'python3', 'tar')

CHECK_JS = r'''
'use strict';
const assert = require('assert');
const { Worker } = require('worker_threads');
const { fork } = require('child_process');
const { Readable, Transform } = require('stream');

(async () => {
  const result = {};
  assert.strictEqual(process.execPath, process.env.EXPECTED_NODE, 'execPath');
  assert.strictEqual(process.versions.node, process.env.EXPECTED_VERSION, 'node version');
  result.execPath = process.execPath;
  result.node = process.versions.node;
  result.icu = process.versions.icu || null;
  result.v8 = process.versions.v8;
  // The real, portable signal that ICU is compiled in is process.versions.icu.
  assert.ok(result.icu, 'ICU version must be present');
  // Record (do not assert) configure-derived flags, which differ between
  // Node revisions and intl modes.
  const variables = (process.config && process.config.variables) || {};
  result.nodeUseIcu = variables.node_use_icu === undefined ? null : variables.node_use_icu;
  result.icuSmall = variables.icu_small === undefined ? null : variables.icu_small;

  // Exercise the compiled ICU data end to end.
  result.numberFormat = new Intl.NumberFormat('en-US').format(1234567.89);
  assert.strictEqual(result.numberFormat, '1,234,567.89');
  result.deLocale = new Intl.DateTimeFormat('de-DE').resolvedOptions().locale;

  const chunks = [];
  await new Promise((resolve, reject) => {
    Readable.from(['a', 'b', 'c'])
      .pipe(new Transform({ transform(c, e, cb) { cb(null, c.toString().toUpperCase()); } }))
      .on('data', (d) => chunks.push(d.toString()))
      .on('end', resolve)
      .on('error', reject);
  });
  result.stream = chunks.join('');
  assert.strictEqual(result.stream, 'ABC');

  result.worker = await new Promise((resolve, reject) => {
    const w = new Worker('const { parentPort } = require("worker_threads");' +
      'let s = 0; for (let i = 1; i <= 10; i++) s += i; parentPort.postMessage(s);',
      { eval: true });
    w.on('message', resolve);
    w.on('error', reject);
  });
  assert.strictEqual(result.worker, 55);

  result.child = await new Promise((resolve, reject) => {
    const c = fork(process.env.CHILD_SCRIPT, ['7'], { stdio: ['ignore', 'pipe', 'inherit', 'ipc'] });
    let buf = '';
    c.stdout.on('data', (d) => { buf += d; });
    c.on('exit', (code) => (code === 0 ? resolve(buf.trim()) : reject(new Error('child exit ' + code))));
  });
  assert.strictEqual(result.child, 'sum-28');

  process.stdout.write('CHECK ' + JSON.stringify(result) + '\n');
})().catch((err) => { console.error((err && err.stack) || String(err)); process.exit(1); });
'''

CHILD_JS = r'''
'use strict';
const n = Number(process.argv[2] || 0);
let sum = 0;
for (let i = 1; i <= n; i++) sum += i;
process.stdout.write('sum-' + sum);
'''

SERVER_JS = r'''
'use strict';
const http = require('http');
const server = http.createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'text/plain', 'X-Node': process.versions.node });
  res.end('hello-from-node\n');
});
server.listen(0, '127.0.0.1', () => {
  process.stdout.write('PORT=' + server.address().port + '\n');
});
process.stdin.resume();
process.stdin.on('end', () => server.close(() => process.exit(0)));
setTimeout(() => server.close(() => process.exit(0)), 30000).unref();
'''

CONSUMER_PY = r'''#!/usr/bin/env python3
"""Independent consumer: drives the freshly installed node binary."""
import json
import os
import select
import socket
import subprocess
import sys
import time


def fail(msg):
    sys.stderr.write('CONSUMER FAILURE: %s\n' % msg)
    raise SystemExit(1)


def main():
    node = sys.argv[1]
    cdir = sys.argv[2]

    r = subprocess.run([node, os.path.join(cdir, 'check_runtime.js')],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        fail('runtime check exit %d\n%s\n%s' % (r.returncode,
                                                r.stdout.decode(errors='replace'),
                                                r.stderr.decode(errors='replace')))
    lines = [l for l in r.stdout.decode().splitlines() if l.startswith('CHECK ')]
    if not lines:
        fail('runtime check produced no CHECK line:\n' + r.stdout.decode(errors='replace'))
    info = json.loads(lines[-1][len('CHECK '):])
    print('runtime-check: ' + json.dumps(info, sort_keys=True))

    proc = subprocess.Popen([node, os.path.join(cdir, 'server.js')],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    port = None
    end = time.time() + 25
    while time.time() < end:
        ready, _, _ = select.select([proc.stdout], [], [], max(0.0, end - time.time()))
        if not ready:
            break
        raw = proc.stdout.readline()
        if not raw:
            break
        text = raw.decode().strip()
        if text.startswith('PORT='):
            port = int(text.split('=', 1)[1])
            break
    if port is None:
        try:
            out, err = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
        fail('node server did not announce a port: ' + err.decode(errors='replace'))

    with socket.create_connection(('127.0.0.1', port), timeout=10) as sock:
        sock.sendall(b'GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n')
        data = b''
        while True:
            part = sock.recv(4096)
            if not part:
                break
            data += part
    if b'hello-from-node' not in data:
        proc.kill()
        fail('unexpected loopback response: %r' % data[:200])
    print('loopback-http: ok (port %d)' % port)

    proc.stdin.close()
    rc = proc.wait(timeout=30)
    if rc != 0:
        fail('node server exited with %d' % rc)
    print('server-exit: 0')
    print('CONSUMER OK')
    return 0


sys.exit(main())
'''


def doctor(input_dir):
    missing = []
    inp = Path(input_dir)
    if not inp.is_dir():
        missing.append('input directory: %s' % inp)
        print('doctor: NOT READY')
        for item in missing:
            print('  missing: %s' % item)
        return 78

    manifest_path = inp / 'manifest.json'
    if not manifest_path.is_file():
        missing.append('manifest: %s' % manifest_path)
        manifest = None
    else:
        manifest = json.loads(manifest_path.read_text())

    if manifest is not None:
        archive = inp / manifest['source']['filename']
        if not archive.is_file():
            missing.append('source archive: %s' % archive)
        else:
            h = hashlib.sha256()
            with archive.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1 << 20), b''):
                    h.update(chunk)
            if h.hexdigest() != manifest['source']['sha256']:
                missing.append('source archive sha256 mismatch: %s' % archive)
            else:
                try:
                    with tarfile.open(archive) as tf:
                        found = set()
                        for member in tf:
                            parts = Path(member.name).parts
                            if len(parts) >= 2:
                                found.add(parts[1])
                            if 'deps' in found and 'configure.py' in found and 'tools' in found:
                                break
                    for need in ('configure.py', 'deps', 'tools'):
                        if need not in found:
                            missing.append('archive is missing top-level entry: %s' % need)
                except tarfile.TarError as exc:
                    missing.append('source archive unreadable: %s' % exc)

    for tool in TOOLS:
        if shutil.which(tool) is None:
            missing.append('tool: %s' % tool)

    if missing:
        print('doctor: NOT READY for %s' % inp)
        for item in missing:
            print('  missing: %s' % item)
        return 78
    print('doctor: READY (frozen source archive + toolchain for CORE small-icu Node build)')
    return 0


def _selector(path, test_root):
    """Node's tools/test.py expects a selector relative to the test ROOT
    (``test/``), without the leading ``test/`` and without the ``.js``
    suffix: e.g. ``parallel/test-stream-legacy``."""
    rel = Path(path).relative_to(test_root).as_posix()
    if rel.endswith('.js'):
        rel = rel[:-3]
    return rel


def run_build(args):
    import buildkit

    session = buildkit.Session(args.input, args.output, jobs=args.jobs)
    src = session.prepare()
    install = session.install

    work_home = session.build / 'home'
    tmp = session.build / 'tmp'
    work_home.mkdir(parents=True, exist_ok=True)
    tmp.mkdir(parents=True, exist_ok=True)
    env = {
        'HOME': str(work_home),
        'TMPDIR': str(tmp),
        'TMP': str(tmp),
        'TEMP': str(tmp),
        'CC': 'gcc',
        'CXX': 'g++',
        'PYTHON': 'python3',
        'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
        'LANG': 'C',
        'LC_ALL': 'C',
    }

    version_header = (src / 'src' / 'node_version.h').read_text(errors='replace')

    def version_part(key):
        match = re.search(r'#define %s (\d+)' % key, version_header)
        return match.group(1) if match else '0'

    version = '.'.join(version_part(k) for k in
                       ('NODE_MAJOR_VERSION', 'NODE_MINOR_VERSION', 'NODE_PATCH_VERSION'))

    configure_text = (src / 'configure.py').read_text(errors='replace')
    temporal_flag = '--v8-disable-temporal-support' if 'disable-temporal-support' in configure_text else None

    options = ['--prefix=%s' % install, '--with-intl=small-icu']
    if temporal_flag:
        options.append(temporal_flag)

    test_jobs = min(session.jobs, 2)
    features = {
        'profile': 'core',
        'node_version': version,
        'intl': 'small-icu (data generated from the in-tree deps/icu-small)',
        'icu_external_source': False,
        'temporal': temporal_flag or 'flag not present in this revision',
        'configure_options': options,
        'build_jobs': session.jobs,
        'test_jobs': test_jobs,
        'test_shell': str(install / 'bin' / 'node'),
    }
    session.write('features.json', features)

    session.run(['python3', 'configure.py'] + options, cwd=src, phase='configure',
                name='configure', env=env, timeout=1200)

    session.run(['make', '-j%d' % session.jobs], cwd=src, phase='build',
                name='make', env=env, timeout=10800)

    session.run(['make', 'install'], cwd=src, phase='install',
                name='make_install', env=env, timeout=2400)

    node = install / 'bin' / 'node'
    session.run([str(node), '--version'], cwd=session.consumer, phase='install',
                name='installed_version', env=env, timeout=180)

    with tarfile.open(session.output / 'node-runtime.tar.gz', 'w:gz') as archive:
        archive.add(install, arcname='node')

    # Frozen official test inventory, captured before execution.
    test_root = src / 'test'
    stream_files = sorted(glob.glob(str(test_root / 'parallel' / 'test-stream-*.js')))
    stream_selector = [_selector(f, test_root) for f in stream_files]
    message_dir = test_root / 'message'
    message_files = sorted(str(p) for p in message_dir.rglob('*.js')) if message_dir.is_dir() else []
    message_selector = [_selector(f, test_root) for f in message_files] or ['message']

    session.write('test_inventory.json', {
        'selector_format': 'parallel/test-name (relative to test/, no .js suffix, no leading test/)',
        'streams': {'files': stream_selector, 'count': len(stream_selector)},
        'message': {'files': message_selector, 'count': len(message_selector)},
        'parallel_flag': '-j %d' % test_jobs,
        'shell': str(node),
    })

    if stream_selector:
        session.test('streams',
                     ['python3', 'tools/test.py', '-j', str(test_jobs),
                      '--shell', str(node)] + stream_selector,
                     cwd=src, timeout=5400, env=env)
    session.test('message',
                 ['python3', 'tools/test.py', '-j', str(test_jobs),
                  '--shell', str(node)] + message_selector,
                 cwd=src, timeout=2400, env=env)

    consumer = session.consumer
    (consumer / 'check_runtime.js').write_text(CHECK_JS)
    (consumer / 'child.js').write_text(CHILD_JS)
    (consumer / 'server.js').write_text(SERVER_JS)
    (consumer / 'consumer.py').write_text(CONSUMER_PY)

    consumer_env = dict(env)
    consumer_env.update({
        'EXPECTED_NODE': str(node),
        'EXPECTED_VERSION': version,
        'CHILD_SCRIPT': str(consumer / 'child.js'),
    })
    session.run(['python3', str(consumer / 'consumer.py'), str(node), str(consumer)],
                cwd=consumer, phase='consumer', name='consumer', env=consumer_env, timeout=900)

    features['consumer'] = 'check_runtime.js + loopback http served by the installed node, driven by consumer.py'
    session.finish(features=features)
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog='main.py',
        description='BUILDv1-B05 CORE: source-build Node.js (small-icu) and verify it.')
    sub = parser.add_subparsers(dest='cmd')

    doctor_parser = sub.add_parser('doctor', help='report missing source/tool prerequisites (exit 78 if not ready)')
    doctor_parser.add_argument('--input', required=True)

    run_parser = sub.add_parser('run', help='configure, build, install and verify Node.js')
    run_parser.add_argument('--input', required=True)
    run_parser.add_argument('--output', required=True)
    run_parser.add_argument('--jobs', type=int, default=4)

    args = parser.parse_args()
    if args.cmd == 'doctor':
        return doctor(args.input)
    if args.cmd == 'run':
        return run_build(args)
    parser.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
