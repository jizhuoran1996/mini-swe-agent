"""Frozen empirical response delays, bound to an immutable source episode."""

from __future__ import annotations

import hashlib
import json
import math
from contextlib import closing
from pathlib import Path
from statistics import median, quantiles

from minisweagent.utils.replay_store import ReplayStore

FEATURE_VERSION = "visible-json-token-proxy-v1"
PROFILE_VERSION = "mini-latency-profile-1"
MANIFEST_VERSION = "mini-latency-manifest-1"


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def write_json_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        stream.write(canonical_json(value) + "\n")


def visible_message(message: dict) -> dict:
    content = message.get("content") or ""
    if not isinstance(content, str):
        raise ValueError("Latency feature version 1 supports text-only messages")
    result = {"role": message["role"], "content": content}
    if message.get("tool_calls"):
        calls = []
        for call in message["tool_calls"]:
            function = call.get("function")
            arguments = function.get("arguments") if isinstance(function, dict) else call.get("arguments")
            name = function.get("name") if isinstance(function, dict) else function
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            arguments = canonical_json(arguments)
            calls.append({"name": name, "arguments": arguments})
        result["tool_calls"] = calls
    return result


class VisibleTokenCounter:
    def __init__(self, encoding: str = "cl100k_base"):
        import tiktoken

        self.encoding = tiktoken.get_encoding(encoding)

    def count(self, value) -> int:
        return len(self.encoding.encode(canonical_json(value), disallowed_special=()))

    def message(self, message: dict) -> int:
        return self.count(visible_message(message))


def source_signature(store: ReplayStore, episode: str) -> tuple[str, int]:
    with closing(store.connect()) as db:
        rows = [
            dict(row)
            for row in db.execute(
                "SELECT round, request, response, error, status FROM calls "
                "WHERE episode=? AND attempt=0 ORDER BY round",
                (episode,),
            )
        ]
    if not rows or [r["round"] for r in rows] != list(range(1, len(rows) + 1)):
        raise ValueError("Latency manifests require complete contiguous source rounds")
    if any(r["status"] == "pending" for r in rows):
        raise ValueError("Source has interrupted calls; cannot bind a latency manifest")
    return digest(rows), len(rows)


def manifest_path(directory: Path, episode: str, replica: str = "0") -> Path:
    return directory / (digest([episode, replica]) + ".json")


class FrozenTiming:
    def __init__(self, path: str, store: ReplayStore, episode: str, replica: str = "0"):
        source = Path(path)
        if source.is_dir():
            source = manifest_path(source, episode, replica)
        raw = source.read_bytes()
        self.sha256 = hashlib.sha256(raw).hexdigest()
        self.manifest = json.loads(raw)
        signature, rounds = source_signature(store, episode)
        if (
            self.manifest.get("format") != MANIFEST_VERSION
            or self.manifest.get("source_episode_id") != episode
            or self.manifest.get("replica_id") != replica
            or self.manifest.get("source_signature") != signature
        ):
            raise ValueError("Latency manifest does not match the source episode/replica/signature")
        self.rows = self.manifest["rounds"]
        if [r["round"] for r in self.rows] != list(range(1, rounds + 1)):
            raise ValueError("Latency manifest must cover every source round exactly once")
        for row in self.rows:
            seconds = row["duration_seconds"]
            if (
                isinstance(seconds, bool)
                or not isinstance(seconds, (int, float))
                or not math.isfinite(seconds)
                or seconds < 0
            ):
                raise ValueError("Simulated durations must be finite nonnegative numbers")
        self.reference = {
            "manifest_sha256": self.sha256,
            "profile_sha256": self.manifest["profile_sha256"],
            "replica_id": replica,
            "seed": self.manifest["seed"],
        }

    def row(self, round: int) -> dict:
        return self.rows[round - 1]


