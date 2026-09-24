from __future__ import annotations

import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import pytest

from minisweagent.agents.default import DefaultAgent
from minisweagent.agents.journal import JournalAgent
from minisweagent.environments.local import LocalEnvironment
from minisweagent.exceptions import FormatError
from minisweagent.models import GLOBAL_MODEL_STATS, get_model
from minisweagent.models.replay import RecordingModel, ReplayModel
from minisweagent.models.test_models import make_toolcall_output
from minisweagent.run.replay import export_trajectory, import_trajectory
from minisweagent.utils.replay_store import ReplayStore


def response(*commands: str) -> dict:
    calls = [
        {
            "id": f"tool-{i}",
            "type": "function",
            "function": {"name": "bash", "arguments": json.dumps({"command": command})},
        }
        for i, command in enumerate(commands)
    ]
    return make_toolcall_output(
        "Recorded reply", calls, [{"command": cmd, "tool_call_id": f"tool-{i}"} for i, cmd in enumerate(commands)]
    )


def put_call(store, round, messages, reply, duration=0.04, episode="source"):
    store.start_call(episode, round, 0, {"messages": store.message_refs(messages), "kwargs": {}})
    store.finish_call(episode, round, 0, response=reply, duration=duration)


@pytest.fixture
def store(tmp_path):
    tape = ReplayStore(tmp_path / "tapes")
    tape.create_episode("source", "record", {"model_config": {"model_name": "offline-test"}})
    return tape


def test_agent_loop_records_and_replays_changed_tools(tmp_path, reset_global_stats):
    source_dir, replay_dir = tmp_path / "source", tmp_path / "replay"
    source_dir.mkdir()
    replay_dir.mkdir()
    recorder = RecordingModel(
        store_path=str(tmp_path / "tapes"),
        episode_id="original",
        backend={
            "model_class": "minisweagent.models.test_models.DeterministicToolcallModel",
            "model_name": "fixture",
            "cost_per_call": 0.25,
            "outputs": [
                response('printf "%s" "$MARKER"', "printf 'patch-data' > result.txt"),
                response("echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT; cat result.txt"),
            ],
        },
    )
    source = JournalAgent(
        recorder,
        LocalEnvironment(cwd=str(source_dir), env={"MARKER": "original-output"}),
        system_template="system",
        instance_template="{{task}}",
        step_limit=3,
        output_path=tmp_path / "source.index.json",
    )
    assert source.run("task")["submission"] == "patch-data"
    original_cost = source.cost
    replay = get_model(
        config={
            "model_class": "replay",
            "model_name": "fixture",
            "store_path": str(tmp_path / "tapes"),
            "source_episode_id": "original",
            "episode_id": "replayed",
            "timing": "instant",
        }
    )
    agent = JournalAgent(
        replay,
        LocalEnvironment(cwd=str(replay_dir), env={"MARKER": "different-output"}),
        system_template="system",
        instance_template="{{task}}",
        step_limit=3,
        output_path=tmp_path / "replay.index.json",
    )
    calls_before = GLOBAL_MODEL_STATS.n_calls
    assert agent.run("task")["submission"] == "patch-data"
    assert agent.n_calls == recorder.round == replay.round == 2
    assert agent.cost == 0 and original_cost > 0
    assert GLOBAL_MODEL_STATS.n_calls == calls_before
    assert (replay_dir / "result.txt").read_text() == "patch-data"
    checks = replay.store.events("replayed", "replay_match")
    assert not checks[0]["differences"] and checks[1]["differences"][0]["role"] == "tool"
    assert all(c["structure_matches"] for c in checks)
    exported = export_trajectory(replay.store, "replayed")
    assert "different-output" in exported["messages"][3]["extra"]["raw_output"]
    assert exported["info"]["replay"]["actual_api_calls"] == 0
    assert json.loads((tmp_path / "replay.index.json").read_text())["trajectory_format"] == "mini-swe-agent-index-1"


