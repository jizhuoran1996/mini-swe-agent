# GPUv1-A07 (debug variant) — DLRM CTR training

Trains a real CUDA DLRM click-through-rate model on the genuine `Criteo_x1`
subset shipped with this task (1000 train rows / 100 held-out rows), and
delivers a reloadable checkpoint plus validation probabilities.

## Usage

```bash
# inspect inputs + dependencies only (no training, exit 78 if anything missing)
python solution/main.py doctor --input input

# train -> output/checkpoint.pt, output/validation_predictions.npy, output/run.json
python solution/main.py train --input input --output output

# score brand-new JSONL rows with the saved checkpoint
python solution/main.py predict \
    --checkpoint output/checkpoint.pt \
    --input input/validation.jsonl \
    --output output/repredict.npy

python solution/main.py --help
```

## Model

* 13 numeric features -> bottom MLP (Linear -> ReLU) -> **8 dims**.
* 26 categorical features -> **26 independent 8-dim embedding tables**
  (index `0` reserved for unknown/unseen categories).
* Concatenate 1 dense vector + 26 embedding vectors, take **all pairwise dot
  products** (27 * 26 / 2 = **351** interaction features).
* Top MLP `351 -> 64 -> 32 -> 1` logit, trained with `BCEWithLogitsLoss`.
* Adam optimizer, fixed seed `1234`, 30 epochs of shuffled mini-batches
  (batch size 125 -> 8 steps/epoch, 240 steps total).

Every train row participates in at least 30 gradient updates; the run report
verifies full row coverage explicitly.

## Preprocessing / reloadable feature semantics

* Category dictionaries are built **from train rows only** and stored inside
  `checkpoint.pt` under `preprocessor.category_maps`.
* Unknown categories map to embedding index `0`, so `predict` never crashes on
  unseen tokens.
* Numeric features are standardised with train-fitted mean/std, also stored in
  the checkpoint (`numeric_mean`, `numeric_std`).
* `predict` re-uses exactly this saved preprocessor, so a separate process
  reproduces identical feature semantics.

## Outputs

`output/checkpoint.pt`
: `model_state_dict`, `optimizer_state_dict`, `step`, `epochs`, `seed`,
  `rng` (torch / numpy / cuda), `preprocessor`, `config`.

`output/validation_predictions.npy`
: float32 probabilities, shape `(100,)` for the provided validation split.

`output/run.json`
: config, seed, device, torch/cuda versions, train timing (CUDA-synchronised),
  per-check results, independent AUC report, input sha256 digests.

## Independent checks performed during `train`

1. **structure** — exactly 26 embedding tables, each 8-dim; interaction width 351.
2. **parameter_change** — real tensors changed between an initial and final snapshot.
3. **input_coverage** — every training row appeared in at least one update.
4. **finite_bce** — every recorded loss was finite.
5. **reload_cuda_backward** — the saved checkpoint is reloaded into a fresh model
   on CUDA, a forward + `backward()` is executed, and gradients verified present.

AUC is computed by an independent Mann-Whitney rank implementation (with
mid-ranks for ties) and is reported for information only — **no quality
threshold is applied**.

## Honest limitations

* This is the **debug** variant: real, genuine `reczoo/Criteo_x1` records, but a
  small 1000/100 subset with an intentionally small categorical domain. It is
  **not** the `reference_large` DLRM/Terabyte FL=3 configuration and does not
  claim multi-rank all-to-all, 82 GB checkpointing, or MLPerf DLRMv2 parity.
* Single-GPU only; no NCCL / hybrid parallelism.
* The validation split's labels are hidden, so `validation_predictions.npy`
  carries probabilities only; validation AUC is reported as `null` unless the
  label field happens to be present in the validation rows.
* CUDA is mandatory. There is intentionally no CPU fallback: `train` and
  `predict` exit non-zero when a CUDA device is unavailable.
* No hyper-parameter search, no ensembling — exactly one required training run.