class EmpiricalLatency:
    def __init__(self, profile: dict, neighbors: int = 50):
        if profile.get("format") != PROFILE_VERSION or profile.get("feature_version") != FEATURE_VERSION:
            raise ValueError("Unsupported latency profile or feature version")
        if not isinstance(neighbors, int) or isinstance(neighbors, bool) or neighbors < 1:
            raise ValueError("neighbors must be a positive integer")
        self.profile = profile
        self.profile_sha256 = digest(profile)
        self.neighbors = neighbors
        self.observations = sorted(profile["observations"], key=lambda r: r["sample_id"])
        if not self.observations or len({r["sample_id"] for r in self.observations}) != len(self.observations):
            raise ValueError("Latency profile needs observations with unique sample IDs")
        for row in self.observations:
            for name in ("input_tokens", "output_tokens", "duration_seconds"):
                value = row[name]
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or value < 0
                ):
                    raise ValueError(f"Invalid profile value: {name}")
            if not isinstance(row["first_round"], bool):
                raise ValueError("first_round must be boolean")
        self.scales = []
        for field in ("input_tokens", "output_tokens"):
            values = [math.log1p(row[field]) for row in self.observations]
            q = quantiles(values, n=4, method="inclusive") if len(values) > 1 else [0, 0, 0]
            self.scales.append(max(q[2] - q[0], 0.25))

    def sample(self, features: dict, *, episode: str, round: int, seed: int, replica: str = "0") -> dict:
        candidates = [r for r in self.observations if r["first_round"] == features["first_round"]]
        if not candidates:
            raise ValueError("Calibration profile has no observations for this request phase")
        fields = ("input_tokens", "output_tokens")

        def distance(row):
            return sum(
                ((math.log1p(features[k]) - math.log1p(row[k])) / scale) ** 2 for k, scale in zip(fields, self.scales)
            )

        ranked = sorted(candidates, key=lambda row: (distance(row), row["sample_id"]))[: self.neighbors]
        choice = int(digest([seed, episode, round, replica]), 16) % len(ranked)
        donor = ranked[choice]
        outside = [
            k for k in fields if not min(r[k] for r in candidates) <= features[k] <= max(r[k] for r in candidates)
        ]
        return {
            "round": round,
            "duration_seconds": donor["duration_seconds"],
            "features": features,
            "donor_sample_id": donor["sample_id"],
            "neighbor_count": len(ranked),
            "nearest_distance": math.sqrt(distance(ranked[0])),
            "donor_distance": math.sqrt(distance(donor)),
            "outside_calibration_range": outside,
            "neighbor_duration_median": median(r["duration_seconds"] for r in ranked),
        }


def build_manifest(
    store: ReplayStore, episode: str, profile: dict, *, seed: int = 0, replica: str = "0", neighbors: int = 50
) -> dict:
    signature, rounds = source_signature(store, episode)
    sampler = EmpiricalLatency(profile, neighbors)
    counter = VisibleTokenCounter(profile["tokenizer"])
    tool_tokens = counter.count(profile["tools"])
    counts = {}
    results = []
    for round in range(1, rounds + 1):
        call = store.call(episode, round)
        refs = call["request"]["messages"]
        for ref in refs:
            if ref not in counts:
                counts[ref] = counter.message(store.get(ref))
        reply = call["response"]
        if reply is None and call["error"] and call["error"].get("type") == "FormatError":
            for message in call["error"]["messages"]:
                raw = message.get("extra", {}).get("response")
                if isinstance(raw, dict) and raw.get("choices"):
                    reply = raw["choices"][0]["message"]
                    break
        if reply is None:
            raise ValueError(
                "Manifest generation requires a saved model response for every round, including format errors"
            )
        features = {
            "input_tokens": tool_tokens + sum(counts[ref] for ref in refs),
            "output_tokens": counter.message(reply),
            "first_round": round == 1,
        }
        results.append(sampler.sample(features, episode=episode, round=round, seed=seed, replica=replica))
    return {
        "format": MANIFEST_VERSION,
        "source_episode_id": episode,
        "source_signature": signature,
        "replica_id": replica,
        "seed": seed,
        "profile_sha256": sampler.profile_sha256,
        "profile_name": profile.get("name"),
        "feature_version": FEATURE_VERSION,
        "tokenizer": profile["tokenizer"],
        "timing_provenance": "simulated_empirical_response_latency",
        "rounds": results,
    }