def test_default_timing_scaling_and_missing_duration(store):
    messages = [{"role": "user", "content": "input"}]
    put_call(store, 1, messages, response("true"), duration=0.12)
    recorded = ReplayModel(store_path=str(store.path), source_episode_id="source")
    started = time.perf_counter()
    assert recorded.query(messages)["extra"]["cost"] == 0
    elapsed = time.perf_counter() - started
    assert elapsed >= 0.11
    instant = ReplayModel(store_path=str(store.path), source_episode_id="source", timing="instant")
    started = time.perf_counter()
    instant.query(messages)
    assert time.perf_counter() - started < elapsed
    scaled = ReplayModel(store_path=str(store.path), source_episode_id="source", time_scale=0.2)
    started = time.perf_counter()
    scaled.query(messages)
    assert time.perf_counter() - started >= 0.02
    assert recorded.store.events(recorded.episode_id, "replay_timing")[0]["elapsed_seconds"] >= 0.11
    assert instant.store.events(instant.episode_id, "replay_timing")[0]["requested_sleep_seconds"] == 0
    put_call(store, 2, messages, response("true"), duration=None)
    with pytest.raises(ValueError, match="duration is unavailable"):
        recorded.query(messages)
    assert instant.query(messages)["extra"]["cost"] == 0
    with pytest.raises(ValueError, match="finite nonnegative"):
        ReplayModel(store_path=str(store.path), source_episode_id="source", time_scale=float("nan"))


def test_missing_pending_and_changed_structure_never_fall_back(store):
    model = ReplayModel(store_path=str(store.path), source_episode_id="source", timing="instant")
    with pytest.raises(KeyError, match="no API fallback"):
        model.query([])
    store.start_call("source", 1, 0, {"messages": []})
    model = ReplayModel(store_path=str(store.path), source_episode_id="source", timing="instant")
    with pytest.raises(ValueError, match="interrupted"):
        model.query([])
    store.finish_call("source", 1, 0, response=response("true"), duration=0)
    model = ReplayModel(store_path=str(store.path), source_episode_id="source", timing="instant")
    with pytest.raises(ValueError, match="structure changed"):
        model.query([{"role": "tool", "tool_call_id": "unexpected", "content": "anything"}])


def test_attempts_are_not_rounds_and_format_error_recovery(store, tmp_path):
    messages = [{"role": "system", "content": "system"}, {"role": "user", "content": "task"}]
    correction = {"role": "user", "content": "Please use the bash tool", "extra": {"cost": 0.3}}

    def recorded_round():
        with store.capture("source", 1, {"messages": store.message_refs(messages)}):
            with pytest.raises(TimeoutError), store.capture("source", 1, {"messages": []}, attempt=1):
                raise TimeoutError("fixture")
            with store.capture("source", 1, {"messages": []}, attempt=2) as capture:
                capture.response = {"choices": [{"message": {"tool_calls": []}}]}
            raise FormatError(correction)

    with pytest.raises(FormatError):
        recorded_round()
    put_call(store, 2, messages + [correction], response("echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"))
    model = ReplayModel(store_path=str(store.path), source_episode_id="source", timing="instant")
    agent = DefaultAgent(
        model, LocalEnvironment(cwd=str(tmp_path)), system_template="system", instance_template="{{task}}", step_limit=3
    )
    assert agent.run("task")["exit_status"] == "Submitted"
    assert model.round == 2 and agent.cost == 0
    assert store.call("source", 1, 1)["error"]["type"] == "TimeoutError"
    assert store.call("source", 1, 2)["status"] == "ok"
    assert store.call("source", 1)["error"]["type"] == "FormatError"


def test_parallel_replays_have_independent_cursors_and_immutable_source(store):
    messages = [{"role": "user", "content": "same-task"}]
    put_call(store, 1, messages, response("echo first"))
    put_call(store, 2, messages, response("echo second"))

    def replay(index):
        model = ReplayModel(
            store_path=str(store.path), source_episode_id="source", episode_id=f"replica-{index}", timing="instant"
        )
        return [model.query(messages)["extra"]["actions"][0]["command"] for _ in range(2)]

    with ThreadPoolExecutor(32) as pool:
        assert list(pool.map(replay, range(32))) == [["echo first", "echo second"]] * 32
    assert store.call("source", 1)["response"]["extra"]["cost"] == 1
    with pytest.raises(sqlite3.IntegrityError):
        store.create_episode("source", "record", {})
    with pytest.raises(ValueError, match="overwrite"):
        store.finish_call("source", 1, 0, response=response("overwritten"))


def test_strict_difference_policy_is_optional(store):
    put_call(store, 1, [{"role": "user", "content": "old"}], response("true"))
    changed = [{"role": "user", "content": "new"}]
    strict = ReplayModel(store_path=str(store.path), source_episode_id="source", timing="instant", divergence="error")
    with pytest.raises(ValueError, match="input differs"):
        strict.query(changed)
    permissive = ReplayModel(store_path=str(store.path), source_episode_id="source", timing="instant")
    assert permissive.query(changed)["extra"]["replay"]["input_difference_count"] == 1


