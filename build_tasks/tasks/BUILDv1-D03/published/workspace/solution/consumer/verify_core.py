#!/usr/bin/env python3
# Plain local (no TLS) consumer for the freshly installed Redis core build.
#
# Starts the installed redis-server on 127.0.0.1 with AOF enabled, drives it
# with the installed redis-cli and with a hand written RESP client, checks
# strings/hashes/transactions plus two expected error paths, snapshots a data
# digest, then restarts the server and verifies the digest survived via AOF.
import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time


class RespError(Exception):
    pass


class ProtocolError(Exception):
    pass


class Client:
    def __init__(self, host, port, timeout=15.0):
        self.sock = socket.create_connection((host, port), timeout)
        self.sock.settimeout(timeout)
        self.buf = bytearray()

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass

    def _fill(self, want):
        while len(self.buf) < want:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise EOFError("redis closed the connection")
            self.buf.extend(chunk)

    def _line(self):
        while True:
            idx = self.buf.find(b"\r\n")
            if idx >= 0:
                line = bytes(self.buf[:idx])
                del self.buf[:idx + 2]
                return line
            self._fill(len(self.buf) + 1)

    def cmd(self, *args):
        payload = [b"*%d\r\n" % len(args)]
        for arg in args:
            data = arg if isinstance(arg, bytes) else str(arg).encode()
            payload.append(b"$%d\r\n" % len(data))
            payload.append(data)
            payload.append(b"\r\n")
        self.sock.sendall(b"".join(payload))
        return self._reply()

    def _reply(self):
        line = self._line()
        tag, body = line[:1], line[1:]
        if tag == b"+":
            return body.decode()
        if tag == b"-":
            raise RespError(body.decode())
        if tag == b":":
            return int(body)
        if tag == b"$":
            length = int(body)
            if length == -1:
                return None
            self._fill(length + 2)
            data = bytes(self.buf[:length])
            del self.buf[:length + 2]
            return data.decode(errors="replace")
        if tag == b"*":
            length = int(body)
            if length == -1:
                return None
            return [self._reply() for _ in range(length)]
        raise ProtocolError("unexpected RESP tag %r" % tag)


def free_port():
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


def write_conf(path, port, datadir, logfile):
    text = (
        "port %d\n" % port
        + "bind 127.0.0.1\n"
        + "protected-mode yes\n"
        + "daemonize no\n"
        + "databases 1\n"
        + 'save ""\n'
        + "appendonly yes\n"
        + "appendfsync always\n"
        + "dir %s\n" % datadir
        + "logfile %s\n" % logfile
    )
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return text


