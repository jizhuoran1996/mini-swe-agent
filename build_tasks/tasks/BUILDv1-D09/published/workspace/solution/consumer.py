#!/usr/bin/env python3
import argparse
import http.server
import json
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


class Upstream(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({'path': self.path, 'method': self.command}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def wait_port(host, port, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.status, r.read().decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--nginx', required=True)
    ap.add_argument('--prefix', required=True)
    ap.add_argument('--workdir', required=True)
    args = ap.parse_args()
    work = Path(args.workdir)
    if work.exists():
        shutil.rmtree(work)
    for d in ['conf', 'logs', 'temp/client_body', 'temp/proxy',
              'temp/fastcgi', 'temp/scgi', 'temp/uwsgi', 'html/static']:
        (work / d).mkdir(parents=True, exist_ok=True)
    (work / 'html/static/hello.txt').write_text('hello-static-123\n')
    upstream = http.server.ThreadingHTTPServer(('127.0.0.1', 18081), Upstream)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    if not wait_port('127.0.0.1', 18081):
        print(json.dumps({'ok': False, 'error': 'upstream did not start'}))
        return 1
    conf = work / 'conf/nginx.conf'

    def write_conf(extra=''):
        conf.write_text(f"""
worker_processes 1;
pid logs/nginx.pid;
events {{ worker_connections 128; }}
http {{
    default_type text/plain;
    access_log logs/access.log;
    client_body_temp_path temp/client_body;
    proxy_temp_path temp/proxy;
    fastcgi_temp_path temp/fastcgi;
    scgi_temp_path temp/scgi;
    uwsgi_temp_path temp/uwsgi;
    server {{
        listen 127.0.0.1:18080;
        server_name localhost;
        location /static/ {{ root html; }}
        location /api/ {{ proxy_pass http://127.0.0.1:18081/; }}
        {extra}
    }}
}}
""")

    write_conf()
    nginx_cmd = [args.nginx, '-p', str(work), '-c', 'conf/nginx.conf']
    proc = subprocess.Popen(nginx_cmd, cwd=str(work))
    report = {}
    try:
        if not wait_port('127.0.0.1', 18080):
            print(json.dumps({'ok': False, 'error': 'nginx did not start'}))
            return 1
        status, body = get('http://127.0.0.1:18080/static/hello.txt')
        report['static'] = {'status': status, 'body': body.strip()}
        assert status == 200 and 'hello-static-123' in body
        status, body = get('http://127.0.0.1:18080/api/test')
        report['proxy'] = {'status': status, 'body': body}
        assert status == 200 and '/test' in body
        try:
            get('http://127.0.0.1:18080/static/missing.txt')
            raise AssertionError('expected 404')
        except urllib.error.HTTPError as exc:
            report['missing'] = {'status': exc.code}
            assert exc.code == 404
        write_conf('location /new/ { return 200 "new-route"; }')
        subprocess.run([args.nginx, '-p', str(work), '-c', 'conf/nginx.conf', '-s', 'reload'],
                       check=True, timeout=10)
        ok = False
        for _ in range(50):
            try:
                status, body = get('http://127.0.0.1:18080/new/')
                if status == 200 and body.strip() == 'new-route':
                    ok = True
                    break
            except Exception:
                pass
            time.sleep(0.1)
        assert ok, 'reload did not apply'
        report['reload'] = {'status': 200, 'body': 'new-route'}
        status, body = get('http://127.0.0.1:18080/static/hello.txt')
        assert status == 200 and 'hello-static-123' in body
        report['after_reload_static'] = {'status': status}
        subprocess.run([args.nginx, '-p', str(work), '-c', 'conf/nginx.conf', '-s', 'quit'],
                       check=False, timeout=10)
        proc.wait(timeout=10)
        print(json.dumps({'ok': True, 'report': report}))
        return 0
    finally:
        upstream.shutdown()
        try:
            proc.terminate()
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(main())
