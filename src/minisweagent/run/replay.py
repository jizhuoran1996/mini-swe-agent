"""Import, inspect and export model tapes; replay using the normal agent loop."""

from __future__ import annotations

import json
import time
from contextlib import closing
from pathlib import Path

import typer

from minisweagent.agents.journal import JournalAgent
from minisweagent.environments import get_environment
from minisweagent.models.replay import ReplayModel
from minisweagent.utils.replay_store import ReplayStore, without_secrets

app = typer.Typer(no_args_is_help=True)


def import_trajectory(
    store: ReplayStore, trajectory: Path, episode_id: str, events: Path | None = None, task_id: str = ""
) -> dict:
    data = json.loads(trajectory.read_text())
    if data.get("trajectory_format") == "mini-swe-agent-index-1":
        raise ValueError("An indexed trajectory already belongs to a replay store; use its episode_id directly")
    messages = data["messages"]
    selected = [
        (index, message)
        for index, message in enumerate(messages)
        if message.get("role") == "assistant" or message.get("extra", {}).get("interrupt_type") == "FormatError"
    ]
    if any(message.get("role") == "assistant" and "actions" not in message.get("extra", {}) for _, message in selected):
        raise ValueError("Import currently requires mini tool-call trajectories with parsed actions")
    timings = []
    if events is not None:
        for line in events.open():
            row = json.loads(line)
            if row.get("kind") == "model" and (row.get("task_id") or row.get("instance_id")) == task_id:
                timings.append(row["duration_s"])
        if len(timings) != len(selected):
            raise ValueError(f"Timing/model-round mismatch: {len(timings)} durations for {len(selected)} rounds")
    if data["info"]["model_stats"]["api_calls"] != len(selected):
        raise ValueError("Trajectory contains a missing model response; cannot silently renumber its rounds")
    model_config = data["info"]["config"]["model"]
    if data["info"]["config"].get("model_type", "").endswith(".RecordingModel"):
        model_config = model_config["backend"]
    model_config = data["info"].get("replay", {}).get("source_model_config", model_config)
    metadata = {
        "source_file": str(trajectory.resolve()),
        "task_id": task_id,
        "model_config": model_config,
        "trajectory_info": data["info"],
        "rounds": len(selected),
        "timing_source": str(events.resolve()) if events else None,
        "request_provenance": "reconstructed_from_trajectory",
        "sdk_attempts_recorded": False,
        "initial_messages": store.message_refs(messages[:2]),
    }
    store.create_episode(episode_id, "import", metadata)
    refs = store.message_refs(messages)
    for round, (index, message) in enumerate(selected, start=1):
        store.start_call(
            episode_id,
            round,
            0,
            {"level": "model.query", "messages": refs[:index], "kwargs": {}, "provenance": "legacy_reconstruction"},
        )
        error = None
        if message.get("extra", {}).get("interrupt_type") == "FormatError":
            error = {"type": "FormatError", "messages": [message]}
        store.finish_call(
            episode_id,
            round,
            0,
            response=None if error else message,
            error=error,
            duration=timings[round - 1] if timings else None,
        )
    for index, message in enumerate(messages):
        compact = dict(message)
        if "extra" in compact:
            compact["extra"] = dict(compact["extra"])
            if "raw_output" in compact["extra"]:
                compact["extra"]["raw_output_ref"] = store.put_text(compact["extra"].pop("raw_output"))
        store.event(episode_id, "message", {"index": index, "ref": store.put(compact)})
    return without_secrets(metadata)


def export_trajectory(store: ReplayStore, episode_id: str) -> dict:
    metadata = store.metadata(episode_id)
    messages = []
    for event in store.events(episode_id, "message"):
        message = store.get(event["ref"])
        extra = message.get("extra", {})
        if "raw_output_ref" in extra:
            extra["raw_output"] = store.text(extra.pop("raw_output_ref"))
        messages.append(message)
    if not messages:
        raise ValueError("No agent message journal: use JournalAgent when recording to support full trajectory export")
    info = metadata.get("trajectory", {}).get("info", metadata.get("trajectory_info", {}))
    return {"info": info, "messages": messages, "trajectory_format": "mini-swe-agent-1.1"}


@app.command("import")
def import_command(
    trajectory: Path,
    store: Path = typer.Option(...),
    episode: str = typer.Option(...),
    events: Path | None = typer.Option(None, help="Original profiler events.jsonl, for exact model-call durations"),
    task_id: str = typer.Option("", help="ID in the timing events; defaults to trajectory's parent directory name"),
) -> None:
    result = import_trajectory(ReplayStore(store), trajectory, episode, events, task_id or trajectory.parent.name)
    typer.echo(
        json.dumps({"episode_id": episode, "rounds": result["rounds"], "timing_source": result["timing_source"]})
    )


@app.command("export")
def export_command(
    store: Path = typer.Option(...), episode: str = typer.Option(...), output: Path = typer.Option(...)
) -> None:
    if output.exists():
        raise ValueError("Refusing to overwrite an existing trajectory")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(export_trajectory(ReplayStore(store), episode), ensure_ascii=False, indent=2))
    typer.echo(str(output))


