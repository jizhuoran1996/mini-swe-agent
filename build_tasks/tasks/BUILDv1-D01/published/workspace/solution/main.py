#!/usr/bin/env python3
"""Build PostgreSQL 17.5 core (server + clients + libpq) from the pinned source
release, run the official core regression suite, install it into a private
prefix, and prove an out-of-tree libpq consumer can drive real transactions.
"""

import argparse
import json
import os
import pwd
import re
import shutil
import sys
from pathlib import Path

import buildkit


HERE = Path(__file__).resolve().parent
C_CONSUMER_SOURCE = HERE / "consumer_libpq.c"

REQUIRED_TOOLS = ["make", "gcc", "perl", "tar", "bzip2"]
OPTIONAL_TOOLS = ["bison", "flex", "cc", "ld"]
OPTIONAL_HEADERS = ["zlib.h", "readline/readline.h", "openssl/ssl.h"]
BC = "C"


def _which(name):
    return shutil.which(name)


def _user():
    return pwd.getpwuid(os.getuid()).pw_name


def _header_present(header):
    for root in ("/usr/include", "/usr/local/include", "/usr/include/x86_64-linux-gnu"):
        if Path(root, header).exists():
            return True
    return False


def doctor(input_dir):
    """List exact missing source/tool/dependency items. 0 = ready, 78 = missing."""
    inp = Path(input_dir)
    missing = []
    manifest = inp / "manifest.json"
    if not manifest.is_file():
        missing.append({"kind": "source", "item": "manifest.json"})
    else:
        try:
            info = json.loads(manifest.read_text())
            src = info["source"]
            archive = inp / src["filename"]
            if not archive.is_file():
                missing.append({"kind": "source", "item": src["filename"]})
            else:
                got = buildkit.digest(archive)
                if got != src["sha256"]:
                    missing.append({"kind": "source", "item": "sha256 mismatch for " + src["filename"] + ": " + got})
        except Exception as exc:  # noqa: BLE001
            missing.append({"kind": "source", "item": "manifest unreadable: " + str(exc)})
    for tool in REQUIRED_TOOLS:
        if not _which(tool):
            missing.append({"kind": "tool", "item": tool})
    if not (_which("cc") or _which("gcc") or _which("clang")):
        missing.append({"kind": "tool", "item": "C compiler cc/gcc/clang"})
    if not C_CONSUMER_SOURCE.is_file():
        missing.append({"kind": "asset", "item": str(C_CONSUMER_SOURCE)})
    report = {
        "ready": not missing,
        "missing": missing,
        "required_tools": REQUIRED_TOOLS,
        "optional_tools": {t: bool(_which(t)) for t in OPTIONAL_TOOLS},
        "optional_headers": {h: _header_present(h) for h in OPTIONAL_HEADERS},
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not missing else 78


def _record_regression_counts(sess):
    """Preserve the upstream pg_regress summary verbatim; the helper parser returns null here."""
    record = sess.tests[-1]
    text = (sess.output / record["raw_log"]).read_text(errors="replace")
    passed = re.search(r"All ([0-9]+) tests passed", text)
    failed = re.search(r"([0-9]+) of ([0-9]+) tests failed", text)
    summary = {
        "selector": record["selector"],
        "nonempty_log": record["nonempty_log"],
        "log_sha256": record["log_sha256"],
        "pg_regress_passed": int(passed.group(1)) if passed else None,
        "pg_regress_failed_match": failed.group(0) if failed else None,
    }
    sess.write("coverage.json", summary)
    if not passed and not failed:
        raise RuntimeError("pg_regress summary line not found; refusing to claim coverage")
    if failed:
        raise RuntimeError("core regression reported failures: " + failed.group(0))
    return summary


def _run_consumer(sess):
    install = sess.install
    consumer = sess.consumer
    env = {"LC_ALL": BC, "LANG": BC}
    user = _user()
    port = "55432"
    data = consumer / "pgdata"
    socket_dir = consumer / "socket"
    server_log = consumer / "server.log"
    if data.exists():
        shutil.rmtree(data)
    socket_dir.mkdir(parents=True, exist_ok=True)

    initdb = str(install / "bin" / "initdb")
    pg_ctl = str(install / "bin" / "pg_ctl")
    psql = str(install / "bin" / "psql")
    postgres_opts = "-p " + port + " -k " + str(socket_dir)

    log = sess.run([str(install / "bin" / "postgres"), "--version"], cwd=consumer,
                   phase="consumer", name="postgres_version", env=env, timeout=60)
    if "17.5" not in log.read_text():
        raise RuntimeError("installed server is not the 17.5 build")

    sess.run([initdb, "-D", str(data), "-U", user, "-A", "trust", "--no-locale",
              "--encoding=UTF8"], cwd=consumer, phase="consumer", name="initdb",
             env=env, timeout=600)
    sess.run([pg_ctl, "-D", str(data), "-l", str(server_log), "-o", postgres_opts,
              "-w", "-t", "90", "start"], cwd=consumer, phase="consumer",
             name="server_start_1", env=env, timeout=300)

    stopped = False
    try:
        cc = _which("cc") or _which("gcc")
        csrc = consumer / "consumer_libpq.c"
        shutil.copyfile(C_CONSUMER_SOURCE, csrc)
        binary = consumer / "consumer_libpq"
        sess.run([cc, "-O2", "-Wall", "-o", str(binary), str(csrc),
                  "-I" + str(install / "include"), "-L" + str(install / "lib"),
                  "-lpq", "-Wl,-rpath," + str(install / "lib")],
                 cwd=consumer, phase="consumer", name="consumer_compile", env=env, timeout=300)

        ldd_log = sess.run(["ldd", str(binary)], cwd=consumer, phase="consumer",
                           name="consumer_ldd", env=env, timeout=120)
        ldd_text = ldd_log.read_text()
        install_lib = str(install / "lib")
        if "libpq" not in ldd_text or install_lib not in ldd_text:
            raise RuntimeError("consumer does not resolve libpq from the new install: " + ldd_text)

        conninfo = "host=" + str(socket_dir) + " port=" + port + " dbname=postgres user=" + user
        run_log = sess.run([str(binary), conninfo], cwd=consumer, phase="consumer",
                           name="consumer_run", env=env, timeout=600)
        run_text = run_log.read_text()
        if "CONSUMER_OK" not in run_text:
            raise RuntimeError("libpq consumer failed: " + run_text)

        sess.run([pg_ctl, "-D", str(data), "-m", "fast", "-w", "-t", "90", "stop"],
                 cwd=consumer, phase="consumer", name="server_stop_1", env=env, timeout=300)
        stopped = True
        sess.run([pg_ctl, "-D", str(data), "-l", str(server_log), "-o", postgres_opts,
                  "-w", "-t", "90", "start"], cwd=consumer, phase="consumer",
                 name="server_start_2", env=env, timeout=300)
        stopped = False

        q = "SELECT count(*) || '|' || count(*) FILTER (WHERE note='rolledback') || '|' || count(*) FILTER (WHERE note='committed') FROM tx_demo"
        psql_log = sess.run([psql, "-h", str(socket_dir), "-p", port, "-U", user,
                             "-d", "postgres", "-Atc", q], cwd=consumer, phase="consumer",
                            name="psql_verify", env=env, timeout=180)
        answer = psql_log.read_text().strip().splitlines()
        answer = answer[-1].strip() if answer else ""
        if answer != "1001|0|1000":
            raise RuntimeError("post-restart verification failed, got: " + answer)
        sess.write("consumer_evidence.json", {
            "ldd_resolves_install_lib": True,
            "consumer_output_ok": True,
            "post_restart_rowcount": answer,
            "link_library": str(install / "lib" / "libpq.so.5"),
        })
    finally:
        if not stopped:
            sess.run([pg_ctl, "-D", str(data), "-m", "immediate", "-w", "stop"],
                     cwd=consumer, phase="consumer", name="server_stop_final",
                     env=env, timeout=180, check=False)


def run(args):
    sess = buildkit.Session(args.input, args.output, args.jobs)
    sess.prepare()
    build = sess.build
    install = sess.install
    jobs = sess.jobs
    env = {"LC_ALL": BC, "LANG": BC}

    configure = [str(sess.src / "configure"), "--prefix=" + str(install)]
    sess.run(configure, cwd=build, phase="configure", name="configure", env=env, timeout=1800)
    sess.run(["make", "-j" + str(jobs), "all"], cwd=build, phase="build",
             name="make_all", env=env, timeout=7200)
    sess.run(["make", "install"], cwd=build, phase="install", name="make_install",
             env=env, timeout=1800)

    sess.test("core_regression", ["make", "check", "MAX_CONNECTIONS=2"], cwd=build,
              env=env, timeout=5400)
    counts = _record_regression_counts(sess)

    _run_consumer(sess)

    features = {
        "project": "PostgreSQL",
        "release": "17.5",
        "components": ["server", "psql", "libpq", "include-headers"],
        "core_regression_passed": counts["pg_regress_passed"],
        "consumer": "out-of-tree C program linked against installed libpq",
        "install_prefix": str(install),
    }
    sess.finish(features=features)
    print(json.dumps({"ok": True, "tests": counts, "install": str(install)}))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="postgresql-core-build",
        description="Build PostgreSQL 17.5 from source, run core regression, verify a libpq consumer.")
    parser.add_argument("command", choices=["run", "doctor"])
    parser.add_argument("--input", default="input")
    parser.add_argument("--output", default="output")
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return doctor(args.input)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
