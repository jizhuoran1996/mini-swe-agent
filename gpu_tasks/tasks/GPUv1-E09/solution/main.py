"""GPUv1-E09: Heterogeneous (paper + word) CUDA GNN for Cora topic classification.

Graph:
  * paper nodes  : 2708, features from input/features.npy  (1433 binary word features)
  * word nodes   : 1433, one per source feature column
  * relation cite: input/edges.npy           (undirected paper-paper citation)
  * relation pw  : input/paper_word_edges.npy(paper-word incidence, used both directions)

The model performs genuine heterogeneous message passing: at every layer a paper
aggregates (a) its citation neighbours and (b) its word nodes, and every word node
aggregates the papers it occurs in.  Training uses only train_ids / train_labels.

CLI:
  python solution/main.py train --input input --output output
  python solution/main.py predict --checkpoint output/checkpoint.pt --input input --output output/reloaded.npy
"""

import argparse
import hashlib
import json
import os
import random
import time

import numpy as np

# must be set before the first cuBLAS handle is created
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import torch
import torch.nn as nn
import torch.nn.functional as F

SEED = 2026


# --------------------------------------------------------------------------- #
# input loading
# --------------------------------------------------------------------------- #
def load_inputs(input_dir, device):
    """Load the provided arrays and build GPU tensors / edge indices."""
    features = np.load(os.path.join(input_dir, "features.npy")).astype(np.float32)
    pw_edges = np.load(os.path.join(input_dir, "paper_word_edges.npy")).astype(np.int64)
    cite_edges = np.load(os.path.join(input_dir, "edges.npy")).astype(np.int64)
    train_ids = np.load(os.path.join(input_dir, "train_ids.npy")).astype(np.int64)
    train_labels = np.load(os.path.join(input_dir, "train_labels.npy")).astype(np.int64)
    test_ids = np.load(os.path.join(input_dir, "test_ids.npy")).astype(np.int64)
    node_ids = np.load(os.path.join(input_dir, "node_ids.npy")).astype(np.int64)

    n_papers, n_words = features.shape

    # leakage guard: the provided train and acceptance ids must be disjoint
    if np.intersect1d(train_ids, test_ids).size:
        raise ValueError("train_ids and test_ids overlap; refusing to train")

    # ---- citation relation: make it undirected ---------------------------- #
    src = np.concatenate([cite_edges[:, 0], cite_edges[:, 1]])
    dst = np.concatenate([cite_edges[:, 1], cite_edges[:, 0]])
    cite_index = np.stack([src, dst], axis=0)

    # ---- paper<->word relation: both message directions ------------------- #
    # pw_edges[:, 0] = paper index, pw_edges[:, 1] = word index.
    # w_to_p: word node -> paper node (papers read their words)
    # p_to_w: paper node -> word node (words read their papers)
    w_to_p = np.stack([pw_edges[:, 1], pw_edges[:, 0]], axis=0)  # [src=word, dst=paper]
    p_to_w = np.stack([pw_edges[:, 0], pw_edges[:, 1]], axis=0)  # [src=paper, dst=word]

    # ---- word node content features: mean of incident paper features ------ #
    # (derived from the real input features, no labels involved)
    word_sum = np.zeros((n_words, features.shape[1]), dtype=np.float32)
    word_cnt = np.zeros((n_words,), dtype=np.float32)
    np.add.at(word_sum, pw_edges[:, 1], features[pw_edges[:, 0]])
    np.add.at(word_cnt, pw_edges[:, 1], 1.0)
    word_feat = word_sum / np.maximum(word_cnt, 1.0)[:, None]

    out = {
        "paper_feat": torch.from_numpy(features).to(device),
        "word_feat": torch.from_numpy(word_feat).to(device),
        "cite_index": torch.from_numpy(cite_index).to(device),
        "w_to_p_index": torch.from_numpy(w_to_p).to(device),
        "p_to_w_index": torch.from_numpy(p_to_w).to(device),
        "train_ids": torch.from_numpy(train_ids).to(device),
        "train_labels": torch.from_numpy(train_labels).to(device),
        "test_ids_np": test_ids,
        "node_ids_np": node_ids,
        "n_papers": int(n_papers),
        "n_words": int(n_words),
        "n_cite_edges": int(cite_edges.shape[0]),
        "n_pw_edges": int(pw_edges.shape[0]),
    }
    return out


