"""GPUv1-E10: citation link-prediction with a CUDA GCN + link scorer.

Train a 2-layer (symmetric-normalized) GCN on the *training* citation graph
provided in input/edges.npy, together with a dot-product link scorer trained
with genuine negative sampling from the non-edges of that training graph.

query_pairs.npy is NEVER used for training: it is only read, in file order,
at scoring time.  Run:

    python solution/main.py train   --input input --output output
    python solution/main.py predict --checkpoint output/checkpoint.pt \
                                    --input input --output output/reloaded.npy
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from typing import Dict, List, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

TASK_ID = "GPUv1-E10"
SEED_DEFAULT = 2026


# --------------------------------------------------------------------------- #
# reproducibility
# --------------------------------------------------------------------------- #
def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    # dense matmul / linear kernels are deterministic; belt and braces:
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


# --------------------------------------------------------------------------- #
# data
# --------------------------------------------------------------------------- #
def load_inputs(input_dir: str):
    feats = np.load(os.path.join(input_dir, "features.npy")).astype(np.float32)
    edges = np.load(os.path.join(input_dir, "edges.npy")).astype(np.int64)
    queries = np.load(os.path.join(input_dir, "query_pairs.npy")).astype(np.int64)
    if feats.ndim != 2:
        raise ValueError("features.npy must be [N, F]")
    num_nodes = feats.shape[0]
    if edges.size:
        if edges.min() < 0 or edges.max() >= num_nodes:
            raise ValueError("edges out of range")
    if queries.size:
        if queries.min() < 0 or queries.max() >= num_nodes:
            raise ValueError("query pairs out of range")
    return feats, edges, queries, num_nodes


def build_norm_adj(edges: np.ndarray, num_nodes: int, device: torch.device) -> torch.Tensor:
    """Symmetric normalized adjacency D^-1/2 (A + I) D^-1/2.

    Citation links are treated as undirected for message passing: both
    directions of each training edge are added.  Only training edges are used.
    """
    A = np.zeros((num_nodes, num_nodes), dtype=np.float32)
    if edges.size:
        u = edges[:, 0]
        v = edges[:, 1]
        A[u, v] = 1.0
        A[v, u] = 1.0
    np.fill_diagonal(A, 1.0)  # self loops
    deg = A.sum(axis=1)
    dinv = 1.0 / np.sqrt(np.maximum(deg, 1e-12))
    A = A * dinv[:, None] * dinv[None, :]
    return torch.from_numpy(A).to(device)


def directed_edge_sets(edges: np.ndarray) -> List[set]:
    s = set()
    for u, v in edges.tolist():
        s.add((int(u), int(v)))
        s.add((int(v), int(u)))
    return s


# --------------------------------------------------------------------------- #
# negative sampling (non-edges of the training graph only)
# --------------------------------------------------------------------------- #
class NonEdgeSampler:
    def __init__(self, edges: np.ndarray, num_nodes: int, rng: np.random.Generator):
        self.n = num_nodes
        self.rng = rng
        self.edge_set = directed_edge_sets(edges)

    def sample(self, k: int) -> np.ndarray:
        out = np.empty((k, 2), dtype=np.int64)
        filled = 0
        while filled < k:
            need = k - filled
            u = self.rng.integers(0, self.n, size=need)
            v = self.rng.integers(0, self.n, size=need)
            ok = []
            for a, b in zip(u.tolist(), v.tolist()):
                if a != b and (a, b) not in self.edge_set:
                    ok.append((a, b))
            if ok:
                arr = np.asarray(ok, dtype=np.int64)
                m = min(len(arr), need)
                out[filled:filled + m] = arr[:m]
                filled += m
        return out


# --------------------------------------------------------------------------- #
# model
# --------------------------------------------------------------------------- #
class GCNEncoder(nn.Module):
    """Symmetric-normalized GCN aggregator running on CUDA."""

    def __init__(self, in_dim: int, hidden_dim: int, out_dim: int,
                 dropout: float = 0.3, num_layers: int = 2):
        super().__init__()
        dims = [in_dim] + [hidden_dim] * (num_layers - 1) + [out_dim]
        self.layers = nn.ModuleList(
            [nn.Linear(dims[i], dims[i + 1]) for i in range(len(dims) - 1)]
        )
        self.dropout = dropout

    def forward(self, x: torch.Tensor, adj: torch.Tensor) -> torch.Tensor:
        h = x
        last = len(self.layers) - 1
        for i, lin in enumerate(self.layers):
            h = adj @ h              # GPU neighbourhood aggregation
            h = lin(h)
            if i != last:
                h = F.relu(h)
                h = F.dropout(h, p=self.dropout, training=self.training)
        return h


class LinkScorer(nn.Module):
    """Bilinear-style dot-product scorer with learnable temperature/bias."""

    def __init__(self, init_scale: float = 5.0):
        super().__init__()
        self.log_scale = nn.Parameter(torch.tensor(float(np.log(init_scale)), dtype=torch.float32))
        self.bias = nn.Parameter(torch.zeros(1, dtype=torch.float32))

    def logits(self, z: torch.Tensor, pairs: torch.Tensor) -> torch.Tensor:
        hu = z[pairs[:, 0]]
        hv = z[pairs[:, 1]]
        dot = (hu * hv).sum(dim=-1)
        return torch.exp(self.log_scale) * dot + self.bias

    def forward(self, z: torch.Tensor, pairs: torch.Tensor) -> torch.Tensor:
        return torch.sigmoid(self.logits(z, pairs))


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def roc_auc(labels: np.ndarray, scores: np.ndarray) -> float:
    labels = np.asarray(labels, dtype=np.float64)
    scores = np.asarray(scores, dtype=np.float64)
    pos = labels > 0.5
    n_pos, n_neg = int(pos.sum()), int((~pos).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    order = np.argsort(scores, kind="mergesort")
    ranks = np.empty(len(scores), dtype=np.float64)
    ranks[order] = np.arange(1, len(scores) + 1, dtype=np.float64)
    # average ranks for ties
    s_sorted = scores[order]
    i = 0
    while i < len(s_sorted):
        j = i
        while j + 1 < len(s_sorted) and s_sorted[j + 1] == s_sorted[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + 1 + j + 1) / 2.0
        i = j + 1
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


# --------------------------------------------------------------------------- #
# training
# --------------------------------------------------------------------------- #
def train_model(feats: np.ndarray, edges: np.ndarray, num_nodes: int,
                cfg: Dict, device: torch.device, log_prefix: str = ""):
    """Train GCN + scorer on the supplied training edges. Returns (model, scorer, log)."""
    rng = np.random.default_rng(cfg["seed"])
    x = torch.from_numpy(feats).to(device)
    adj = build_norm_adj(edges, num_nodes, device)

    model = GCNEncoder(feats.shape[1], cfg["hidden_dim"], cfg["out_dim"],
                       dropout=cfg["dropout"], num_layers=cfg["num_layers"]).to(device)
    scorer = LinkScorer(cfg["init_scale"]).to(device)
    params = list(model.parameters()) + list(scorer.parameters())
    opt = torch.optim.Adam(params, lr=cfg["lr"], weight_decay=cfg["weight_decay"])
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(
        opt, T_max=cfg["steps"], eta_min=cfg["lr"] * 0.05
    )
    loss_fn = nn.BCEWithLogitsLoss()

    sampler = NonEdgeSampler(edges, num_nodes, rng)
    pos_all = np.concatenate([edges, edges[:, ::-1]], axis=0) if edges.size else edges
    n_pos = max(len(pos_all), 1)

    init_snapshot = [p.detach().clone() for p in params]
    log = {"losses": [], "steps": cfg["steps"], "first_grad_norm": None}
    t0 = time.time()
    for step in range(cfg["steps"]):
        model.train()
        scorer.train()
        idx = rng.integers(0, n_pos, size=cfg["batch_pos"])
        pos = pos_all[idx]
        neg = sampler.sample(cfg["batch_neg"])
        pairs = torch.from_numpy(np.concatenate([pos, neg], axis=0)).to(device)
        labels = torch.cat([
            torch.ones(len(pos), dtype=torch.float32, device=device),
            torch.zeros(len(neg), dtype=torch.float32, device=device),
        ])

        z = model(x, adj)                     # GPU aggregation
        logits = scorer.logits(z, pairs)      # GPU scoring
        loss = loss_fn(logits, labels)
        opt.zero_grad(set_to_none=True)
        loss.backward()                       # real backprop
        if step == 0:
            gn = torch.sqrt(sum((p.grad.detach() ** 2).sum()
                                for p in params if p.grad is not None))
            log["first_grad_norm"] = float(gn.detach().cpu())
        opt.step()                            # real parameter update
        sched.step()
        log["losses"].append(float(loss.detach().cpu()))
        if step % max(1, cfg["steps"] // 10) == 0 or step == cfg["steps"] - 1:
            print(f"{log_prefix}step {step:4d}  loss {loss.item():.4f}", flush=True)
    log["train_seconds"] = time.time() - t0
    log["final_loss"] = log["losses"][-1] if log["losses"] else float("nan")
    with torch.no_grad():
        delta = sum(float(((p.detach() - q) ** 2).sum().cpu())
                    for p, q in zip(params, init_snapshot)) ** 0.5
    log["param_delta_l2"] = delta
    opt_steps = [int(v["step"].item()) for v in opt.state_dict()["state"].values()
                 if hasattr(v, "get") and "step" in v and torch.is_tensor(v["step"])]
    log["optimizer_step_min"] = int(min(opt_steps)) if opt_steps else 0
    log["optimizer_step_max"] = int(max(opt_steps)) if opt_steps else 0
    if torch.cuda.is_available():
        log["cuda_peak_memory_bytes"] = int(torch.cuda.max_memory_allocated())
    return model, scorer, opt, log


@torch.no_grad()
def score_pairs(model: GCNEncoder, scorer: LinkScorer, feats: np.ndarray,
                edges: np.ndarray, queries: np.ndarray, num_nodes: int,
                device: torch.device) -> np.ndarray:
    model.eval()
    scorer.eval()
    x = torch.from_numpy(feats).to(device)
    adj = build_norm_adj(edges, num_nodes, device)
    z = model(x, adj)
    if len(queries) == 0:
        return np.zeros((0,), dtype=np.float64)
    q = torch.from_numpy(np.ascontiguousarray(queries)).to(device)
    probs = scorer(z, q)
    return probs.detach().cpu().numpy().astype(np.float64)


def train_cfg(seed: int) -> Dict:
    return {
        "hidden_dim": 256,
        "out_dim": 128,
        "dropout": 0.3,
        "num_layers": 2,
        "lr": 0.01,
        "weight_decay": 5e-4,
        "steps": 400,
        "batch_pos": 1024,
        "batch_neg": 1024,
        "init_scale": 5.0,
        "seed": seed,
        "normalize_embeddings": False,
    }


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def cmd_train(args) -> None:
    os.makedirs(args.output, exist_ok=True)
    seed = args.seed
    set_seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    feats, edges, queries, num_nodes = load_inputs(args.input)
    print(f"device={device} nodes={num_nodes} feat_dim={feats.shape[1]} "
          f"train_edges={len(edges)} query_pairs={len(queries)}", flush=True)

    # ---- honest internal validation: hold out 10% of TRAIN edges ----------
    rng = np.random.default_rng(seed + 1)
    perm = rng.permutation(len(edges))
    n_val = max(1, int(0.10 * len(edges)))
    val_idx, fit_idx = perm[:n_val], perm[n_val:]
    fit_edges = edges[fit_idx]
    val_edges = edges[val_idx]

    cfg = train_cfg(seed)
    vcfg = dict(cfg, steps=min(cfg["steps"], 250))
    vmodel, vscorer, _vopt, vlog = train_model(
        feats, fit_edges, num_nodes, vcfg, device, log_prefix="[val] ")
    # probe positives vs non-edges of the fit graph (never the query set)
    val_sampler = NonEdgeSampler(np.concatenate([fit_edges, val_edges], axis=0),
                                 num_nodes, rng)
    val_probe_pos = np.concatenate([val_edges, val_edges[:, ::-1]], axis=0)
    val_neg = val_sampler.sample(len(val_probe_pos))
    val_pairs = np.concatenate([val_probe_pos, val_neg], axis=0)
    val_scores = score_pairs(vmodel, vscorer, feats, fit_edges, val_pairs,
                             num_nodes, device)
    val_labels = np.concatenate([np.ones(len(val_probe_pos)),
                                 np.zeros(len(val_neg))])
    val_auc = roc_auc(val_labels, val_scores)
    print(f"[val] held-out-edge AUC = {val_auc:.4f}", flush=True)

    # ---- final model on ALL supplied training edges -----------------------
    set_seed(seed)
    model, scorer, opt, log = train_model(feats, edges, num_nodes, cfg, device,
                                          log_prefix="[train] ")
    scores = score_pairs(model, scorer, feats, edges, queries, num_nodes, device)

    if len(scores) != len(queries):
        raise RuntimeError("score/query length mismatch")
    if not np.all(np.isfinite(scores)):
        raise RuntimeError("non-finite probabilities produced")
    if scores.size and (scores.min() < 0.0 or scores.max() > 1.0):
        raise RuntimeError("probabilities outside [0,1]")

    # real optimizer state captured directly from the training optimizer
    opt_state = {k: v for k, v in opt.state_dict().items()}
    ckpt = {
        "task_id": TASK_ID,
        "model_state_dict": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()},
        "scorer_state_dict": {k: v.detach().cpu().clone() for k, v in scorer.state_dict().items()},
        "state_dict": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()},
        "model_config": {k: cfg[k] for k in
                         ("hidden_dim", "out_dim", "dropout", "num_layers")},
        "in_dim": int(feats.shape[1]),
        "num_nodes": int(num_nodes),
        "config": cfg,
        "optimizer_state_dict": opt_state,
        "optimizer": opt_state,
        "step": int(cfg["steps"]),
        "seed": int(seed),
        "initial_scale": float(cfg["init_scale"]),
        "losses": log["losses"][-20:],
        "val_auc_internal": float(val_auc),
    }

    ckpt_path = os.path.join(args.output, "checkpoint.pt")
    torch.save(ckpt, ckpt_path)
    scores_path = os.path.join(args.output, "query_scores.npy")
    np.save(scores_path, scores.astype(np.float64))

    # verify reload determinism (same process, exact path used by evaluator)
    reloaded = _load_checkpoint(ckpt_path, device)
    r_scores = score_pairs(reloaded["model"], reloaded["scorer"], feats, edges,
                           queries, num_nodes, device)
    reload_diff = float(np.max(np.abs(r_scores - scores))) if scores.size else 0.0

    run = {
        "task_id": TASK_ID,
        "mode": "train",
        "dataset": "Cora held-out real citation edges + genuine nonedge candidates",
        "device": str(device),
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "seed": int(seed),
        "torch_version": torch.__version__,
        "num_nodes": int(num_nodes),
        "feature_dim": int(feats.shape[1]),
        "train_edges": int(len(edges)),
        "query_pairs": int(len(queries)),
        "query_pairs_used_for_training": False,
        "negative_sampling": "uniform non-edges of training graph (directed pairs)",
        "steps": int(cfg["steps"]),
        "optimizer": "Adam",
        "model": "2-layer symmetric-normalized GCN + dot-product link scorer",
        "config": cfg,
        "final_loss": float(log["final_loss"]),
        "first_step_grad_norm": log["first_grad_norm"],
        "param_delta_l2": float(log["param_delta_l2"]),
        "optimizer_step_min": log["optimizer_step_min"],
        "optimizer_step_max": log["optimizer_step_max"],
        "cuda_peak_memory_bytes": log.get("cuda_peak_memory_bytes"),
        "training_graph_source": "input/edges.npy only",
        "train_seconds": float(log["train_seconds"]),
        "internal_val_holdout_edge_auc": float(val_auc),
        "query_score_min": float(scores.min()) if scores.size else None,
        "query_score_max": float(scores.max()) if scores.size else None,
        "query_score_mean": float(scores.mean()) if scores.size else None,
        "query_score_std": float(scores.std()) if scores.size else None,
        "query_scores_finite": bool(np.all(np.isfinite(scores))),
        "reload_max_abs_diff": reload_diff,
        "artifacts": {
            "checkpoint": "checkpoint.pt",
            "query_scores": "query_scores.npy",
            "run": "run.json",
        },
    }
    with open(os.path.join(args.output, "run.json"), "w") as f:
        json.dump(run, f, indent=2)
    print(json.dumps({k: run[k] for k in
                      ("steps", "final_loss", "first_step_grad_norm", "param_delta_l2",
                       "optimizer_step_max", "internal_val_holdout_edge_auc",
                       "query_score_mean", "reload_max_abs_diff")}, indent=2))
    print(f"saved {ckpt_path}, {scores_path}, run.json")


def _load_checkpoint(path: str, device: torch.device):
    try:
        ckpt = torch.load(path, map_location="cpu", weights_only=False)
    except TypeError:
        ckpt = torch.load(path, map_location="cpu")
    mc = ckpt["model_config"]
    model = GCNEncoder(ckpt["in_dim"], mc["hidden_dim"], mc["out_dim"],
                       dropout=mc["dropout"], num_layers=mc["num_layers"])
    model.load_state_dict(ckpt["model_state_dict"])
    scorer = LinkScorer(ckpt.get("initial_scale", 5.0))
    scorer.load_state_dict(ckpt["scorer_state_dict"])
    model.to(device).eval()
    scorer.to(device).eval()
    return {"model": model, "scorer": scorer, "ckpt": ckpt}


def cmd_predict(args) -> None:
    out_is_dir = args.output.endswith(os.sep) or os.path.isdir(args.output)
    if args.output.endswith(".npy"):
        out_path = args.output
    else:
        os.makedirs(args.output, exist_ok=True)
        out_path = os.path.join(args.output, "reloaded.npy")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ckpt = _load_checkpoint(args.checkpoint, device)
    set_seed(int(ckpt["ckpt"].get("seed", SEED_DEFAULT)))
    feats, edges, queries, num_nodes = load_inputs(args.input)
    if num_nodes != ckpt["ckpt"]["num_nodes"]:
        raise ValueError("checkpoint node count does not match input features")
    scores = score_pairs(ckpt["model"], ckpt["scorer"], feats, edges, queries,
                         num_nodes, device)
    if not np.all(np.isfinite(scores)):
        raise RuntimeError("non-finite probabilities")
    np.save(out_path, scores.astype(np.float64))
    print(f"wrote {out_path}  shape={scores.shape}  "
          f"min={scores.min():.6f} max={scores.max():.6f}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="GPUv1-E10 citation link prediction")
    sub = p.add_subparsers(dest="cmd", required=True)
    tr = sub.add_parser("train")
    tr.add_argument("--input", required=True)
    tr.add_argument("--output", required=True)
    tr.add_argument("--seed", type=int, default=SEED_DEFAULT)
    pr = sub.add_parser("predict")
    pr.add_argument("--checkpoint", required=True)
    pr.add_argument("--input", required=True)
    pr.add_argument("--output", required=True)
    return p


def main() -> None:
    args = build_parser().parse_args()
    if args.cmd == "train":
        cmd_train(args)
    elif args.cmd == "predict":
        cmd_predict(args)
    else:  # pragma: no cover
        raise SystemExit(f"unknown command {args.cmd}")


if __name__ == "__main__":
    main()
