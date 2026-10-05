#!/usr/bin/env python3
"""BUILDv1-D03 (core profile): build Redis 7.4.5 from the frozen source
archive without TLS, install it, run the official Tcl ``unit/type/string``
unit and consume the installed binaries from outside the source tree."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tarfile
from pathlib import Path

import buildkit

REQUIRED_SOURCE_PATHS = [
    "src/Makefile",
    "deps/Makefile",
    "runtest",
    "tests/test_helper.tcl",
    "tests/unit/type/string.tcl",
]

TOOL_CANDIDATES = {
    "make": ["make"],
    "tclsh": ["tclsh", "tclsh8.6", "tclsh8.5"],
    "cc": ["cc", "gcc", "clang"],
}

OFFICIAL_UNIT = "unit/type/string"
TEST_PORTCOUNT = 16

CORE_CONF_TEMPLATE = """# Fixed configuration for the source-built Redis core build.
# TLS is intentionally NOT compiled in this profile (no BUILD_TLS=yes).
bind 127.0.0.1
protected-mode yes
port 6379
daemonize no
databases 1
save ""
appendonly yes
appendfsync always
dir ./data
"""

CONSUMER_SOURCE = r'''#!/usr/bin/env python3
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
'''


def doctor(input_dir: Path) -> int:
    """Report the exact missing source/tool/dependency items.

    Returns 0 when the frozen core build can start, 78 when something required
    is absent (the builder is expected to prepare the item and retry).
    """
    missing = []
    present = {}
    manifest = None

    if not input_dir.is_dir():
        missing.append("input directory missing or unreadable: %s" % input_dir)

    manifest_path = input_dir / "manifest.json"
    if not manifest_path.is_file():
        missing.append("input manifest missing: %s" % manifest_path)
    else:
        try:
            manifest = json.loads(manifest_path.read_text())
        except Exception as exc:  # noqa: BLE001 - diagnostics only
            missing.append("input manifest unreadable: %s: %s" % (manifest_path, exc))

    archive = None
    if manifest:
        source = manifest.get("source") or {}
        archive = input_dir / str(source.get("filename", ""))
        if not archive.is_file():
            missing.append("source archive missing: %s" % archive)
        else:
            sha = buildkit.digest(archive)
            if sha != source.get("sha256"):
                missing.append("source archive sha256 mismatch: %s (got %s)" % (archive, sha))

    if archive is not None and archive.is_file():
        try:
            names = set()
            with tarfile.open(archive) as tar:
                for member in tar:
                    parts = Path(member.name).parts
                    if not parts:
                        continue
                    names.add("/".join(parts[1:]) if len(parts) > 1 else "")
            for rel in REQUIRED_SOURCE_PATHS:
                if rel not in names:
                    missing.append("source tree is missing required path: %s" % rel)
        except Exception as exc:  # noqa: BLE001 - diagnostics only
            missing.append("source archive unreadable: %s: %s" % (archive, exc))

    for tool, candidates in TOOL_CANDIDATES.items():
        found = None
        for candidate in candidates:
            found = shutil.which(candidate)
            if found:
                break
        if not found:
            missing.append("required tool not on PATH: %s (tried %s)"
                           % (tool, ", ".join(candidates)))
        else:
            present[tool] = found

    if "tclsh" in present:
        try:
            probe = subprocess.run([present["tclsh"]], input="puts [info patchlevel]\n",
                                   capture_output=True, text=True, timeout=30)
            version = probe.stdout.strip()
            if probe.returncode != 0 or not version:
                missing.append("tclsh is not runnable: %s" % present["tclsh"])
            else:
                present["tclsh_version"] = version
                major_minor = version.split(".")[:2]
                try:
                    if (int(major_minor[0]), int(major_minor[1])) < (8, 5):
                        missing.append("official test harness needs tclsh >= 8.5, found %s" % version)
                except ValueError:
                    pass
        except Exception as exc:  # noqa: BLE001 - diagnostics only
            missing.append("tclsh probe failed: %s: %s" % (present["tclsh"], exc))

    report = {"input": str(input_dir), "ready": not missing,
              "missing": missing, "present": present}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not missing else 78


def _port_window_free(base, portcount):
    """True when a contiguous run of candidate test ports is bindable.

    The Redis Tcl harness itself searches backwards from ``baseport - 32`` for
    the main server ports and then allocates ``portcount`` ports upward, so a
    full window below and above the requested base must be verified while no
    other listener (or other test session) occupies it.
    """
    low = base - 40
    high = base + portcount + 24
    if low < 1024 or high > 65000:
        return False
    holders = []
    try:
        for port in range(low, high + 1):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("0.0.0.0", port))
            except OSError:
                sock.close()
                return False
            holders.append(sock)
        return True
    finally:
        for sock in holders:
            sock.close()


def pick_baseport(portcount=TEST_PORTCOUNT):
    """Pick a base port from a low, non-ephemeral range.

    Ephemeral ports (Linux default 32768-60999) are avoided on purpose: the
    kernel hands them out for outbound sockets while the test suite runs, which
    is exactly what made a previously auto-selected high base port unusable.
    """
    for step in (8, 1):
        for base in range(15000, 32000, step):
            if _port_window_free(base, portcount):
                return base
    # Last resort: a large contiguous window is unavailable; ask for the widest
    # verified window we can still find rather than guessing blindly.
    for base in range(15000, 32000):
        if _port_window_free(base, 2):
            return base
    raise RuntimeError("no contiguous free TCP port window found for the official test suite")


def run(input_dir: Path, output_dir: Path, jobs: int) -> int:
    if doctor(input_dir) != 0:
        sys.stderr.write("refusing to build: required source/tool items are missing "
                         "(see doctor report above)\n")
        return 78

    session = buildkit.Session(input_dir, output_dir, jobs=jobs)
    build_jobs = min(max(1, int(jobs)), 4)
    test_jobs = min(max(1, int(jobs)), 2)
    src = session.prepare()

    # Core build: default Linux allocator (bundled jemalloc), no BUILD_TLS.
    session.run(["make", "-j", str(build_jobs)], cwd=src, phase="build",
                name="redis_core_build", timeout=7200)

    session.run(["make", "PREFIX=" + str(session.install), "install"], cwd=src,
                phase="install", name="redis_core_install", timeout=1800)

    bin_dir = session.install / "bin"
    required_bins = ["redis-server", "redis-cli"]
    other_bins = ["redis-benchmark", "redis-check-aof", "redis-check-rdb", "redis-sentinel"]
    missing_bins = [name for name in required_bins if not (bin_dir / name).is_file()]
    if missing_bins:
        raise RuntimeError("make install did not produce %s under %s" % (missing_bins, bin_dir))
    session.write("installed_binaries.json", {
        "bin_dir": str(bin_dir),
        "present": required_bins + [n for n in other_bins if (bin_dir / n).is_file()],
        "absent": [n for n in other_bins if not (bin_dir / n).is_file()],
    })

    version_log = session.run([str(bin_dir / "redis-server"), "--version"],
                              cwd=session.install, phase="verify",
                              name="redis_server_version", timeout=120)
    version_lines = [line for line in version_log.read_text(errors="replace").splitlines() if line.strip()]
    session.write("redis_version.json", {
        "redis_server_version": version_lines[-1] if version_lines else "",
    })

    etc = session.install / "etc"
    etc.mkdir(parents=True, exist_ok=True)
    (etc / "redis-core.conf").write_text(CORE_CONF_TEMPLATE)

    runtest = src / "runtest"
    runtest.chmod(runtest.stat().st_mode | 0o755)

    inventory_log = session.run(["./runtest", "--list-tests"], cwd=src, phase="discovery",
                                name="official_test_inventory", timeout=600)
    inventory_text = inventory_log.read_text(errors="replace")
    (session.output / "official_test_inventory.txt").write_text(inventory_text)
    inventory_lines = [line.strip() for line in inventory_text.splitlines() if line.strip()]
    if not any(line == OFFICIAL_UNIT or line.endswith(OFFICIAL_UNIT) for line in inventory_lines):
        raise RuntimeError("official test discovery does not list %s" % OFFICIAL_UNIT)

    baseport = pick_baseport(TEST_PORTCOUNT)
    session.write("official_test_baseport.json", {
        "baseport": baseport,
        "portcount": TEST_PORTCOUNT,
        "verified_window": [baseport - 40, baseport + TEST_PORTCOUNT + 24],
    })
    test_log = session.test(
        "official_unit_type_string",
        ["./runtest", "--single", OFFICIAL_UNIT, "--clients", str(test_jobs),
         "--baseport", str(baseport), "--portcount", str(TEST_PORTCOUNT)],
        cwd=src, parser="auto", timeout=5400)
    test_text = test_log.read_text(errors="replace")
    ok_count = len(re.findall(r"^\[ok\]", test_text, re.M))
    err_count = len(re.findall(r"^\[(?:err|exception)\]", test_text, re.M))
    all_passed = "All tests passed without errors" in test_text
    session.write("official_test_report.json", {
        "selector": OFFICIAL_UNIT,
        "unit": OFFICIAL_UNIT,
        "baseport": baseport,
        "portcount": TEST_PORTCOUNT,
        "clients": test_jobs,
        "upstream_ok_assertions": ok_count,
        "upstream_error_lines": err_count,
        "upstream_all_passed_marker": all_passed,
        "raw_log": str(test_log.relative_to(session.output)),
    })
    if err_count:
        raise RuntimeError("official test log contains %d error/exception lines" % err_count)
    if not all_passed:
        raise RuntimeError("official test log lacks the upstream all-passed marker")
    if ok_count < 1:
        raise RuntimeError("official test log contains no [ok] assertions; nothing ran")

    consumer_work = session.consumer / "core_local"
    consumer_work.mkdir(parents=True, exist_ok=True)
    consumer_script = session.consumer / "verify_core.py"
    consumer_script.write_text(CONSUMER_SOURCE)
    consumer_log = session.run(
        [sys.executable, str(consumer_script), "--bindir", str(bin_dir),
         "--workdir", str(consumer_work), "--port", "0"],
        cwd=session.consumer, phase="consumer", name="plain_local_client_aof_restart", timeout=900)
    if "CONSUMER_OK" not in consumer_log.read_text(errors="replace"):
        raise RuntimeError("consumer did not report CONSUMER_OK")

    session.finish({
        "profile": "core",
        "tls": False,
        "build_command": "make -j%d (BUILD_TLS not set)" % build_jobs,
        "allocator": "bundled jemalloc (Linux default)",
        "official_unit": OFFICIAL_UNIT,
        "upstream_ok_assertions": ok_count,
        "consumer": "installed redis-server on 127.0.0.1 + installed redis-cli + RESP client + AOF restart digest",
    })
    print("BUILDv1-D03 core profile finished in %s" % session.output)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="buildv1-d03",
        description="Source-build Redis 7.4.5 (core, no TLS), install it, run the "
                    "official unit/type/string Tcl unit and consume the installed binaries.")
    sub = parser.add_subparsers(dest="command")

    doctor_parser = sub.add_parser("doctor", help="list missing source/tool/dependency items")
    doctor_parser.add_argument("--input", required=True, help="directory holding manifest.json and the source archive")

    run_parser = sub.add_parser("run", help="build, install, test and consume")
    run_parser.add_argument("--input", required=True)
    run_parser.add_argument("--output", required=True)
    run_parser.add_argument("--jobs", type=int, default=4)

    args = parser.parse_args(argv)
    if args.command == "doctor":
        return doctor(Path(args.input).resolve())
    if args.command == "run":
        return run(Path(args.input).resolve(), Path(args.output).resolve(), args.jobs)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
