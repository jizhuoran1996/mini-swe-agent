"""Audit recorded acceptance and distinguish cold builds from continuations."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read(path: Path) -> dict | list:
    return json.loads(path.read_text())


def audit() -> dict:
    records = []
    pending = []
    for task in sorted((ROOT / "tasks").iterdir()):
        state = read(task / "latest_run.json")
        if not state.get("independent_consumer_passed"):
            pending.append(task.name)
            continue
        run = Path(state["run_directory"])
        if not run.is_absolute():
            run = ROOT / run
        cold = Path(state.get("source_build_run", str(run)))
        if not cold.is_absolute():
            cold = ROOT / cold
        output = run / "workspace/output"
        if not (output / "run.json").exists():
            candidates = list(output.glob("*/run.json"))
            assert len(candidates) == 1
            output = candidates[0].parent
        locked = read(task / "source_lock.json")
        assert read(task / "input/manifest.json")["source"] == locked
        assert read(output / "run.json")["source"] == locked
        tests = read(output / "tests.json")
        assert tests and all(t["exit_code"] == 0 and t["nonempty_log"] for t in tests)
        assert all(t.get("parsed_count") is None or t["parsed_count"] > 0 for t in tests)
        evaluation = state["evaluation"]
        assert evaluation["passed"] and evaluation["fresh_container"]
        assert not evaluation["extracted_source_present"]
        assert evaluation["source_locked"] and evaluation["source_sha256"] == locked["sha256"]
        wheel_artifacts = []
        if evaluation["installed_files_checked"] == 0:
            assert task.name in {"BUILDv1-F03", "BUILDv1-F06"}
            for wheel in sorted(output.rglob("*.whl")):
                digest = hashlib.sha256()
                with wheel.open("rb") as stream:
                    for block in iter(lambda: stream.read(8 << 20), b""):
                        digest.update(block)
                wheel_artifacts.append({"path": str(wheel.relative_to(output)),
                                        "bytes": wheel.stat().st_size,
                                        "sha256": digest.hexdigest()})
            assert wheel_artifacts
        assert not state["reference_tested"] and state["profile"] == "core"
        grading = Path(state["evaluation_directory"])
        if not grading.is_absolute():
            grading = ROOT / grading
        assert read(grading / "command.json")["exit_code"] == 0
        assert read(grading / "output/evaluation/results.json") == evaluation
        if cold != run:
            receipt = read(run / "consumer_continuation.json")
            assert not receipt["cold_source_build_repeated"]
            assert not receipt["cross_task_artifact_reuse"]
            assert receipt["initial_failed_consumer_retained"]
            original = cold / "workspace/output"
            assert read(original / "tests.json") == tests
            original_commands = read(original / "commands.json")
            assert read(output / "commands.json")[:len(original_commands)] == original_commands
            assert any(c["phase"] == "build" and c["exit_code"] == 0 for c in original_commands)
        cgroup_path = cold / "isolation/cgroup_final.json"
        metrics = json.loads(read(cgroup_path)["output"]) if cgroup_path.exists() else {}
        events = dict(line.split() for line in metrics.get("memory.events", "").splitlines())
        assert int(events.get("oom_kill", "0")) == 0
        records.append({
            "task_id": task.name,
            "source_sha256": locked["sha256"],
            "official_test_entries": len(tests),
            "installed_files_checked": evaluation["installed_files_checked"],
            "delivered_wheels_for_empty_install_tree": wheel_artifacts,
            "fresh_independent_consumer_passed": True,
            "accepted_run": str(run.relative_to(ROOT)),
            "cold_source_run": str(cold.relative_to(ROOT)),
            "consumer_continued": cold != run,
            "cold_memory_peak_bytes": int(metrics["memory.peak"]) if metrics else None,
            "cold_oom_kill_count": int(events["oom_kill"]) if events else None,
            "separate_input_snapshot_present": (cold / "isolation/input_manifest.json").exists(),
        })
    report = {"verified_tasks": len(records), "pending_tasks": pending, "records": records,
              "missing_historical_metrics_are_unknown": True, "reference_tested": 0}
    destination = ROOT / "recorded_evidence_audit.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


if __name__ == "__main__":
    result = audit()
    print("AUDITED", result["verified_tasks"], "accepted tasks; pending", result["pending_tasks"])
