# GPUv1-A02 debug variant — DPO alignment of SmolLM2-135M-Instruct

Real Direct Preference Optimization on CUDA with the frozen base model used as
the reference policy. No mock weights, no CPU fallback, no random surrogate.

## Usage

```
python solution/main.py doctor   --input input
python solution/main.py train    --input input --output output [--epochs 3] [--lr 1e-5]
python solution/main.py evaluate --checkpoint output/checkpoint \
                                 --input input/validation.jsonl \
                                 --output output/reloaded.json
```

`python solution/main.py --help` and every subcommand `--help` work without
loading any model. `doctor` inspects files, hashes and dependencies only.

## Row schema and masking (mask-audit fix)

UltraFeedback binarized rows carry `prompt` (conversation prefix) plus `chosen`
and `rejected` which may be a plain assistant string **or** a full conversation
array whose earlier entries duplicate the prompt. To avoid scoring prompt
tokens as if they were response tokens:

* The prompt is taken from `row["prompt"]` when present; otherwise it is
  derived as the shared message prefix of `chosen`/`rejected` up to their final
  assistant turns. It is included **exactly once**.
* Only the **final assistant message** of `chosen`/`rejected` is used as a
  response; earlier user turns inside those arrays never enter the response
  mask.
* The response string is the exact prefix-suffix difference between the
  chat-templated full conversation and the chat-templated prompt rendered with
  the generation prefix. The template's response terminator (e.g. `<|im_end|>`)
  is retained, so the scored log-prob sum covers the entire assistant turn.
* The prompt and response are tokenized separately and concatenated, so the
  assistant mask start index is exactly `len(prompt_ids)` and the mask is
  never empty.

## Length handling (`max_tokens = 256`)

1. If the pair fits, nothing is truncated.
2. Otherwise, if the response alone fits, the prompt is left-truncated so the
   response stays complete.
3. Otherwise the response is right-truncated to fill the budget while at least
   one prompt token is retained (up to `MAX_PROMPT_KEEP_ON_RESP_OVERFLOW=64`)
   so the first scored token has a real context and the response mask is
   non-empty.  `run.json` reports `truncated_rows` and, honestly,
   `identical_truncated_rows` (pairs whose chosen/rejected become identical
   after truncation).  Training aborts loudly if a pair cannot be encoded.

## Training

`beta = 0.1`, seed 0, AdamW (lr=1e-5, betas 0.9/0.999), gradient clipping,
3 epochs by default over all 32 pairs (each used at least once; per-row step
counts recorded). Only the policy receives gradients; the reference is
`eval()` + `requires_grad_(False)`.  Real `backward()` + optimizer steps on
CUDA.  The 8 validation pairs are scored only after training.

## Artifacts

`output/checkpoint/` (HF/PEFT-loadable), `output/training_state.pt`
(optimizer, step, reference binding, RNG, losses, per-row step counts),
`output/preferences.json` (validation pairs keyed by **original row IDs** with
policy/reference chosen+rejected log-probs, DPO loss, preference margin),
`output/train_preferences.json`, `output/run.json` (hashes proving the policy
changed and the reference did not, synchronized wall-clock timings, accuracy,
truncation and identical-truncation counts).

`evaluate` reloads the checkpoint from disk, rebuilds the frozen reference
from the base container, recomputes every log-probability independently, and
writes `reloaded.json` with the same row IDs.

## Honest limitations

* Debug scale only: 32 train / 8 validation authentic pairs of a 135M model.
  This does not reproduce the 7B Zephyr reference result and makes no such
  claim.
* Some UltraFeedback responses exceed 256 tokens and were right-truncated;
  `run.json` reports how many.  Pairs whose truncated chosen and rejected
  collapse to the same ids are counted (`identical_truncated_rows`) and left
  in the data honestly rather than hidden.
* Preference accuracy on 8 pairs is a sanity signal, not a quality metric.
* UltraFeedback labels are inherited; they are not ground truth for real user
  preference.
* No network, no package installation, no hyperparameter search, no ensemble.
