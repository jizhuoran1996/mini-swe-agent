# Simulated response timing for offline replay

`ReplayModel` supports three timing modes:

| Mode | Response timing |
| --- | --- |
| `recorded` (default) | Wait for the original model-call duration. Missing durations are an error. |
| `instant` | Return the stored reply without an intentional wait. |
| `simulated` | Wait for the duration in a frozen, source-bound manifest. |

All modes execute real tools and retrieve model replies by source episode and round. Simulated timing makes no LLM requests and does not modify the original duration. It models a remote service's response delay; it does not consume GPU capacity locally or simulate an additional provider queue.

## Generate a manifest offline

Install the optional tokenizer dependency with `pip install 'mini-swe-agent[replay-timing]'`. Only generation needs the tokenizer; replay reads a small manifest for its own episode.

An empirical profile is a JSON object with these fields:

```json
{
  "format": "mini-latency-profile-1",
  "feature_version": "visible-json-token-proxy-v1",
  "name": "my-measured-service",
  "tokenizer": "cl100k_base",
  "tools": [],
  "observations": [
    {
      "sample_id": "source-episode/1",
      "first_round": true,
      "input_tokens": 1000,
      "output_tokens": 100,
      "duration_seconds": 2.5
    },
    {
      "sample_id": "source-episode/2",
      "first_round": false,
      "input_tokens": 1200,
      "output_tokens": 150,
      "duration_seconds": 3.0
    }
  ]
}
```

These values illustrate the schema, not a useful calibration. A real profile needs many measured requests and the actual tool definitions. For mini's tool-calling model use `[BASH_TOOL]` from `minisweagent.models.utils.actions_toolcall`. Set additional provenance fields for the service/configuration, tokenizer version, source files and exclusions.

Use `VisibleTokenCounter` to compute **both** calibration and target features. Input length is the sum of canonical visible-message JSON token counts plus the canonical tool-definition token count; output length is the visible response JSON token count. Tool names and canonicalized JSON arguments are included. Reasoning fields, provider metadata, raw-output duplicates and tool call IDs are excluded. This is a consistent text-length proxy, not the provider's exact token usage. Version 1 accepts text-only content.

The sampler separates first requests from later requests, computes distance in `log1p(input_tokens), log1p(output_tokens)` normalized by calibration interquartile ranges, then uniformly samples one of the nearest 50 observations. `seed + source episode + round + replica` determines the draw, independently of worker scheduling and backend. The measured donor latency already includes its original network/provider delay; do not add the same queue again. Missing hidden reasoning is represented by empirical variability, not an assumed zero token count.

```bash
python -m minisweagent.run.replay_timing \
  --profile profile.json \
  --store ./tapes \
  --source original-episode \
  --output-dir ./timing-manifests \
  --seed 42
```

The output directory contains an immutable JSON file for the source episode and replica. Existing files are never overwritten. It stores source fingerprints, profile hash, seed, every selected donor and duration, visible-length estimates, neighbor distances, and out-of-range flags. A range flag only checks the feature-wise calibration envelope; it is not a confidence interval or proof of sufficient coverage.

Use `--replica 1` (etc.) when independent copies of the same trace should have distinct draws. Use the same replica and manifest when comparing execution backends. Generation requires all source rounds to be complete and contain the original response, including an SDK response for imported format errors; it never invents missing rounds.

## Replay with real waits

```bash
python -m minisweagent.run.replay run \
  --store ./tapes \
  --source original-episode \
  --output ./simulated.index.json \
  --timing simulated \
  --timing-manifest ./timing-manifests \
  --time-scale 1
```

The usual fresh-environment requirements of the replay CLI still apply. `--timing-manifest` also accepts the individual manifest file. `--timing-replica-id` selects a non-default replica. A manifest from another source, an incomplete round list, or a nonfinite/negative delay is rejected before the CLI starts the tool environment.

The Python interface accepts the same fields:

```python
model = ReplayModel(
    store_path="./tapes",
    source_episode_id="original-episode",
    timing="simulated",
    timing_manifest="./timing-manifests",
    timing_replica_id="0",
    time_scale=1.0,
)
```

The timer starts when the real agent calls `query`. Existing lookup/audit time is deducted from the target delay; `sleep` waits only the remainder. Slow tools naturally delay the next request. There is no attempt to force the trace onto its original absolute timeline. Actual tool-output changes are audited but do not change the precomputed delays, making backend comparisons reproducible.

`replay_timing` events distinguish:

- `source_duration_seconds` and `simulated_duration_seconds`;
- scaled `target_duration_seconds`, `pre_wait_seconds`, requested and actual sleep;
- `elapsed_seconds` through wake-up and `deadline_lateness_seconds`;
- manifest/profile hashes and donor sample IDs.

The timing event itself is written after wake-up, so its `elapsed_seconds` excludes that final journal write and response copying. An outer caller timer measures complete `query` latency, including those costs. Hosts under contention may return later than the target; lateness is reported, not hidden. `time_scale` defines a different response-speed scenario and does not accelerate real tools.

## Validation and interpretation

Hold out complete issues, including all repeated runs of each issue. Validate response quantiles and per-episode cumulative waits over several seeds, then compare recorded and simulated pacing with real tool execution. Report per-task error as well as aggregate agreement: matching the overall latency distribution does not reconstruct each task's hidden reasoning.

Keep instant replay as an execution-pressure baseline. For service-speed sensitivity, reuse one manifest at scales such as 0.5, 1 and 2. Report wall time, useful tool CPU, concurrency, resource occupancy over time and failures together. The first version samples independent per-request delays; it does not preserve provider-wide incidents, all within-episode correlations, or capacity changes at higher concurrency. Those require separate calibration and an explicit shared-service simulator.
