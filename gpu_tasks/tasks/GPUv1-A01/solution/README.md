# GPUv1-A01 — SmolLM2-135M-Instruct UltraChat SFT (debug variant)

Offline SFT adaptation of `HuggingFaceTB/SmolLM2-135M-Instruct`
(revision `12fd25f77366fa6b3b4b768ec3050bf629380bac`) to 64 real UltraChat
`train_sft` conversations, plus a reloadable checkpoint, deterministic
responses for the 16 `test_sft` validation conversations, and exact-resume
training state.

## Commands

```bash
python solution/main.py train --input input --output output
python solution/main.py infer --checkpoint output/checkpoint \
    --input input/validation.jsonl --output output/responses.jsonl

# continue training for N extra optimizer steps from saved state
python solution/main.py train --input input --output output \
    --resume output/training_state.pt --steps 8
```

`train` options (defaults): `--model /models/HuggingFaceTB--SmolLM2-135M-Instruct`,
`--epochs 3`, `--batch-size 4`, `--grad-accum 1`, `--lr 2e-5`, `--weight-decay 0`,
`--warmup-ratio 0.05`, `--max-grad-norm 1.0`, `--max-tokens 256`, `--seed 42`,
`--checkpoint output/checkpoint`, `--state output/training_state.pt`,
`--steps` (fresh run: total optimizer steps; with `--resume`: extra steps).

## Method

* Full fine-tune (all 134.5M params, fp32) on the RTX 5090 with real
  autograd/AdamW updates on autoregressive cross-entropy.
* Every conversation is rendered with the tokenizer chat template
  (`apply_chat_template(..., add_generation_prompt=False)`) and truncated to
  256 tokens; padded batches mask pad tokens to `-100`.
* 3 epochs x 16 batches/epoch (batch 4) = 48 optimizer steps; with
  `--seed 42` for data order, initialization and CUDA RNG.
* `loss_before` / `loss_after` are teacher-forced (same template + 256-token
  truncation) mean CE losses over the 16 validation conversations, measured
  before and after the updates (2.486 -> 1.936 on a fresh run).
* `output/run.json` records `train_examples`, `optimizer_steps`, `seed`,
  `loss_before`, `loss_after`, `device`, training params, SHA-256 input hashes,
  synchronized train seconds, weight-change statistics and a run history.
* `output/training_state.pt` stores optimizer, scheduler, global step/epoch,
  Python/NumPy/Torch/CUDA RNG states, hyperparameters, input hashes and the
  checkpoint path, so `--resume` restores weights + optimizer + schedule and
  continues (verified: 48 -> 56 steps with decreasing loss).

## Artifacts

* `output/checkpoint/` — full HF-loadable fp32 weights (`model.safetensors`),
  tokenizer, config and `model_meta.json` (base model + revision).
* `output/responses.jsonl` — 16 lines `{id, prompt, generated_text,
  generated_token_ids}`; greedy decoding, 1–32 new tokens, prompt = messages
  before the first assistant turn rendered with the chat template and truncated
  to 256 tokens.
* `output/run.json`, `output/training_state.pt`.

## Verification performed

Reloaded `output/checkpoint` with plain `transformers`; recomputed the
teacher-forced validation loss (matches `run.json` to <1e-7); regenerated a
response greedily (token ids match `responses.jsonl`); confirmed 16/16 ids
covered, all responses within 1–32 new tokens, weight deltas non-zero
(272/272 tensors changed, max |delta| 4.9e-4), input hashes equal to the
manifest, and resumed step count increased while training loss kept decreasing.