def test_large_tool_output_is_retained_once_and_exportable(tmp_path, reset_global_stats):
    recorder = RecordingModel(
        store_path=str(tmp_path / "tapes"),
        episode_id="large",
        backend={
            "model_class": "minisweagent.models.test_models.DeterministicToolcallModel",
            "model_name": "fixture",
            "observation_template": "{{output.output[:32]}}",
            "outputs": [
                response("head -c 2097152 /dev/zero | tr '\\000' x"),
                response("echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"),
            ],
        },
    )
    agent = JournalAgent(
        recorder,
        LocalEnvironment(cwd=str(tmp_path)),
        system_template="system",
        instance_template="{{task}}",
        output_path=tmp_path / "index.json",
    )
    assert agent.run("task")["exit_status"] == "Submitted"
    tool = next(m for m in agent.messages if m["role"] == "tool")
    assert "raw_output" not in tool["extra"] and len(tool["content"]) == 32
    assert recorder.store.text(tool["extra"]["raw_output_ref"]) == "x" * 2097152
    assert (tmp_path / "index.json").stat().st_size < 16384
    exported = export_trajectory(recorder.store, "large")
    assert next(m for m in exported["messages"] if m["role"] == "tool")["extra"]["raw_output"] == "x" * 2097152


def test_legacy_import_uses_explicit_model_timings_and_preserves_inputs(tmp_path):
    messages = [{"role": "system", "content": "system"}, {"role": "user", "content": "task"}, response("true")]
    trajectory = tmp_path / "trajectory.json"
    trajectory.write_text(
        json.dumps(
            {
                "messages": messages,
                "info": {
                    "model_stats": {"api_calls": 1},
                    "config": {"model": {"model_name": "fixture", "model_kwargs": {"api_key": "fixture-secret"}}},
                },
            }
        )
    )
    events = tmp_path / "events.jsonl"
    events.write_text(json.dumps({"kind": "model", "task_id": "task-7", "duration_s": 0.21}) + "\n")
    store = ReplayStore(tmp_path / "tapes")
    import_trajectory(store, trajectory, "imported", events, "task-7")
    assert store.call("imported", 1)["duration"] == 0.21
    assert [store.get(r) for r in store.call("imported", 1)["request"]["messages"]] == messages[:2]
    assert store.metadata("imported")["model_config"]["model_kwargs"]["api_key"] == "[REDACTED]"
    assert export_trajectory(store, "imported")["messages"] == messages
    with pytest.raises(ValueError, match="mismatch"):
        import_trajectory(store, trajectory, "bad-import", events, "wrong-task")


def test_litellm_records_real_sdk_requests_and_retry_attempts(tmp_path, reset_global_stats):
    received = []
    reply = response("printf offline")

    class Endpoint(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            payload = {"error": {"message": "temporary fixture failure", "type": "server_error", "code": "503"}}
            if len(received) > 1:
                payload = {
                    "id": "offline-request-2",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "offline-fixture",
                    "choices": [
                        {
                            "index": 0,
                            "message": {k: v for k, v in reply.items() if k != "extra"},
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
                }
            body = json.dumps(payload).encode()
            self.send_response(503 if len(received) == 1 else 200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(("127.0.0.1", 0), Endpoint)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        recorder = RecordingModel(
            store_path=str(tmp_path / "tapes"),
            episode_id="sdk",
            model_name="openai/offline-fixture",
            cost_tracking="ignore_errors",
            model_kwargs={
                "api_base": f"http://127.0.0.1:{server.server_port}/v1",
                "api_key": "offline-fixture-key",
                "max_retries": 0,
                "num_retries": 0,
                "timeout": 5,
            },
        )
        assert (
            recorder.query([{"role": "user", "content": "task"}])["extra"]["actions"][0]["command"] == "printf offline"
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    assert len(received) == 2 and recorder.round == 1 and recorder.attempt == 2
    assert recorder.store.call("sdk", 1, 1)["error"]["status_code"] == 503
    assert recorder.store.call("sdk", 1, 2)["response"]["id"] == "offline-request-2"
    assert recorder.store.call("sdk", 1, 2)["request"]["tools"] == received[1]["tools"]
    assert recorder.store.call("sdk", 1, 2)["request"]["kwargs"]["api_key"] == "[REDACTED]"
    assert recorder.store.call("sdk", 1)["duration"] >= 4
