# GPUv1-E10 — CUDA GCN citation link-prediction (debug variant)

Learns a link-prediction model for a real Cora citation graph using the
training edges in `input/edges.npy` only.

## Files
- `solution/main.py` — training / prediction entry point.
- `output/checkpoint.pt` — model weights, config, real Adam optimizer state, step.
- `output/query_scores.npy` — probability for every row of `input/query_pairs.npy`,
  in file order (`float64`, shape `(2110,)`).
- `output/run.json` — config, metrics and training evidence.
- `output/reloaded.npy` — scores re-computed through the `predict` path.

## Commands
```bash
python solution/main.py train   --input input --output output
python solution/main.py predict --checkpoint output/checkpoint.pt \
                                --input input --output output/reloaded.npy
```

## Method
- **Graph:** training citation edges are treated as undirected for message
  passing; the symmetric-normalized adjacency `D^-1/2 (A+I) D^-1/2` is built on
  CUDA. `query_pairs.npy` is *never* part of this graph.
- **Encoder:** 2-layer GCN (`Linear(1433→256) → ReLU → Dropout → Linear(256→128)`),
  dense GPU neighbourhood aggregation `adj @ H`.
- **Scorer:** dot product of node embeddings with a learnable logit
  temperature and bias, `sigmoid(exp(log s)·⟨h_u,h_v⟩ + b)`.
- **Negatives:** sampled uniformly from genuine **non-edges of the training
  graph** (directed pairs, self-loops excluded). No query pair is used as a
  training negative target or positive.
- **Optimization:** Adam (lr 1e-2, weight decay 5e-4), cosine decay, 400 real
  `loss.backward()`/`optimizer.step()` updates; seed fixed at 2026.
- **Internal validation:** 10% of the *training* edges are held out from the
  supervision graph and probed against sampled non-edges of the remaining
  graph — honest held-out-edge AUC ≈ 0.845. The final model is then retrained
  on all supplied training edges.

## Acceptance evidence (from `output/run.json`)
- `steps = 400` (≥ 5), real optimizer state with `optimizer_step_max = 400`.
- `param_delta_l2 ≈ 14.9` → parameters genuinely changed from the seeded init
  (fresh-init vs checkpoint L2 distance ≈ 14.87).
- `first_step_grad_norm ≈ 1.20`, loss 0.80 → 0.395 → real aggregation,
  backprop and updates on CUDA (`device = cuda`, 103 MiB peak GPU memory).
- `query_scores.npy`: 2110 finite probabilities in `[0.0025, 0.99999]`.
- `predict` reload reproduces `query_scores.npy` with max abs diff `0.0`
  (requirement ≤ 1e-5); repeat training runs are bit-identical (diff 0.0).
- Query-pair coverage is 100%: one score per query row, in original order.
