"""Generate immutable timing manifests offline; replay needs no tokenizer."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from minisweagent.utils.replay_store import ReplayStore
from minisweagent.utils.replay_timing import build_manifest, manifest_path, write_json_new

app = typer.Typer(no_args_is_help=True)


@app.command()
def generate(
    profile: Path = typer.Option(..., help="Empirical latency profile JSON"),
    store: Path = typer.Option(..., help="Replay store containing the source episode"),
    source: str = typer.Option(...),
    output_dir: Path = typer.Option(..., help="New per-episode manifest is written without overwriting existing files"),
    seed: int = typer.Option(0),
    replica: str = typer.Option("0"),
    neighbors: int = typer.Option(50),
) -> None:
    result = build_manifest(
        ReplayStore(store), source, json.loads(profile.read_text()), seed=seed, replica=replica, neighbors=neighbors
    )
    destination = manifest_path(output_dir, source, replica)
    write_json_new(destination, result)
    typer.echo(json.dumps({"manifest": str(destination), "rounds": len(result["rounds"])}))


if __name__ == "__main__":
    app()
