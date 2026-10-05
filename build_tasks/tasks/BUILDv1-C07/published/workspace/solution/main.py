#!/usr/bin/env python3
"""BUILDv1-C07 (core profile).

Build a Godot ``tests=yes`` Linux editor directly from the frozen source release,
run the official unit (doctest) and GDScript suites without touching the
upstream expected outputs, then verify a basic headless consumer project using
only the artifacts produced in this session.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, os.environ.get("PYTHONPATH", ""))
import buildkit  # noqa: F401  (trusted plumbing supplied on PYTHONPATH)
from buildkit import Session

REQUIRED_TOOLS = ("scons", "gcc", "g++", "pkg-config", "python3")
REQUIRED_PKGS = ("x11", "xcursor", "xinerama", "xrandr", "xi", "xkbcommon", "gl")

CONSUMER_PROJECT = (
    '[application]\n\n'
    'config/name="CoreConsumer"\n'
    'run/main_scene="res://main.tscn"\n'
    'config/features=PackedStringArray("4.4")\n'
)

CONSUMER_SCENE = (
    '[gd_scene load_steps=2 format=3]\n\n'
    '[ext_resource type="Script" path="res://main.gd" id="1_main"]\n\n'
    '[node name="Main" type="Node"]\n'
    'script = ExtResource("1_main")\n'
)

CONSUMER_SCRIPT = '''extends Node


func _ready() -> void:
\tvar total := 0
\tfor i in range(1, 11):
\t\ttotal += i
\tprint("CONSUMER_SUM=%d" % total)
\tif total != 55:
\t\tpush_error("CONSUMER_FAIL: unexpected sum")
\t\tget_tree().quit(1)
\t\treturn
\tprint("CONSUMER_NODE=%s" % name)
\tprint("CONSUMER_OK")
\tget_tree().quit(0)
'''


def missing_items(input_dir):
    """Return the exact list of missing source/tool/dependency items."""
    missing = []
    inp = Path(input_dir)
    manifest = inp / "manifest.json"
    if not manifest.is_file():
        return ["source/manifest.json"]
    try:
        data = json.loads(manifest.read_text())
    except Exception as exc:  # noqa: BLE001
        return [f"source/manifest.json ({exc})"]
    source = data.get("source", {})
    filename = source.get("filename", "source.tar.gz")
    if not (inp / filename).is_file():
        missing.append(f"source/{filename}")
    for tool in REQUIRED_TOOLS:
        if shutil.which(tool) is None:
            missing.append(f"tool:{tool}")
    if shutil.which("pkg-config"):
        for pkg in REQUIRED_PKGS:
            proc = subprocess.run(
                ["pkg-config", "--exists", pkg],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if proc.returncode != 0:
                missing.append(f"pkg-config:{pkg}")
    return missing


def find_editor_bin(src):
    bin_dir = src / "bin"
    candidates = sorted(p for p in bin_dir.glob("godot.linuxbsd.editor.*") if p.is_file())
    if not candidates:
        candidates = sorted(
            p for p in bin_dir.glob("*")
            if p.is_file() and os.access(p, os.X_OK)
        )
    if not candidates:
        raise RuntimeError("SCons build produced no editor binary under bin/")
    return max(candidates, key=lambda p: p.stat().st_size)


def doctest_counts(text):
    """Best-effort extraction of doctest summary counters from console output."""
    out = {}
    patterns = {
        "cases": r"test cases:\s*([0-9]+)",
        "assertions": r"assertions:\s*([0-9]+)",
        "passed": r"([0-9]+)\s+passed",
        "skipped": r"([0-9]+)\s+skipped",
        "failed": r"([0-9]+)\s+failed",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            out[key] = int(match.group(1))
    return out


def parse_doctest_xml(path):
    if not Path(path).is_file():
        return None
    try:
        root = ET.parse(path).getroot()
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    test_cases = list(root.iter("TestCase"))
    failures = 0
    for element in root.iter("OverallResultsAsserts"):
        failures += int(element.get("failures", "0"))
    return {
        "binary": root.get("binary"),
        "version": root.get("version"),
        "test_case_elements": len(test_cases),
        "assert_failures": failures,
    }


def cmd_doctor(args):
    missing = missing_items(args.input)
    if missing:
        for item in missing:
            print(f"MISSING {item}")
        return 78
    print("READY: frozen source archive and declared build dependencies are present")
    return 0


def cmd_run(args):
    missing = missing_items(args.input)
    if missing:
        for item in missing:
            print(f"MISSING {item}")
        return 78

    session = Session(args.input, args.output, args.jobs)
    src = session.prepare()

    # 1. Build the editor with the in-tree doctest harness enabled.
    session.run(
        [
            "scons",
            "platform=linuxbsd",
            "target=editor",
            "arch=x86_64",
            "tests=yes",
            f"-j{session.jobs}",
        ],
        cwd=src,
        phase="build",
        name="scons_editor_tests",
        timeout=7200,
    )

    built = find_editor_bin(src)

    # 2. Install the real artifact into the private install prefix.
    installed = session.install / "bin" / "godot"
    installed.parent.mkdir(parents=True, exist_ok=True)
    session.run(
        ["install", "-m", "0755", str(built), str(installed)],
        phase="install",
        name="install_editor",
    )
    for extra in ("LICENSE.txt", "COPYRIGHT.txt", "AUTHORS.md"):
        source_file = src / extra
        if source_file.is_file():
            session.run(
                ["install", "-m", "0644", str(source_file), str(session.install / extra)],
                phase="install",
                name=f"install_{extra}",
            )

    version_log = session.run(
        [str(installed), "--version"], phase="install", name="editor_version", timeout=300
    )
    version_text = version_log.read_text(errors="replace").strip()
    version = version_text.splitlines()[-1] if version_text else "unknown"
    (session.install / "version.json").write_text(
        json.dumps(
            {
                "version": version,
                "built_from_commit": session.manifest["source"].get("commit"),
                "release_ref": session.manifest["source"].get("release_ref"),
                "binary_sha256": buildkit.digest(installed),
                "provenance": "built in this session from the frozen source archive",
            },
            indent=2,
        )
        + "\n"
    )
    session.write(
        "scons_config.json",
        {
            "command": (
                "scons platform=linuxbsd target=editor arch=x86_64 "
                f"tests=yes -j{session.jobs}"
            ),
            "platform": "linuxbsd",
            "target": "editor",
            "arch": "x86_64",
            "tests": "yes",
            "source_commit": session.manifest["source"].get("commit"),
            "release_ref": session.manifest["source"].get("release_ref"),
        },
    )

    # 3. Official unit suite (documented [Stress] cases excluded).
    unit_log = session.test(
        "doctest_unit",
        [str(built), "--headless", "--test", "--test-case-exclude=*[Stress]*"],
        cwd=src,
        timeout=3600,
    )
    unit_counts = doctest_counts(unit_log.read_text(errors="replace"))
    if unit_counts.get("cases", 0) <= 0:
        raise RuntimeError("doctest reported no executed test cases")

    # 3b. Same suite producing the machine-readable XML artifact.
    session.run(
        [
            str(built),
            "--headless",
            "--test",
            "--test-case-exclude=*[Stress]*",
            "--reporters=xml",
            f"--out={session.output / 'doctest.xml'}",
        ],
        cwd=src,
        phase="official_test",
        name="doctest_xml",
        timeout=3600,
    )

    # 4. Official GDScript script suite.
    gd_log = session.test(
        "gdscript_suite",
        [str(built), "--headless", "--test", "--test-suite=*GDScript*"],
        cwd=src,
        timeout=3600,
    )
    gd_counts = doctest_counts(gd_log.read_text(errors="replace"))
    if gd_counts.get("cases", 0) <= 0:
        raise RuntimeError("GDScript suite reported no executed test cases")

    session.write(
        "test_summary.json",
        {
            "doctest_unit": unit_counts,
            "gdscript_suite": gd_counts,
            "doctest_xml": parse_doctest_xml(session.output / "doctest.xml"),
        },
    )

    # 5. Independent headless consumer, driven only by the installed binary.
    consumer = session.consumer
    (consumer / "project.godot").write_text(CONSUMER_PROJECT)
    (consumer / "main.tscn").write_text(CONSUMER_SCENE)
    (consumer / "main.gd").write_text(CONSUMER_SCRIPT)

    consumer_log = session.test(
        "consumer_headless",
        [str(installed), "--headless", "--path", str(consumer), "--quit-after", "300"],
        cwd=consumer,
        timeout=600,
    )
    consumer_text = consumer_log.read_text(errors="replace")
    for needle in ("CONSUMER_SUM=55", "CONSUMER_NODE=Main", "CONSUMER_OK"):
        if needle not in consumer_text:
            raise RuntimeError(
                f"headless consumer verification failed (missing {needle}):\n"
                + consumer_text[-4000:]
            )

    session.finish(
        features={
            "profile": "core",
            "editor_tests_enabled": True,
            "official_unit_tests": True,
            "official_gdscript_suite": True,
            "headless_consumer_verified": True,
            "template_release": False,
        }
    )
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Godot core source build, official tests and headless consumer verification",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="build, test and verify")
    run_parser.add_argument("--input", required=True, help="directory holding the frozen source mount")
    run_parser.add_argument("--output", required=True, help="writable output directory")
    run_parser.add_argument("--jobs", type=int, default=4, help="build parallelism (clamped to 4)")

    doctor_parser = sub.add_parser("doctor", help="report missing source/tool/dependency items")
    doctor_parser.add_argument("--input", required=True)

    args = parser.parse_args()
    if args.command == "doctor":
        return cmd_doctor(args)
    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