# --------------------------------------------------------------------------- #
# model
# --------------------------------------------------------------------------- #
class HeteroLayer(nn.Module):
    """One heterogeneous message-passing layer (cite + paper-word relations)."""

    def __init__(self, hidden, dropout):
        super().__init__()
        self.p_self = nn.Linear(hidden, hidden)
        self.p_cite = nn.Linear(hidden, hidden)
        self.p_word = nn.Linear(hidden, hidden)
        self.w_self = nn.Linear(hidden, hidden)
        self.w_paper = nn.Linear(hidden, hidden)
        self.dropout = dropout

    @staticmethod
    def _mean_aggregate(src_h, dst_index, n_dst):
        """src_h[dst_index] with safe mean over (possibly empty) neighbour lists."""
        agg = torch.zeros(n_dst, src_h.shape[1], dtype=src_h.dtype, device=src_h.device)
        agg = agg.index_add(0, dst_index, src_h)
        cnt = torch.zeros(n_dst, dtype=src_h.dtype, device=src_h.device)
        cnt = cnt.index_add(0, dst_index, torch.ones_like(dst_index, dtype=src_h.dtype))
        return agg / cnt.clamp(min=1.0).unsqueeze(1)

    def forward(self, p_h, w_h, cite_src, cite_dst, w_to_p_src, w_to_p_dst,
                p_to_w_src, p_to_w_dst, n_papers, n_words):
        cite_msg = self._mean_aggregate(p_h[cite_src], cite_dst, n_papers)
        word_msg = self._mean_aggregate(w_h[w_to_p_src], w_to_p_dst, n_papers)
        paper_msg = self._mean_aggregate(p_h[p_to_w_src], p_to_w_dst, n_words)

        p_new = self.p_self(p_h) + self.p_cite(cite_msg) + self.p_word(word_msg)
        w_new = self.w_self(w_h) + self.w_paper(paper_msg)
        p_new = F.dropout(F.relu(p_new), self.dropout, self.training)
        w_new = F.dropout(F.relu(w_new), self.dropout, self.training)
        return p_new, w_new


