# Implementation notes

- `main.py` supports `run`, `doctor` and `query`; `main.py --help` never imports
  torch/transformers, and `doctor` inspects files/deps without loading weights.
- `doctor` returns 78 when any required input, model file or CUDA device is missing,
  otherwise 0.
- `run` fails fast (78) when required inputs or CUDA are unavailable and never falls
  back to CPU or to fabricated answers.
- Input integrity: SHA-256 of `schema.sql`, `chinook.sqlite`, `requests.jsonl` is
  compared with `manifest.json` and recorded in `run.json`.
- SQL safety: string literals are blanked before keyword/`;` checks, the connection is
  opened read-only (`mode=ro` + `PRAGMA query_only=ON`), and the database hash is
  re-checked after the run to prove the file was not modified.
- Each execution uses a `set_progress_handler` callback that returns non-zero after
  3 s, aborting runaway statements with a real sqlite error.