@app.command("inspect")
def inspect_command(store: Path = typer.Option(...), episode: str = typer.Option(...)) -> None:
    tape = ReplayStore(store)
    with closing(tape.connect()) as db:
        calls = [
            dict(row)
            for row in db.execute(
                "SELECT round, attempt, status, duration FROM calls WHERE episode=? ORDER BY round, attempt", (episode,)
            )
        ]
    typer.echo(
        json.dumps(
            {
                "episode_id": episode,
                "calls": calls,
                "replay_checks": tape.events(episode, "replay_match"),
                "replay_timings": tape.events(episode, "replay_timing"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("run")
def run_command(
    store: Path = typer.Option(...),
    source: str = typer.Option(..., help="Source episode ID"),
    output: Path = typer.Option(..., help="New indexed trajectory; existing files are never overwritten"),
    episode: str = typer.Option("", help="New replay episode ID; defaults to a UUID"),
    timing: str = typer.Option("recorded", help="recorded, instant or simulated"),
    time_scale: float = typer.Option(1.0, help="Multiplier for recorded or simulated response durations"),
    timing_manifest: Path | None = typer.Option(None, help="Frozen simulated timing file or manifest directory"),
    timing_replica_id: str = typer.Option("0", help="Replica ID bound into the simulated timing manifest"),
    divergence: str = typer.Option("record", help="record or error for changed input text"),
    environment_config: Path | None = typer.Option(None, help="Optional JSON/YAML environment override"),
) -> None:
    if output.exists():
        raise ValueError("Refusing to overwrite an existing trajectory")
    model = ReplayModel(
        store_path=str(store),
        source_episode_id=source,
        episode_id=episode,
        timing=timing,
        time_scale=time_scale,
        divergence=divergence,
        timing_manifest=str(timing_manifest) if timing_manifest is not None else None,
        timing_replica_id=timing_replica_id,
    )
    source_info = model.source.get("trajectory_info", model.source.get("trajectory", {}).get("info", {}))
    if not source_info:
        raise ValueError("Agent/environment metadata missing; record using JournalAgent or supply your own run script")
    config = source_info["config"]
    with closing(model.store.connect()) as db:
        unavailable = db.execute(
            "SELECT COUNT(*) FROM calls WHERE episode=? AND attempt=0 AND (status='pending' OR duration IS NULL)",
            (source,),
        ).fetchone()[0]
    if timing == "recorded" and unavailable:
        raise ValueError("Source has incomplete calls or missing durations; no environment was started")
    env_config = dict(config["environment"])
    env_config["environment_class"] = config["environment_type"]
    if environment_config is not None:
        from minisweagent.config import get_config_from_spec

        overrides = get_config_from_spec(str(environment_config))
        env_config.update(overrides.get("environment", overrides))
    elif env_config["environment_class"].endswith(".LocalEnvironment"):
        raise ValueError("Provide --environment-config with a fresh workspace before replaying a local environment")
    elif any(
        arg in ("-v", "--volume", "--mount", "--volumes-from")
        or arg.startswith(("--volume=", "--mount=", "--volumes-from=", "-v/"))
        for arg in env_config.get("run_args", [])
    ):
        raise ValueError("Source uses mounted storage; provide --environment-config pointing to a fresh workspace")
    if env_config["environment_class"].endswith(".DockerEnvironment"):
        env_config["run_args"] = [
            *env_config.get("run_args", ["--rm"]),
            "--pull=never",
            "--label",
            f"agentos.replay={model.episode_id}",
        ]
    first = model.store.call(source, 1)["request"]["messages"]
    prompts = [model.store.get(ref) for ref in first]
    if len(prompts) != 2 or [m.get("role") for m in prompts] != ["system", "user"]:
        raise ValueError("CLI expects an initial system/user pair; use ReplayModel in a custom run script otherwise")
    env = get_environment(env_config)
    try:
        started = time.perf_counter()
        agent_config = dict(config["agent"])
        agent_config.update(system_template="{{ replay_system }}", instance_template="{{ task }}", output_path=output)
        agent = JournalAgent(model, env, **agent_config)
        result = agent.run(prompts[1]["content"], replay_system=prompts[0]["content"])
        expected = source_info.get("submission")
        summary = {
            "episode_id": model.episode_id,
            "source_episode_id": source,
            "actual_api_calls": 0,
            "actual_cost": 0.0,
            "model_rounds": agent.n_calls,
            "agent_wall_seconds": time.perf_counter() - started,
            "replay_model_seconds": sum(
                e["elapsed_seconds"] for e in model.store.events(model.episode_id, "replay_timing")
            ),
            "timing": timing,
            "time_scale": time_scale,
            "exit_status": result.get("exit_status"),
            "submission_matches": result.get("submission") == expected if expected is not None else None,
            "input_difference_rounds": sum(
                bool(e["differences"]) for e in model.store.events(model.episode_id, "replay_match")
            ),
        }
        output.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2))
        typer.echo(json.dumps(summary))
    finally:
        if hasattr(env, "cleanup"):
            env.cleanup()


if __name__ == "__main__":
    app()
