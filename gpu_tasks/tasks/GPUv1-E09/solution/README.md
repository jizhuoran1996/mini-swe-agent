# GPUv1-E09 — Heterogeneous Cora (paper + word) topic classifier

Real Cora paper nodes, citation edges and word nodes; a CUDA heterogeneous GNN trained with
only the provided `train_ids` / `train_labels`.

## Run

```bash
python solution/main.py train   --input input --output output
python solution/main.py predict --checkpoint output/checkpoint.pt --input input \
                                --output output/reloaded.npy
```

`train` writes `output/checkpoint.pt`, `output/test_predictions.npy` and `output/run.json`.
Optional flags: `--epochs` (default 100), `--hidden` (64), `--layers` (3), `--dropout` (0.5),
`--lr` (1e-2), `--weight-decay` (5e-4), `--val-frac` (0.0; held-out split of the **training**
labels only, used for the sanity check reported below).

## Graph and model

| node type | count | initial content |
|---|---|---|
| paper | 2708 | `features.npy` (1433 binary word features), linear projection |
| word  | 1433 | mean of the features of the papers containing the word (derived from real features) |

| relation | source | use |
|---|---|---|
| `paper–cite–paper` | `edges.npy`, made undirected | citation message passing |
| `paper–word` | `paper_word_edges.npy`, both message directions | words read their papers, papers read their words |

Each of the 3 layers performs genuine heterogeneous message passing (`HeteroLayer`):

```
paper_i' = ReLU( W_self·paper_i + W_cite·mean_{j in cite(i)} paper_j + W_word·mean_{w in words(i)} word_w )
word_w'  = ReLU( W_wself·word_w + W_wpaper·mean_{i contains w} paper_i )
```

Aggregations are sparse means over the real edge index tensors (`index_add`), so citation and
paper–word structure both enter every forward/backward pass — this is not a row-wise MLP.
Classification is 7-way on the paper embeddings; loss is cross-entropy on the 1624 training
papers only (full-graph transductive forward; `test_ids`/labels are never used for training).

## Reproducibility / determinism

Fixed seed 2026 (`random`, NumPy, torch, CUDA), `cudnn.deterministic`, and
`torch.use_deterministic_algorithms(True)` with `CUBLAS_WORKSPACE_CONFIG=:4096:8`.
Two full training runs produce bitwise-identical loss curves and `test_predictions.npy`
(verified). The checkpoint stores the model parameters, configuration, optimizer state,
completed step count and all RNG states (python / numpy / torch / torch-CUDA).

## Observed results (this machine, RTX 5090, torch 2.11.0+cu129)

* device `cuda`, parameters/inputs on CUDA, 100 optimizer updates, loss 1.9465 → 0.1205,
  train accuracy 0.988.
* Held-out sanity run (`--val-frac 0.25`, 406 training labels held out, test labels untouched):
  **validation accuracy 0.8645**, far above the 0.40 requirement.
* Reload check: `predict` re-creates the model from `checkpoint.pt` and reproduces
  `test_predictions.npy` with max abs difference **2.4e-7** (≤ 1e-5); crossing devices
  (CPU reload vs. saved CUDA predictions) also differs by only 2.4e-7.
* Graph participation (post-training ablations, no labels involved, recorded in `run.json`):
  * removing citation edges changes test probabilities by 0.556 L1 and flips the argmax of
    571 / 2708 papers,
  * removing paper–word edges changes test probabilities by 0.140 L1 and flips 112 papers.
  * all 5278 citation edges and 49216 paper–word edges are consumed and cover all 2708 papers /
    1432 non-isolated word nodes (`input_coverage` in `run.json`).
* Timing: ~0.6 s of training, ~1.7 s end-to-end for `train`.

## Outputs

* `checkpoint.pt` — `model_state`, `config`, `optimizer_state`, `step`/`global_step`,
  `rng_state`, training history, graph usage/coverage evidence.
* `test_predictions.npy` — `float32 (542, 7)` probabilities in `test_ids.npy` order, rows sum to 1.
* `run.json` — losses per step, step count, device, structure, input coverage, ablations, timings.
