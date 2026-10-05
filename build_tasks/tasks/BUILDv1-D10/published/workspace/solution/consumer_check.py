#!/usr/bin/env python3
"""Single-route local consumer for the packaged Envoy binary.

Runs outside the source tree: starts a fixture HTTP upstream and the packaged
Envoy, drives one static route with header propagation, then exercises the
upstream-down error path (503). Also asserts Envoy emits progress evidence on
its admin endpoint (ready + stats) and that the listener actually served a
request, before the negative case. Writes JSON and exits nonzero on failure.

HTTP field names are case-insensitive per RFC 7230/9110. Envoy's HTTP/1
responses preserve the case defined by the filter/route (lowercase for the
upstream response header here), so every response header is stored in a
case-insensitive mapping and looked up by normalized (lowercase) name.
"""
import argparse
import http.server
import json
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


def free_port():
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class HeaderMap:
    """Case-insensitive HTTP header mapping (RFC 9110 field-name semantics)."""

    def __init__(self, items=()):
        self._store = {}
        for name, value in items:
            self._store[str(name).lower()] = value

    def get(self, name, default=None):
        return self._store.get(str(name).lower(), default)

    def __contains__(self, name):
        return str(name).lower() in self._store

    def items(self):
        return self._store.items()


class Fixture(http.server.BaseHTTPRequestHandler):
    server_version = 'Fixture/1.0'

    def do_GET(self):
        payload = json.dumps({'path': self.path,
                              'echo_x_test': self.headers.get('x-test', '')}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('X-Upstream', 'fixture')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


def http_get(url, headers=None, timeout=5):
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, HeaderMap(response.headers.items()), response.read().decode(errors='replace')
    except urllib.error.HTTPError as error:
        return error.code, HeaderMap(error.headers.items() if error.headers else ()), error.read().decode(errors='replace')


def wait_ready(admin_port, timeout=45):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            status, _, body = http_get(f'http://127.0.0.1:{admin_port}/ready', timeout=2)
            if status == 200 and 'LIVE' in body:
                return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--envoy', required=True)
    parser.add_argument('--config', required=True)
    parser.add_argument('--result', required=True)
    args = parser.parse_args()

    checks = {}
    envoy_proc = None
    server = None
    log_file = None

    admin_port = free_port()
    listener_port = free_port()
    upstream_port = free_port()

    text = Path(args.config).read_text()
    text = (text.replace('10001', str(upstream_port))
                .replace('9901', str(admin_port))
                .replace('10000', str(listener_port)))
    config_path = Path(args.result).with_suffix('.bootstrap.yaml')
    config_path.write_text(text)
    log_path = Path(args.result).with_suffix('.envoy.log')
    log_file = log_path.open('wb')

    version = subprocess.run([args.envoy, '--version'], capture_output=True, text=True, timeout=60)
    checks['version_exit'] = version.returncode
    checks['version_stdout'] = version.stdout.strip().splitlines()[:1]

    server = http.server.ThreadingHTTPServer(('127.0.0.1', upstream_port), Fixture)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    base_id = (free_port() % 500) + 1
    envoy_proc = subprocess.Popen(
        [args.envoy, '-c', str(config_path), '--base-id', str(base_id), '--log-level', 'warning'],
        stdout=log_file, stderr=subprocess.STDOUT)
    try:
        checks['ready'] = wait_ready(admin_port)

        # Progress evidence before driving traffic: admin /stats shows counters.
        stats_status, _, stats_body = http_get(f'http://127.0.0.1:{admin_port}/stats', timeout=5)
        checks['admin_stats_status'] = stats_status
        checks['admin_stats_seen'] = ('listener_manager.listener_added' in stats_body
                                      or 'http.ingress_http.downstream_rq_total' in stats_body)

        status, headers, body = http_get(f'http://127.0.0.1:{listener_port}/route-a',
                                         headers={'x-test': 'abc'})
        checks['proxied_status'] = status
        checks['proxied_body'] = body
        checks['upstream_header'] = headers.get('x-upstream')
        try:
            checks['echo_x_test'] = json.loads(body).get('echo_x_test') if body else None
        except Exception:
            checks['echo_x_test'] = None

        # Confirm Envoy accounted for the served request.
        _, _, stats_after = http_get(f'http://127.0.0.1:{admin_port}/stats', timeout=5)
        checks['downstream_rq_seen'] = 'http.ingress_http.downstream_rq_total: 1' in stats_after

        server.shutdown()
        server.server_close()
        server = None
        time.sleep(0.5)
        err_status, _, _ = http_get(f'http://127.0.0.1:{listener_port}/route-a',
                                    headers={'x-test': 'abc'})
        checks['upstream_down_status'] = err_status
    finally:
        if envoy_proc.poll() is None:
            envoy_proc.terminate()
            try:
                envoy_proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                envoy_proc.kill()
        if server is not None:
            server.shutdown()
            server.server_close()
        if log_file is not None:
            log_file.close()
        checks['envoy_log_tail'] = log_path.read_text(errors='replace')[-500:]

    passed = (checks.get('version_exit') == 0
              and checks.get('ready') is True
              and checks.get('admin_stats_status') == 200
              and checks.get('admin_stats_seen') is True
              and checks.get('proxied_status') == 200
              and checks.get('upstream_header') == 'fixture'
              and checks.get('echo_x_test') == 'abc'
              and checks.get('downstream_rq_seen') is True
              and checks.get('upstream_down_status') == 503)
    checks['passed'] = passed
    Path(args.result).write_text(json.dumps(checks, indent=2) + '\n')
    print(json.dumps(checks, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
