from __future__ import annotations

import copy
import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from minisweagent.agents.journal import JournalAgent
from minisweagent.environments.local import LocalEnvironment
from minisweagent.exceptions import FormatError
from minisweagent.models import GLOBAL_MODEL_STATS
from minisweagent.models.replay import RecordingModel, ReplayModel
from minisweagent.models.test_models import make_toolcall_output
from minisweagent.models.utils.actions_toolcall import BASH_TOOL
from minisweagent.utils.replay_store import ReplayStore
from minisweagent.utils.replay_timing import (
    FEATURE_VERSION,
    PROFILE_VERSION,
    EmpiricalLatency,
    FrozenTiming,
    VisibleTokenCounter,
    build_manifest,
    manifest_path,
    visible_message,
    write_json_new,
)


def reply(command):
    return make_toolcall_output(
        "",
        [
            {
                "id": "call-1",
                "type": "function",
                "function": {"name": "bash", "arguments": json.dumps({"command": command})},
            }
        ],
        [{"command": command, "tool_call_id": "call-1"}],
    )


@pytest.fixture
def profile():
    return {
        "format": PROFILE_VERSION,
        "feature_version": FEATURE_VERSION,
        "tokenizer": "cl100k_base",
        "tools": [BASH_TOOL],
        "observations": [
            {
                "sample_id": str(i),
                "first_round": i < 4,
                "input_tokens": 300 + i * 10,
                "output_tokens": 30 + i,
                "duration_seconds": 0.04 + i / 1000,
            }
            for i in range(8)
        ],
    }


@pytest.fixture
def tape(tmp_path):
    store = ReplayStore(tmp_path / "store")
    store.create_episode("source", "import", {"model_config": {}})
    store.start_call("source", 1, 0, {"messages": store.message_refs([{"role": "user", "content": "original"}])})
    store.finish_call("source", 1, 0, response=reply("true"), duration=None)
    return store


def test_visible_features_normalize_tool_calls_and_exclude_hidden_metadata():
    a = reply("printf 'visible'")
    a["reasoning_content"] = "hidden" * 100
    a["extra"]["raw_output"] = "discard" * 1000
    b = {
        "role": "assistant",
        "content": "",
        "metadata": {"secret": "discard"},
        "tool_calls": [{"id": "different", "function": "bash", "arguments": {"command": "printf 'visible'"}}],
    }
    counter = VisibleTokenCounter()
    assert visible_message(a) == visible_message(b)
    assert counter.message(a) == counter.message(b) > 0
    b["tool_calls"][0]["arguments"]["command"] *= 100
    assert counter.message(b) > counter.message(a)


def test_sampling_is_reproducible_order_independent_and_phase_matched(profile):
    sampler = EmpiricalLatency(profile, neighbors=2)
    features = {"input_tokens": 100000, "output_tokens": 4000, "first_round": True}
    first = sampler.sample(features, episode="issue-a", round=1, seed=7)
    reversed_profile = profile | {"observations": list(reversed(profile["observations"]))}
    assert first == EmpiricalLatency(reversed_profile, neighbors=2).sample(features, episode="issue-a", round=1, seed=7)
    assert first["outside_calibration_range"] == ["input_tokens", "output_tokens"]
    assert int(first["donor_sample_id"]) < 4 and first["neighbor_count"] == 2
    draws = {
        sampler.sample(features, episode="issue-a", round=1, seed=7, replica=str(i))["donor_sample_id"]
        for i in range(16)
    }
    assert len(draws) == 2


def test_parallel_simulation_waits_and_preserves_missing_original_duration(tape, profile, tmp_path):
    manifest = build_manifest(tape, "source", profile, seed=42)
    path = manifest_path(tmp_path / "delays", "source")
    write_json_new(path, manifest)
    with pytest.raises(FileExistsError):
        write_json_new(path, manifest)

    def run(index):
        model = ReplayModel(
            store_path=str(tape.path),
            source_episode_id="source",
            episode_id=f"copy-{index}",
            timing="simulated",
            timing_manifest=str(path.parent),
            time_scale=0.5,
        )
        before = time.perf_counter()
        response = model.query([{"role": "user", "content": f"different-{index}"}])
        elapsed = time.perf_counter() - before
        event = tape.events(model.episode_id, "replay_timing")[0]
        assert event["source_duration_seconds"] is None
        assert event["target_duration_seconds"] == manifest["rounds"][0]["duration_seconds"] * 0.5
        assert elapsed >= event["target_duration_seconds"] - 0.002
        assert event["requested_sleep_seconds"] <= event["target_duration_seconds"]
        assert response["extra"]["replay"]["actual_api_calls"] == response["extra"]["cost"] == 0
        return event["simulation"]["manifest_sha256"], response["extra"]["replay"]["input_difference_count"]

    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(run, range(4)))
    assert len({r[0] for r in results}) == 1 and all(r[1] == 1 for r in results)
    assert tape.call("source", 1)["duration"] is None
    recorded = ReplayModel(store_path=str(tape.path), source_episode_id="source")
    with pytest.raises(ValueError, match="duration is unavailable"):
        recorded.query([{"role": "user", "content": "original"}])


