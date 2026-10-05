#!/usr/bin/env python3
"""BUILDv1-B07 core profile.

Source-build PHP 8.4.8 from the frozen php-src archive, install a CLI
interpreter, run the official PHPT suites for tests/lang and ext/json/tests,
and then consume the freshly installed runtime from outside the source tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import buildkit

REQUIRED_TOOLS = ["gcc", "make", "autoconf", "bison", "re2c", "pkg-config", "m4", "sed", "grep"]
REQUIRED_PKGS = [
    ("libxml-2.0", "libxml2 development files (hard requirement in PHP 8.4)"),
    ("sqlite3", "sqlite3 development files"),
]

CONSUMER_PHP = r'''<?php
error_reporting(E_ALL);
$fail = 0;
function check($cond, $msg) {
    global $fail;
    if ($cond) { echo "ok: $msg\n"; }
    else { fwrite(STDERR, "FAIL: $msg\n"); $fail++; }
}
check(PHP_SAPI === 'cli', 'SAPI is cli');
check(PHP_BINARY !== '', 'PHP_BINARY is set');
check(extension_loaded('json'), 'json extension loaded');
check(extension_loaded('sqlite3'), 'sqlite3 extension loaded');
check(extension_loaded('pdo_sqlite'), 'pdo_sqlite extension loaded');
check(extension_loaded('libxml'), 'libxml extension loaded');
$in = ['b' => 2, 'a' => [1, 2, 3], 'unicode' => 'h\xc3\xa9llo', 'n' => null, 'f' => 1.5];
check(json_decode(json_encode($in), true) === $in, 'json round trip preserves structure');
check(array_sum(array_map(fn($x) => $x * 2, $in['a'])) === 12, 'closure + array_sum');
check((match (2) { 1 => 'one', 2 => 'two', default => 'other' }) === 'two', 'match expression');
$sum = 0;
foreach ([1, 2, 3, 4] as $v) { $sum += $v; }
check($sum === 10, 'foreach accumulation');
if ($fail) { fwrite(STDERR, "$fail consumer checks failed\n"); exit(1); }
echo "consumer selftest OK\n";
'''

PRODUCER_PHP = r'''<?php
error_reporting(E_ALL);
if ($argc < 2) { fwrite(STDERR, "usage: produce.php <db>\n"); exit(2); }
$dbPath = $argv[1];
if (file_exists($dbPath)) { unlink($dbPath); }
$records = [
    ['id' => 1, 'name' => 'alpha', 'score' => 10, 'tags' => ['x', 'y']],
    ['id' => 2, 'name' => 'beta',  'score' => 20, 'tags' => ['z']],
    ['id' => 3, 'name' => 'gamma', 'score' => 30, 'tags' => []],
];
$pdo = new PDO('sqlite:' . $dbPath);
$pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
$pdo->exec('CREATE TABLE records (id INTEGER PRIMARY KEY, name TEXT NOT NULL, payload TEXT NOT NULL)');
$stmt = $pdo->prepare('INSERT INTO records (id, name, payload) VALUES (:id, :name, :payload)');
foreach ($records as $r) {
    $stmt->execute([
        ':id' => $r['id'],
        ':name' => $r['name'],
        ':payload' => json_encode(['score' => $r['score'], 'tags' => $r['tags']], JSON_THROW_ON_ERROR),
    ]);
}
echo 'produced ' . count($records) . " records into $dbPath\n";
'''

VERIFIER_PHP = r'''<?php
error_reporting(E_ALL);
if ($argc < 2) { fwrite(STDERR, "usage: verify.php <db>\n"); exit(2); }
$dbPath = $argv[1];
if (!file_exists($dbPath)) { fwrite(STDERR, "db missing: $dbPath\n"); exit(1); }
$fail = 0;
function expect($cond, $msg) {
    global $fail;
    if ($cond) { echo "ok: $msg\n"; }
    else { fwrite(STDERR, "FAIL: $msg\n"); $fail++; }
}
$pdo = new PDO('sqlite:' . $dbPath);
$pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
$rows = $pdo->query('SELECT id, name, payload FROM records ORDER BY id')->fetchAll(PDO::FETCH_ASSOC);
expect(count($rows) === 3, 'three records persisted');
expect($rows[0]['name'] === 'alpha' && $rows[2]['name'] === 'gamma', 'names in insertion order');
$decoded = array_map(fn($row) => json_decode($row['payload'], true, 512, JSON_THROW_ON_ERROR), $rows);
expect(array_sum(array_column($decoded, 'score')) === 60, 'aggregate score matches input');
expect($decoded[0]['tags'] === ['x', 'y'] && $decoded[2]['tags'] === [], 'json tags round-tripped');
if ($fail) { fwrite(STDERR, "$fail verification checks failed\n"); exit(1); }
echo "verification OK\n";
'''


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def missing_items(input_dir):
    missing = []
    manifest_path = Path(input_dir) / "manifest.json"
    if not manifest_path.is_file():
        return ["source manifest: manifest.json is absent"], None
    manifest = json.loads(manifest_path.read_text())
    source = manifest.get("source", {})
    archive = Path(input_dir) / source.get("filename", "")
    if not archive.is_file():
        missing.append(f"source archive: {archive} is absent")
    elif sha256_file(archive) != source.get("sha256"):
        missing.append(f"source archive {archive} fails sha256 verification")
    for tool in REQUIRED_TOOLS:
        if shutil.which(tool) is None:
            missing.append(f"build tool: {tool} is not on PATH")
    probe = shutil.which("pkg-config")
    for package, description in REQUIRED_PKGS:
        found = False
        if probe is not None:
            found = subprocess.run(
                [probe, "--exists", package],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode == 0
        if not found and package == "libxml-2.0" and shutil.which("xml2-config"):
            found = True
        if not found:
            missing.append(f"library dependency: {description} (pkg-config '{package}')")
    return missing, manifest


def phpt_summary(log_path):
    text = Path(log_path).read_text(errors="replace")

    def grab(pattern):
        match = re.search(pattern, text)
        return int(match.group(1)) if match else None

    return {
        "number_of_tests": grab(r"Number of tests\s*:\s*(\d+)"),
        "tests_passed": grab(r"Tests passed\s*:\s*(\d+)"),
        "tests_failed": grab(r"Tests failed\s*:\s*(\d+)"),
        "tests_skipped": grab(r"Tests skipped\s*:\s*(\d+)"),
        "tests_warned": grab(r"Tests warned\s*:\s*(\d+)"),
        "expected_fail": grab(r"Expected fail\s*:\s*(\d+)"),
        "borked_lines": len(re.findall(r"(?m)^BORKED\b", text)),
    }


def write_consumers(target: Path):
    target.mkdir(parents=True, exist_ok=True)
    for name, body in (
        ("consumer.php", CONSUMER_PHP),
        ("produce.php", PRODUCER_PHP),
        ("verify.php", VERIFIER_PHP),
    ):
        (target / name).write_text(body)
    (target / "php.ini").write_text(
        "; private configuration for out-of-tree consumer validation\n"
        "error_reporting = E_ALL\n"
        "display_errors = 1\n"
        "log_errors = 0\n"
    )
    return target


def cmd_run(args):
    missing, manifest = missing_items(args.input)
    if missing:
        for item in missing:
            print("MISSING: " + item, file=sys.stderr)
        return 78

    session = buildkit.Session(args.input, args.output, args.jobs)
    src = session.prepare()
    session.write("source.json", {
        "task_id": manifest["task_id"],
        "profile": manifest.get("profile"),
        "release_ref": manifest["source"].get("release_ref"),
        "commit": manifest["source"].get("commit"),
        "declared_sha256": manifest["source"].get("sha256"),
        "verified_sha256": sha256_file(Path(args.input) / manifest["source"]["filename"]),
    })

    inventory = {}
    for label, directory in (("tests/lang", src / "tests" / "lang"),
                             ("ext/json/tests", src / "ext" / "json" / "tests")):
        files = sorted(p.name for p in directory.glob("*.phpt"))
        inventory[label] = {"phpt_files": len(files), "names": files}
    session.write("tests_inventory.json", inventory)

    session.run(["./buildconf", "--force"], cwd=src, phase="configure",
                name="buildconf", timeout=1200)
    session.run(["./configure", f"--prefix={session.install}",
                 "--with-pdo-sqlite", "--with-sqlite3", "--without-pear"],
                cwd=src, phase="configure", name="configure", timeout=3600)
    session.run(["make", f"-j{session.jobs}"], cwd=src, phase="build",
                name="make", timeout=10800)

    test_env = {"NO_INTERACTION": "1", "REPORT_EXIT_STATUS": "0"}
    test_jobs = min(session.jobs, 2)
    coverage = {}
    for label, tests in (("phpt_tests_lang", "tests/lang"),
                         ("phpt_ext_json", "ext/json/tests")):
        log = session.test(
            label,
            ["make", "test", f"TESTS={tests}", f"TEST_PHP_ARGS=-j{test_jobs}"],
            cwd=src, parser="auto", env=test_env, timeout=5400,
        )
        coverage[tests] = phpt_summary(log)
    session.write("phpt_coverage.json", coverage)

    session.run(["make", "install"], cwd=src, phase="install",
                name="make_install", timeout=3600)

    php = session.install / "bin" / "php"
    if not php.is_file():
        raise RuntimeError(f"installed interpreter is missing: {php}")
    consumer = write_consumers(session.consumer)
    ini = consumer / "php.ini"

    session.run([str(php), "-n", "-v"], cwd=consumer, phase="consumer",
                name="php_version", timeout=300)
    session.run([str(php), "-n", "-r", "echo PHP_BINARY, PHP_EOL, PHP_SAPI, PHP_EOL;"],
                cwd=consumer, phase="consumer", name="php_identity", timeout=300)
    session.run([str(php), "-c", str(ini), "-m"], cwd=consumer, phase="consumer",
                name="php_modules", timeout=300)
    session.run([str(php), "-n", "--ri", "json"], cwd=consumer, phase="consumer",
                name="php_ri_json", timeout=300)
    session.run([str(php), "-n", "--ri", "pdo_sqlite"], cwd=consumer, phase="consumer",
                name="php_ri_pdo_sqlite", timeout=300)
    session.run(
        [str(php), "-n", "-r",
         "foreach(['json','sqlite3','pdo_sqlite','libxml'] as $e){if(!extension_loaded($e))"
         "{fwrite(STDERR,'missing '.$e);exit(1);}} echo 'modules ok';"] ,
        cwd=consumer, phase="consumer", name="php_modules_check", timeout=300)
    session.run([str(php), "-n", str(consumer / "consumer.php")], cwd=consumer,
                phase="consumer", name="consumer_selftest", timeout=300)

    database = consumer / "records.sqlite"
    session.run([str(php), "-n", str(consumer / "produce.php"), str(database)],
                cwd=consumer, phase="consumer", name="consumer_produce", timeout=300)
    session.run([str(php), "-n", str(consumer / "verify.php"), str(database)],
                cwd=consumer, phase="consumer", name="consumer_verify", timeout=300)

    features = {
        "profile": "core",
        "interpreter": str(php),
        "sapi": ["cli"],
        "required_extensions": ["json", "sqlite3", "pdo_sqlite", "libxml"],
        "official_test_directories": list(inventory),
        "phpt_coverage": coverage,
        "build_parallelism": session.jobs,
        "test_parallelism": test_jobs,
        "consumer_scope": "installed prefix only, -n / private ini, source tree not on PATH",
    }
    session.finish(features=features)
    shutil.copyfile(session.output / "install.tar.gz", session.output / "php-install.tar.gz")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="php-core-build",
        description="Source-build PHP 8.4 (core profile) and validate CLI + JSON content",
    )
    sub = parser.add_subparsers(dest="command")
    run_parser = sub.add_parser("run", help="build, test, install and consume PHP")
    run_parser.add_argument("--input", required=True)
    run_parser.add_argument("--output", required=True)
    run_parser.add_argument("--jobs", type=int, default=4)
    doctor_parser = sub.add_parser("doctor", help="report missing source, tools and dependencies")
    doctor_parser.add_argument("--input", required=True)
    args = parser.parse_args(argv)

    if args.command == "run":
        return cmd_run(args)
    if args.command == "doctor":
        missing, _ = missing_items(args.input)
        if missing:
            for item in missing:
                print("MISSING: " + item)
            return 78
        print("READY: source archive, build tools and library dependencies are present")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
