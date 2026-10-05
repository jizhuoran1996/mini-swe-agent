#!/usr/bin/env python3
"""Independent consumer for the freshly built etcd release toolset.

Starts a single-member etcd on loopback, does put/get, a conditional
transaction, saves a snapshot, restores it to a NEW data directory with
the packaged etcdutl, restarts, re-verifies the keys and continues by
writing another key and checking that the revision advances.
"""
import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def run(argv, stdin=None):
    r = subprocess.run(argv, capture_output=True, text=True, stdin=stdin)
    if r.returncode:
        raise RuntimeError('cmd failed rc=%d argv=%r\nstdout=%s\nstderr=%s'
                           % (r.returncode, argv, r.stdout[-2000:], r.stderr[-2000:]))
    return r.stdout


def wait_ready(etcdctl, endpoint, timeout=60):
    end = time.time() + timeout
    last = ''
    while time.time() < end:
        r = subprocess.run(
            [etcdctl, '--endpoints=' + endpoint, '--command-timeout=3s',
             'endpoint', 'health'], capture_output=True, text=True)
        last = (r.stdout or '') + (r.stderr or '')
        if r.returncode == 0 and 'healthy' in last.lower():
            return
        time.sleep(0.4)
    raise RuntimeError('etcd not ready: ' + last[-500:])


def start(etcd, datadir, cport, pport, name='e1'):
    argv = [etcd, '--name', name, '--data-dir', datadir,
            '--listen-client-urls', 'http://127.0.0.1:%d' % cport,
            '--advertise-client-urls', 'http://127.0.0.1:%d' % cport,
            '--listen-peer-urls', 'http://127.0.0.1:%d' % pport,
            '--initial-advertise-peer-urls', 'http://127.0.0.1:%d' % pport,
            '--initial-cluster', '%s=http://127.0.0.1:%d' % (name, pport),
            '--initial-cluster-state', 'new',
            '--initial-cluster-token', 'buildv1-d08', '--logger', 'zap']
    log = open(datadir + '.log', 'wb')
    return subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT), log


def stop(proc, log):
    proc.terminate()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    log.close()


def rev_of(etcdctl, endpoint):
    raw = run([etcdctl, '--endpoints=' + endpoint, 'endpoint', 'status',
               '--write-out=json'])
    data = json.loads(raw)
    if isinstance(data, list):
        data = data[0]
    return data['header']['revision']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--bindir', required=True)
    ap.add_argument('--workdir', required=True)
    ap.add_argument('--report', required=True)
    a = ap.parse_args()
    bin_ = Path(a.bindir).resolve()
    wd = Path(a.workdir).resolve()
    wd.mkdir(parents=True, exist_ok=True)
    etcd = str(bin_ / 'etcd')
    etcdctl = str(bin_ / 'etcdctl')
    etcdutl = str(bin_ / 'etcdutl')

    steps = {}
    c1, p1 = free_port(), free_port()
    ep1 = '127.0.0.1:%d' % c1
    proc, log = start(etcd, str(wd / 'data1'), c1, p1)
    try:
        wait_ready(etcdctl, ep1)
        run([etcdctl, '--endpoints=' + ep1, 'put', 'pk', 'pv'])
        got = run([etcdctl, '--endpoints=' + ep1, 'get', 'pk',
                   '--print-value-only']).strip()
        assert got == 'pv', 'put/get mismatch: %r' % got
        steps['put_get'] = 'ok'

        txn = ('compares:\nvalue("pk") = "pv"\n\n'
               'success requests (get, put, del):\nput tk tv\n\n'
               'failure requests (get, put, del):\nput tk bad\n\nCOMMIT\n')
        tfile = wd / 'txn.txt'
        tfile.write_text(txn)
        with tfile.open() as fh:
            out = run([etcdctl, '--endpoints=' + ep1, 'txn'], stdin=fh)
        tk = run([etcdctl, '--endpoints=' + ep1, 'get', 'tk',
                  '--print-value-only']).strip()
        assert tk == 'tv', 'txn success path wrong: %r\n%s' % (tk, out)
        steps['txn'] = 'ok'

        snap = wd / 'snapshot.db'
        run([etcdctl, '--endpoints=' + ep1, 'snapshot', 'save', str(snap)])
        assert snap.is_file() and snap.stat().st_size > 0, 'snapshot missing'
        steps['snapshot_bytes'] = snap.stat().st_size
    finally:
        stop(proc, log)

    c2, p2 = free_port(), free_port()
    ep2 = '127.0.0.1:%d' % c2
    run([etcdutl, 'snapshot', 'restore', str(wd / 'snapshot.db'),
         '--data-dir', str(wd / 'data2'), '--name', 'e1',
         '--initial-cluster', 'e1=http://127.0.0.1:%d' % p2,
         '--initial-advertise-peer-urls', 'http://127.0.0.1:%d' % p2])
    steps['restore'] = 'ok'

    proc2, log2 = start(etcd, str(wd / 'data2'), c2, p2)
    try:
        wait_ready(etcdctl, ep2)
        for k, v in (('pk', 'pv'), ('tk', 'tv')):
            got = run([etcdctl, '--endpoints=' + ep2, 'get', k,
                       '--print-value-only']).strip()
            assert got == v, 'restored %s mismatch: %r' % (k, got)
        steps['restore_verify'] = 'ok'

        before = rev_of(etcdctl, ep2)
        run([etcdctl, '--endpoints=' + ep2, 'put', 'nk', 'nv'])
        after = rev_of(etcdctl, ep2)
        nv = run([etcdctl, '--endpoints=' + ep2, 'get', 'nk',
                  '--print-value-only']).strip()
        assert nv == 'nv' and after > before, \
            'continuation failed: %s->%s nv=%r' % (before, after, nv)
        steps['continuation'] = {'revision_before': before, 'revision_after': after}
    finally:
        stop(proc2, log2)

    Path(a.report).write_text(json.dumps(
        {'consumer': 'packaged etcd/etcdctl/etcdutl', 'status': 'ok',
         'steps': steps}, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