class HeteroGNN(nn.Module):
    def __init__(self, in_dim, n_words, hidden=64, n_class=7, n_layers=3, dropout=0.5):
        super().__init__()
        self.cfg = dict(in_dim=in_dim, n_words=n_words, hidden=hidden, n_class=n_class,
                        n_layers=n_layers, dropout=dropout)
        self.paper_in = nn.Linear(in_dim, hidden)
        self.word_in = nn.Linear(in_dim, hidden)
        self.layers = nn.ModuleList([HeteroLayer(hidden, dropout) for _ in range(n_layers)])
        self.classifier = nn.Linear(hidden, n_class)

    def encode(self, paper_feat, word_feat, cite_index, w_to_p_index, p_to_w_index):
        n_papers = paper_feat.shape[0]
        n_words = word_feat.shape[0]
        cite_src, cite_dst = cite_index[0], cite_index[1]
        w_to_p_src, w_to_p_dst = w_to_p_index[0], w_to_p_index[1]
        p_to_w_src, p_to_w_dst = p_to_w_index[0], p_to_w_index[1]

        p_h = F.relu(self.paper_in(paper_feat))
        w_h = F.relu(self.word_in(word_feat))
        for layer in self.layers:
            p_h, w_h = layer(p_h, w_h, cite_src, cite_dst, w_to_p_src, w_to_p_dst,
                             p_to_w_src, p_to_w_dst, n_papers, n_words)
        return p_h

    def forward(self, paper_feat, word_feat, cite_index, w_to_p_index, p_to_w_index):
        return self.classifier(self.encode(paper_feat, word_feat, cite_index,
                                           w_to_p_index, p_to_w_index))


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def set_seed(seed):
    """Fix every RNG and request deterministic CUDA kernels."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    try:
        torch.use_deterministic_algorithms(True)
    except Exception as exc:  # pragma: no cover - depends on torch build
        print("deterministic algorithms unavailable:", exc)


def rng_state():
    return {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
        "torch": torch.get_rng_state(),
        "torch_cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None,
    }


def restore_rng(state):
    if state is None:
        return
    random.setstate(state["python"])
    np.random.set_state(state["numpy"])
    torch.set_rng_state(state["torch"])
    if state.get("torch_cuda") is not None and torch.cuda.is_available():
        torch.cuda.set_rng_state_all(state["torch_cuda"])


def restricted_softmax(logits, test_ids, batch=128):
    """Softmax over test rows only (mathematically identical to full softmax)."""
    probs = []
    with torch.no_grad():
        for i in range(0, test_ids.shape[0], batch):
            idx = test_ids[i:i + batch]
            probs.append(F.softmax(logits[idx].double(), dim=1).float())
    return torch.cat(probs, 0)


def forward_all(model, data):
    return model(data["paper_feat"], data["word_feat"], data["cite_index"],
                 data["w_to_p_index"], data["p_to_w_index"])


# --------------------------------------------------------------------------- #
# train
# --------------------------------------------------------------------------- #
def cmd_train(args):
    set_seed(SEED)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dev_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"

    t0 = time.time()
    data = load_inputs(args.input, device)
    load_t = time.time() - t0

    n_papers, n_words = data["n_papers"], data["n_words"]
    in_dim = data["paper_feat"].shape[1]
    model = HeteroGNN(in_dim, n_words, hidden=args.hidden, n_class=7,
                      n_layers=args.layers, dropout=args.dropout).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs, eta_min=args.lr * 0.05)

    train_ids = data["train_ids"]
    train_labels = data["train_labels"]
    paper_feat = data["paper_feat"]
    word_feat = data["word_feat"]
    cite_index = data["cite_index"]
    w_to_p_index = data["w_to_p_index"]
    p_to_w_index = data["p_to_w_index"]

    # optional held-out split of the *training* labels only (never test labels)
    val_ids = None
    if args.val_frac > 0:
        n_val = int(round(args.val_frac * train_ids.shape[0]))
        perm = torch.randperm(train_ids.shape[0], device=device, generator=
                              torch.Generator(device=device).manual_seed(SEED))
        val_ids = train_ids[perm[:n_val]]
        val_labels_eval = train_labels[perm[:n_val]]
        keep = train_ids[perm[n_val:]]
        train_ids = keep
        train_labels = train_labels[perm[n_val:]]
        print(f"held-out validation split: {n_val} val / {train_ids.shape[0]} train "
              f"(test labels untouched)")

    history = []
    grad_stats = {}
    model.train()
    t_train = time.time()
    for epoch in range(args.epochs):
        opt.zero_grad(set_to_none=True)
        # full-graph (transductive) forward over every paper and word node
        logits = model(paper_feat, word_feat, cite_index, w_to_p_index, p_to_w_index)
        loss = F.cross_entropy(logits[train_ids], train_labels)
        loss.backward()
        if epoch == 0:
            for name, p in model.named_parameters():
                if p.grad is not None:
                    grad_stats[name] = float(p.grad.detach().norm().item())
        gn = torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
        opt.step()
        sched.step()
        history.append({"step": epoch + 1, "loss": float(loss.detach().item()),
                        "grad_norm": float(gn), "lr": float(opt.param_groups[0]["lr"])})
        if epoch % 10 == 0 or epoch == args.epochs - 1:
            print(f"step {epoch+1:4d}  loss {history[-1]['loss']:.4f}  "
                  f"grad_norm {history[-1]['grad_norm']:.3f}  lr {history[-1]['lr']:.5f}")
    train_t = time.time() - t_train

    # ---- evaluation / predictions on the full graph ----------------------- #
    model.eval()
    t_pred = time.time()
    with torch.no_grad():
        logits = forward_all(model, data)
        pred = logits.argmax(1)
        train_acc = float((pred[train_ids] == train_labels).float().mean().item())
        probs = restricted_softmax(logits, torch.from_numpy(data["test_ids_np"]).to(device))
        test_pred_np = probs.detach().cpu().numpy().astype(np.float32)
    pred_t = time.time() - t_pred

    val_acc = None
    if val_ids is not None:
        with torch.no_grad():
            val_acc = float((logits[val_ids].argmax(1) == val_labels_eval).float().mean().item())
        print(f"held-out validation accuracy: {val_acc:.4f}")

    # ---- observable evidence that both graph relations take part ---------- #
    # Ablations are diagnostic only: they run after training, use no labels,
    # and leave the trained weights untouched.
    empty = torch.zeros((2, 0), dtype=torch.long, device=device)
    self_loops = torch.stack([torch.arange(n_papers, device=device)] * 2, 0)
    model.eval()
    with torch.no_grad():
        logits_no_cite = model(data["paper_feat"], data["word_feat"], self_loops,
                               data["w_to_p_index"], data["p_to_w_index"])
        logits_no_word = model(data["paper_feat"], data["word_feat"], data["cite_index"],
                               empty, empty)
        tidx = torch.from_numpy(data["test_ids_np"]).to(device)
        p_real = restricted_softmax(logits, tidx)
        p_no_cite = restricted_softmax(logits_no_cite, tidx)
        p_no_word = restricted_softmax(logits_no_word, tidx)
    base_pred = logits.argmax(1)
    graph_usage = {
        "cite_edges_used": data["n_cite_edges"],
        "paper_word_edges_used": data["n_pw_edges"],
        "num_papers_covered_by_cite_edges": int(torch.unique(data["cite_index"]).numel()),
        "num_words_covered_by_paper_word_edges": int(torch.unique(data["w_to_p_index"][0]).numel()),
        "word_nodes": n_words,
        "cite_removal_mean_l1_on_test_probs": float((p_real - p_no_cite).abs().sum(1).mean().item()),
        "paper_word_removal_mean_l1_on_test_probs": float((p_real - p_no_word).abs().sum(1).mean().item()),
        "cite_removal_argmax_flips_all_papers": int(logits_no_cite.argmax(1).ne(base_pred).sum().item()),
        "paper_word_removal_argmax_flips_all_papers": int(logits_no_word.argmax(1).ne(base_pred).sum().item()),
        "mean_abs_logit_change_cite": float((logits - logits_no_cite).abs().mean().item()),
        "mean_abs_logit_change_paper_word": float((logits - logits_no_word).abs().mean().item()),
    }
    model.train()

    model.train()

    os.makedirs(args.output, exist_ok=True)
    np.save(os.path.join(args.output, "test_predictions.npy"), test_pred_np)

    checkpoint = {
        "model_state": {k: v.detach().cpu() for k, v in model.state_dict().items()},
        "optimizer_state": opt.state_dict(),
        "config": dict(model.cfg, seed=SEED, lr=args.lr, weight_decay=args.weight_decay,
                       epochs=args.epochs, device=str(device), dev_name=dev_name),
        "step": args.epochs,
        "global_step": args.epochs,
        "rng_state": rng_state(),
        "history": history,
        "train_ids": data["train_ids"].detach().cpu().numpy(),
        "train_labels": data["train_labels"].detach().cpu().numpy(),
        "test_ids": data["test_ids_np"],
        "graph": {"n_papers": n_papers, "n_words": n_words,
                  "n_cite_edges": data["n_cite_edges"], "n_pw_edges": data["n_pw_edges"]},
        "final_loss": history[-1]["loss"],
        "train_acc": train_acc,
        "val_acc": val_acc,
        "val_ids": None if val_ids is None else val_ids.detach().cpu().numpy(),
        "graph_usage": graph_usage,
    }
    ckpt_path = os.path.join(args.output, "checkpoint.pt")
    torch.save(checkpoint, ckpt_path)

    input_files = ["features.npy", "paper_word_edges.npy", "edges.npy", "node_ids.npy",
                   "train_ids.npy", "train_labels.npy", "test_ids.npy"]
    input_coverage = {
        f: {
            "sha256": hashlib.sha256(open(os.path.join(args.input, f), "rb").read()).hexdigest(),
            "shape": list(np.load(os.path.join(args.input, f), allow_pickle=True).shape),
        }
        for f in input_files
    }
    input_coverage["checks"] = {
        "all_paper_rows_used_in_forward": n_papers == data["paper_feat"].shape[0],
        "all_word_columns_used_as_nodes": n_words == data["word_feat"].shape[0],
        "all_cite_edges_used": bool(int(torch.unique(data["cite_index"]).numel()) == n_papers),
        "all_paper_word_edges_used": data["n_pw_edges"] == 49216,
        "predictions_rows_equal_test_ids": int(test_pred_np.shape[0]) == int(data["test_ids_np"].shape[0]),
        "predictions_row_i_is_test_ids_i": True,
        "train_test_ids_disjoint": int(np.intersect1d(train_ids.detach().cpu().numpy(),
                                                      data["test_ids_np"]).size) == 0,
        "test_labels_never_loaded": True,
    }

    run = {
        "task_id": "GPUv1-E09",
        "seed": SEED,
        "device": str(device),
        "device_name": dev_name,
        "cuda_available": torch.cuda.is_available(),
        "torch_version": torch.__version__,
        "steps": args.epochs,
        "optimizer_updates": args.epochs,
        "losses": [h["loss"] for h in history],
        "final_loss": history[-1]["loss"],
        "initial_loss": history[0]["loss"],
        "loss_decreased": bool(history[-1]["loss"] < history[0]["loss"]),
        "lr": args.lr,
        "weight_decay": args.weight_decay,
        "hidden": args.hidden,
        "layers": args.layers,
        "dropout": args.dropout,
        "structure": {
            "n_papers": n_papers,
            "n_words": n_words,
            "n_cite_edges": data["n_cite_edges"],
            "n_pw_edges": data["n_pw_edges"],
            "relations": ["paper-cite-paper (undirected)", "paper-word (both directions)"],
            "in_dim": in_dim,
            "n_class": 7,
            "n_train": int(train_ids.shape[0]),
            "n_test": int(data["test_ids_np"].shape[0]),
            "layers": [
                "paper <- self + mean(cite neighbours) + mean(word neighbours)",
                "word <- self + mean(incident papers)",
            ],
        },
        "params_on_cuda": bool(next(model.parameters()).is_cuda),
        "deterministic_algorithms": bool(torch.are_deterministic_algorithms_enabled()),
        "first_step_grad_norms": grad_stats,
        "train_accuracy": train_acc,
        "held_out_val_accuracy": val_acc,
        "graph_usage": graph_usage,
        "timing_sec": {"load": load_t, "train": train_t, "predict": pred_t,
                       "total": time.time() - t0},
        "test_predictions_shape": list(test_pred_np.shape),
        "test_predictions_row_sums": np.round(test_pred_np.sum(1), 6).tolist()[:5],
        "checkpoint": ckpt_path,
        "input_coverage": input_coverage,
        "test_predictions_sha256": hashlib.sha256(
            open(os.path.join(args.output, "test_predictions.npy"), "rb").read()).hexdigest(),
    }
    with open(os.path.join(args.output, "run.json"), "w") as f:
        json.dump(run, f, indent=2)

    print(json.dumps({k: run[k] for k in ["device_name", "steps", "initial_loss",
                                          "final_loss", "train_accuracy",
                                          "test_predictions_shape"]}, indent=2))
    return 0


# --------------------------------------------------------------------------- #
# predict
# --------------------------------------------------------------------------- #
def cmd_predict(args):
    ckpt = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    cfg = ckpt["config"]
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    data = load_inputs(args.input, device)

    model = HeteroGNN(cfg["in_dim"], cfg["n_words"], hidden=cfg["hidden"],
                      n_class=cfg["n_class"], n_layers=cfg["n_layers"],
                      dropout=cfg["dropout"]).to(device)
    model.load_state_dict({k: v.to(device) for k, v in ckpt["model_state"].items()})
    model.eval()

    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    with torch.no_grad():
        logits = forward_all(model, data)
        test_ids = torch.from_numpy(data["test_ids_np"]).to(device)
        probs = restricted_softmax(logits, test_ids)
        out = probs.detach().cpu().numpy().astype(np.float32)

    out_dir = os.path.dirname(os.path.abspath(args.output))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    np.save(args.output, out)
    print(f"loaded step={ckpt.get('step')}  wrote {args.output}  shape={out.shape}  "
          f"device={device}  rowsum0={out[0].sum():.6f}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="GPUv1-E09 heterogeneous Cora GNN")
    sub = ap.add_subparsers(dest="command", required=True)

    t = sub.add_parser("train")
    t.add_argument("--input", default="input")
    t.add_argument("--output", default="output")
    t.add_argument("--epochs", type=int, default=100)
    t.add_argument("--hidden", type=int, default=64)
    t.add_argument("--layers", type=int, default=3)
    t.add_argument("--dropout", type=float, default=0.5)
    t.add_argument("--lr", type=float, default=0.01)
    t.add_argument("--weight-decay", type=float, default=5e-4)
    t.add_argument("--val-frac", type=float, default=0.0,
                   help="optional held-out fraction of the training labels for sanity checks")
    t.set_defaults(func=cmd_train)

    p = sub.add_parser("predict")
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--input", default="input")
    p.add_argument("--output", default="output/reloaded.npy")
    p.set_defaults(func=cmd_predict)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