def wait_ready(port, timeout=30.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            probe = Client("127.0.0.1", port, timeout=2.0)
            try:
                if probe.cmd("PING") == "PONG":
                    return True
            finally:
                probe.close()
        except (OSError, EOFError, RespError, ProtocolError) as exc:
            last = exc
        time.sleep(0.1)
    raise RuntimeError("redis-server on port %d never became ready (%s)" % (port, last))


def run_cli(cli, port, *args, check=True):
    proc = subprocess.run([cli, "-p", str(port)] + list(args),
                          capture_output=True, text=True, timeout=60)
    if check and proc.returncode != 0:
        raise AssertionError("redis-cli %s failed rc=%d stdout=%r stderr=%r"
                             % (list(args), proc.returncode, proc.stdout, proc.stderr))
    return proc


def snapshot(client):
    data = {}
    for key in sorted(client.cmd("KEYS", "*")):
        kind = client.cmd("TYPE", key)
        if kind == "string":
            value = client.cmd("GET", key)
        elif kind == "hash":
            flat = client.cmd("HGETALL", key)
            value = sorted((flat[i], flat[i + 1]) for i in range(0, len(flat), 2))
        elif kind == "list":
            value = client.cmd("LRANGE", key, "0", "-1")
        elif kind == "set":
            value = sorted(client.cmd("SMEMBERS", key))
        else:
            value = None
        data[key] = [kind, value]
    return data


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="plain local consumer for the installed Redis core build")
    parser.add_argument("--bindir", required=True)
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--port", type=int, default=0, help="0 picks a free loopback port")
    args = parser.parse_args(argv)

    server = os.path.join(args.bindir, "redis-server")
    cli = os.path.join(args.bindir, "redis-cli")
    for exe in (server, cli):
        if not (os.path.isfile(exe) and os.access(exe, os.X_OK)):
            print("CONSUMER_FAIL not an executable: %s" % exe)
            return 1

    port = args.port or free_port()
    work = os.path.abspath(args.workdir)
    datadir = os.path.join(work, "data")
    for path in (work, datadir):
        os.makedirs(path, exist_ok=True)
    conf = os.path.join(work, "redis.conf")
    logfile = os.path.join(work, "redis-server.log")
    write_conf(conf, port, datadir, logfile)

    summary = {"port": port, "server": os.path.realpath(server), "checks": []}
    handles = []
    proc = None

    def start():
        handle = open(logfile, "ab")
        handles.append(handle)
        return subprocess.Popen([server, conf], cwd=work,
                                stdout=handle, stderr=subprocess.STDOUT)

    try:
        proc = start()
        wait_ready(port)
        summary["checks"].append("server_started")

        cli_out = run_cli(cli, port, "SET", "cli:key", "cli-value")
        assert cli_out.stdout.strip() == "OK", cli_out.stdout
        cli_out = run_cli(cli, port, "GET", "cli:key")
        assert cli_out.stdout.strip() == "cli-value", cli_out.stdout
        summary["checks"].append("installed_redis_cli_set_get")

        client = Client("127.0.0.1", port)
        try:
            assert client.cmd("PING") == "PONG"
            client.cmd("SET", "core:string", "hello")
            assert client.cmd("APPEND", "core:string", "-world") == 11
            assert client.cmd("GET", "core:string") == "hello-world"
            assert client.cmd("STRLEN", "core:string") == 11
            client.cmd("SET", "core:counter", "10")
            assert client.cmd("INCR", "core:counter") == 11
            assert client.cmd("HSET", "core:hash", "field-a", "va", "field-b", "vb") == 2
            assert client.cmd("HGET", "core:hash", "field-b") == "vb"

            assert client.cmd("MULTI") == "OK"
            assert client.cmd("SET", "core:tx", "tx-value") == "QUEUED"
            assert client.cmd("INCR", "core:counter") == "QUEUED"
            assert client.cmd("EXEC") == ["OK", 12]
            summary["checks"].append("strings_hashes_multi_exec")

            try:
                client.cmd("INCR", "core:string")
                raise AssertionError("INCR over a non-integer string must fail")
            except RespError as exc:
                assert "not an integer" in str(exc).lower(), str(exc)
                summary["expected_error_integer"] = str(exc)
            try:
                client.cmd("GET", "core:hash")
                raise AssertionError("GET over a hash must fail")
            except RespError as exc:
                assert "WRONGTYPE" in str(exc), str(exc)
                summary["expected_error_wrongtype"] = str(exc)
            summary["checks"].append("expected_errors")

            before = snapshot(client)
            before_digest = digest(before)
            assert sorted(before) == ["cli:key", "core:counter", "core:hash",
                                      "core:string", "core:tx"], sorted(before)
        finally:
            client.close()

        aof_dir = os.path.join(datadir, "appendonlydir")
        summary["aof_files"] = sorted(os.listdir(aof_dir)) if os.path.isdir(aof_dir) else []
        assert summary["aof_files"], "AOF directory %s was not created" % aof_dir
        summary["checks"].append("aof_files_present")

        run_cli(cli, port, "SHUTDOWN", check=False)
        proc.wait(timeout=60)
        proc = None

        proc = start()
        wait_ready(port)
        client = Client("127.0.0.1", port)
        try:
            after = snapshot(client)
            after_digest = digest(after)
            assert after_digest == before_digest, (before, after)
            assert client.cmd("SET", "core:continued", "yes") == "OK"
            assert client.cmd("GET", "core:continued") == "yes"
            summary["keys_after_restart"] = sorted(after)
        finally:
            client.close()
        summary["checks"].append("aof_restart_digest_match")
        summary["digest"] = before_digest

        print("CONSUMER_SUMMARY " + json.dumps(summary, sort_keys=True))
        print("CONSUMER_OK digest=%s keys=%d port=%d"
              % (before_digest, len(summary["keys_after_restart"]), port))
        return 0
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
        for handle in handles:
            handle.close()


if __name__ == "__main__":
    sys.exit(main())