@pytest.mark.parametrize(
    "mutation", ["missing_round", "wrong_episode", "wrong_replica", "wrong_signature", "nan", "negative"]
)
def test_invalid_manifest_fails_before_replay_episode_is_created(tape, profile, tmp_path, mutation):
    manifest = build_manifest(tape, "source", profile)
    if mutation == "missing_round":
        manifest["rounds"] = []
    elif mutation == "wrong_episode":
        manifest["source_episode_id"] = "different"
    elif mutation == "wrong_replica":
        manifest["replica_id"] = "different"
    elif mutation == "wrong_signature":
        manifest["source_signature"] = "0" * 64
    elif mutation == "nan":
        manifest["rounds"][0]["duration_seconds"] = float("nan")
    else:
        manifest["rounds"][0]["duration_seconds"] = -1
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        ReplayModel(
            store_path=str(tape.path),
            source_episode_id="source",
            episode_id="must-not-exist",
            timing="simulated",
            timing_manifest=str(path),
        )
    with pytest.raises(KeyError, match="Unknown episode"):
        tape.metadata("must-not-exist")


def test_manifest_rejects_different_reply_and_scaled_overflow(tape, profile, tmp_path):
    manifest = build_manifest(tape, "source", profile)
    path = tmp_path / "manifest.json"
    write_json_new(path, manifest)
    other = ReplayStore(tmp_path / "other")
    other.create_episode("source", "import", {"model_config": {}})
    other.start_call("source", 1, 0, tape.call("source", 1)["request"])
    other.finish_call("source", 1, 0, response=reply("different command"))
    with pytest.raises(ValueError, match="signature"):
        FrozenTiming(str(path), other, "source")
    huge = copy.deepcopy(manifest)
    huge["rounds"][0]["duration_seconds"] = 1e308
    write_json_new(tmp_path / "huge.json", huge)
    model = ReplayModel(
        store_path=str(tape.path),
        source_episode_id="source",
        timing="simulated",
        timing_manifest=str(tmp_path / "huge.json"),
        time_scale=2,
    )
    with pytest.raises(ValueError, match="Scaled replay duration"):
        model.query([{"role": "user", "content": "original"}])


def test_simulated_format_error_uses_saved_sdk_response(profile, tmp_path):
    store = ReplayStore(tmp_path / "format-error-store")
    store.create_episode("source", "import", {"model_config": {}})
    messages = [{"role": "user", "content": "task"}]
    correction = {
        "role": "user",
        "content": "Use a tool",
        "extra": {
            "cost": 1.0,
            "response": {"choices": [{"message": {"role": "assistant", "content": "forgot tool"}}]},
        },
    }
    store.start_call("source", 1, 0, {"messages": store.message_refs(messages)})
    store.finish_call("source", 1, 0, error={"type": "FormatError", "messages": [correction]})
    path = tmp_path / "error-timing.json"
    write_json_new(path, build_manifest(store, "source", profile))
    model = ReplayModel(
        store_path=str(store.path),
        source_episode_id="source",
        timing="simulated",
        timing_manifest=str(path),
        time_scale=0,
    )
    with pytest.raises(FormatError) as error:
        model.query(messages)
    assert error.value.messages[0]["extra"]["cost"] == 0
    assert store.call("source", 1)["error"]["messages"][0]["extra"]["cost"] == 1.0
    assert store.events(model.episode_id, "replay_timing")[0]["simulated_duration_seconds"] > 0


def test_real_agent_loop_with_simulated_timing_and_changed_tool_output(profile, tmp_path, reset_global_stats):
    source_dir, target_dir = tmp_path / "original", tmp_path / "target"
    source_dir.mkdir()
    target_dir.mkdir()
    model = RecordingModel(
        store_path=str(tmp_path / "agent-store"),
        episode_id="source",
        backend={
            "model_class": "minisweagent.models.test_models.DeterministicToolcallModel",
            "model_name": "fixture",
            "outputs": [
                reply('printf "%s" "$MARKER"'),
                reply("echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT; printf patch"),
            ],
        },
    )
    agent = JournalAgent(
        model,
        LocalEnvironment(cwd=str(source_dir), env={"MARKER": "old"}),
        system_template="system",
        instance_template="{{task}}",
        output_path=tmp_path / "source.json",
    )
    assert agent.run("task")["submission"] == "patch"
    source_durations = [model.store.call("source", i)["duration"] for i in (1, 2)]
    path = tmp_path / "delays.json"
    write_json_new(path, build_manifest(model.store, "source", profile, seed=4))
    replay = ReplayModel(
        store_path=str(model.store.path), source_episode_id="source", timing="simulated", timing_manifest=str(path)
    )
    calls_before = GLOBAL_MODEL_STATS.n_calls
    agent = JournalAgent(
        replay,
        LocalEnvironment(cwd=str(target_dir), env={"MARKER": "new"}),
        system_template="system",
        instance_template="{{task}}",
        output_path=tmp_path / "target.json",
    )
    assert agent.run("task")["submission"] == "patch"
    assert GLOBAL_MODEL_STATS.n_calls == calls_before and agent.cost == 0
    events = replay.store.events(replay.episode_id, "replay_timing")
    assert len(events) == 2 and all(e["elapsed_seconds"] >= e["target_duration_seconds"] - 0.002 for e in events)
    assert [model.store.call("source", i)["duration"] for i in (1, 2)] == source_durations
    assert replay.store.events(replay.episode_id, "replay_match")[1]["differences"]
