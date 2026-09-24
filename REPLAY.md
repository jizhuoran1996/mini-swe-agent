# Recording and replaying model calls

Recording and replay are optional model implementations. Replay uses the normal
agent loop and executes tools in the selected environment. It replaces model
requests with recorded replies, indexed by **source episode ID and model round**.
It never falls back to an online model.

## Record a task

Create a recording overlay, for example `recording.yaml`:

```yaml
agent:
  agent_class: journal
model:
  model_class: recording
  store_path: ./model-tapes
  episode_id: example-run-1
```

Apply it after your usual LiteLLM model and environment configuration:

```bash
mini -c mini.yaml -c your-task.yaml -c recording.yaml \
  -t 'Your task' -o example-run-1.index.json
```

`your-task.yaml` supplies the live model name, model parameters and environment.
Recording makes normal, potentially billable model requests. Keep credentials in
environment variables. `JournalAgent` executes automatically using the default
agent loop; it does not provide the interactive agent's confirmation prompts.
Choose a unique episode ID for every task run, including repeated attempts at the
same issue. Batch runners must create a fresh model and agent for each episode.

`RecordingModel` can also wrap an explicit `backend` model configuration. With the
standard LiteLLM tool-call backend, it records prepared SDK inputs, tool schemas,
parameters, SDK responses, normalized replies, errors and durations. Other
backends receive recording at the generic `model.query()` boundary.

## Replay a task

```bash
python -m minisweagent.run.replay run \
  --store model-tapes --source example-run-1 \
  --output replay-1.index.json
```

The CLI creates a new replay episode automatically and restores the source agent
and environment configuration. An existing output file is not overwritten.

| Option | Behavior |
| --- | --- |
| `--timing recorded` (default) | Reproduce each original logical model-call duration, including its retry/backoff time |
| `--timing instant` | Return replies without intentional waiting |
| `--time-scale 0.5` | Target half the recorded model duration; the default multiplier is 1 |
| `--divergence record` (default) | Record changed input text and continue |
| `--divergence error` | Stop when input text differs |

Lookup and input-audit time count toward the target model duration. Tools execute
at their current speed; container startup and tool durations are not replayed.
Thus a faster tool environment can finish sooner while preserving LLM waiting.
This is response-level replay, not token streaming or network traffic simulation.

For Docker sources, the CLI creates a new container and adds `--pull=never`.
The source image must already exist locally. Containers are cleaned up at exit;
images and recordings are retained. Pin image IDs/digests for reproducibility.

Use `--environment-config fresh-environment.yaml` to override the environment.
The file accepts an `environment:` mapping or the environment configuration
directly. Local environments and sources with mounted storage require an explicit
override pointing to a fresh workspace. Replay does not snapshot or restore
filesystem state. Custom environments must implement mini's Environment interface.

## Matching and failure behavior

A round is one `model.query()` invocation, which may produce several tool calls.
Original tool-call IDs are retained. Internal model retries use separate attempt
numbers within that round: attempt 0 is the logical call, positive attempts are
observable SDK calls. SDK-internal HTTP retries may remain inside one SDK attempt.

Fresh tool observations enter the actual agent history. Input text is audited,
not used as a cache key. Changed message counts, roles, ordering or tool-call IDs
stop replay rather than shifting rounds. Missing, incomplete or corrupt records
also stop replay. Format errors are replayed through the normal correction loop.

Replay follows the original decisions; it cannot adapt those decisions to changed
tool results. Original step/time limits still apply. Runs originally stopped by
cost or time limits may stop at a different boundary; exhausted records never
produce extra model replies. Online continuation and mid-run branching are not
implemented. The current replay formatter targets mini tool-call trajectories.

## Storage, inspection and export

The store contains `index.sqlite3` and content-addressed compressed files in
`blobs/`. Requests reference deduplicated messages. `JournalAgent` saves incremental
message events and externalizes full raw tool stdout, while preserving the
observation content passed to the model. Environment stdout capture can still
allocate substantial memory before it reaches the journal.

Index JSON files depend on the store: back up both the SQLite database and blobs.
Export creates the ordinary full trajectory format, including raw tool outputs:

```bash
python -m minisweagent.run.replay inspect \
  --store model-tapes --episode example-run-1
python -m minisweagent.run.replay export \
  --store model-tapes --episode example-run-1 --output exported.traj.json
```

`replay_match` events retain input differences and actual message references.
`replay_timing` events retain source duration, timing parameters, requested sleep
and elapsed model-phase time. Replay cost is zero; source cost is retained
separately. `info.replay.actual_api_calls` is zero, while the legacy
`model_stats.api_calls` field still counts agent model rounds.

API key and Authorization fields in configuration/SDK arguments are redacted.
Messages and outputs are preserved, so their contents remain part of the record.
This is SDK-boundary recording, not a byte-for-byte HTTP capture.

## Import an existing trajectory

```bash
python -m minisweagent.run.replay import path/to/trajectory.json \
  --store model-tapes --episode imported-run-1 \
  --events path/to/events.jsonl --task-id original-task-id
```

Import requires parsed tool actions and complete model rounds. Legacy inputs are
reconstructed from message prefixes; unrecorded SDK parameters and attempts cannot
be recovered. Optional timing events are JSONL rows containing `kind: "model"`,
`task_id` (or `instance_id`) and `duration_s`, ordered by model round. The default
task ID is the trajectory's parent directory name. Counts must match exactly.

Without timing events, import is supported but replay requires `--timing instant`.
LLM latency is never guessed from adjacent message timestamps. Importing old large
JSON trajectories and exporting full trajectories can require significant memory.

## Validation

```bash
python -m pytest tests/models/test_replay.py tests/models/test_init.py \
  tests/agents/test_default.py tests/agents/test_init.py -q
```

The focused suite passed 86 tests, including real local tool execution, changed
observations, 32 independent replay cursors, timing, retry/error paths, large
stdout retention, legacy import/export, and real LiteLLM requests to a local HTTP
test server. A six-round recorded SWE-bench pytest task was also replayed in fresh
Docker containers: both timing modes reproduced the original patch without live
LLM requests. Its recorded model time was 9.091 seconds, and paced replay measured
9.092 seconds. This validates replay behavior, not a new benchmark score.
