#!/usr/bin/env python3
"""GPUv1-A07 (debug variant).

Train a DLRM click-through-rate model on the provided genuine Criteo_x1 subset,
and deliver a reloadable checkpoint, validation probabilities, and a run report.

Commands
--------
train   --input DIR  --output DIR
predict --checkpoint PATH --input JSONL --output NPY
doctor  --input DIR

Hard requirements implemented here
---------------------------------
* CUDA is mandatory for all real work (train / predict). No CPU fallback.
* Category dictionaries are built from train rows only; unknown -> index 0.
* Numeric normalisation (mean/std) is fitted on train and saved.
* 26 independent 8-dim embedding tables + 1 dense 8-dim numeric projection,
  ALL pairwise dot interactions (351 pairs) -> top MLP -> logit.
* BCEWithLogitsLoss, real gradient updates, every train row updated at least once.
* Fixed seed; optimizer/RNG/step/preprocessor saved inside checkpoint.pt.
* Independent structural / parameter-change / coverage / finite-loss /
  reload-and-CUDA-backward checks; AUC reported by an independent implementation.
"""

import argparse
import hashlib
import json
import os
import sys
import time

import numpy as np

try:
    import torch
    import torch.nn as nn
    TORCH_IMPORT_ERROR = None
except Exception as _e:  # pragma: no cover
    torch = None
    nn = None
    TORCH_IMPORT_ERROR = "%s: %s" % (type(_e).__name__, _e)


EMB_DIM = 8
TOP_HIDDEN = (64, 32)
SEED = 1234
EPOCHS = 30
BATCH_SIZE = 125
LR = 1e-2
UNKNOWN_TOKEN = "<MISSING>"
LABEL_KEYS = ("label", "target", "click", "y", "Label")


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def read_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def require_cuda():
    if torch is None:
        print("ERROR: PyTorch is unavailable: %s" % TORCH_IMPORT_ERROR, file=sys.stderr)
        sys.exit(2)
    if not torch.cuda.is_available():
        print("ERROR: CUDA is required for this task but is not available.", file=sys.stderr)
        sys.exit(2)
    return torch.device("cuda")


# --------------------------------------------------------------------------
# schema handling
# --------------------------------------------------------------------------
def _extract_names(seq):
    out = []
    for it in seq:
        if isinstance(it, str):
            out.append(it)
        elif isinstance(it, dict):
            for k in ("name", "field", "column", "feature", "col"):
                if isinstance(it.get(k), str):
                    out.append(it[k])
                    break
    return out


def parse_schema(schema):
    """Return (numeric_names, categorical_names, label_name) from schema.json."""
    numeric = categorical = label = None
    if isinstance(schema, dict):
        for k in ("numeric_features", "numerical_features", "num_features",
                  "numeric_feature_names", "numeric_cols", "numerical"):
            v = schema.get(k)
            if isinstance(v, list) and v:
                n = _extract_names(v)
                if n:
                    numeric = n
                    break
        for k in ("categorical_features", "cat_features",
                  "categorical_feature_names", "categorical_cols", "categorical"):
            v = schema.get(k)
            if isinstance(v, list) and v:
                n = _extract_names(v)
                if n:
                    categorical = n
                    break
        for k in ("label", "target", "label_column", "label_name",
                  "target_name", "click"):
            if k in schema:
                v = schema[k]
                if isinstance(v, str):
                    label = v
                    break
                if isinstance(v, dict):
                    for kk in ("name", "field", "column"):
                        if isinstance(v.get(kk), str):
                            label = v[kk]
                            break
                    if label:
                        break
        if numeric is None or categorical is None:
            for key in ("columns", "fields", "features", "schema"):
                cols = schema.get(key)
                if not isinstance(cols, list):
                    continue
                nums, cats = [], []
                for c in cols:
                    if not isinstance(c, dict):
                        continue
                    name = c.get("name") or c.get("field") or c.get("column")
                    if not isinstance(name, str):
                        continue
                    typ = str(c.get("type") or c.get("dtype") or "").lower()
                    if c.get("is_label"):
                        label = name
                    if "cat" in typ or "str" in typ or "object" in typ:
                        cats.append(name)
                    elif "num" in typ or "float" in typ or "int" in typ or "double" in typ:
                        nums.append(name)
                if nums and cats:
                    numeric, categorical = nums, cats
                    break
    return numeric, categorical, label


def infer_schema(rows):
    """Fallback only: derive names from a sample row (Criteo I*/C* convention)."""
    sample = rows[0]
    numeric, categorical = [], []
    label = None
    for key, val in sample.items():
        if key in LABEL_KEYS:
            label = label or key
            continue
        if key.startswith("I") and key[1:].isdigit():
            numeric.append(key)
        elif key.startswith("C") and key[1:].isdigit():
            categorical.append(key)
    if not numeric or not categorical:
        numeric, categorical = [], []
        for key, val in sample.items():
            if key in LABEL_KEYS:
                continue
            if isinstance(val, str):
                categorical.append(key)
            elif isinstance(val, (int, float)) and not isinstance(val, bool):
                numeric.append(key)
    return numeric, categorical, label


def pick_label_name(rows, label_name):
    if label_name and label_name in rows[0]:
        return label_name
    for k in LABEL_KEYS:
        if k in rows[0]:
            return k
    return label_name


# --------------------------------------------------------------------------
# feature encoding
# --------------------------------------------------------------------------
def _num_value(row, name):
    v = row.get(name, None)
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _cat_token(row, name):
    v = row.get(name, None)
    return UNKNOWN_TOKEN if v is None else str(v)


def build_preprocessor(numeric_names, categorical_names, label_name, train_rows):
    num_raw = np.zeros((len(train_rows), len(numeric_names)), dtype=np.float64)
    for i, r in enumerate(train_rows):
        for j, n in enumerate(numeric_names):
            num_raw[i, j] = _num_value(r, n)
    mean = num_raw.mean(axis=0) if len(train_rows) else np.zeros(len(numeric_names))
    std = num_raw.std(axis=0) if len(train_rows) else np.ones(len(numeric_names))
    std = np.where(std < 1e-6, 1.0, std)

    category_maps = []
    for name in categorical_names:
        m = {}
        for r in train_rows:
            tok = _cat_token(r, name)
            if tok not in m:
                m[tok] = len(m) + 1  # 0 reserved for unknown
        category_maps.append(m)

    cat_vocab_sizes = [len(m) + 1 for m in category_maps]
    return {
        "numeric_features": list(numeric_names),
        "categorical_features": list(categorical_names),
        "label": label_name,
        "numeric_mean": [float(x) for x in mean],
        "numeric_std": [float(x) for x in std],
        "category_maps": category_maps,
        "cat_vocab_sizes": cat_vocab_sizes,
        "num_numeric": len(numeric_names),
        "num_categorical": len(categorical_names),
        "embedding_dim": EMB_DIM,
    }


def encode_rows(rows, pre):
    n = len(rows)
    num = np.zeros((n, pre["num_numeric"]), dtype=np.float32)
    cat = np.zeros((n, pre["num_categorical"]), dtype=np.int64)
    names_num = pre["numeric_features"]
    names_cat = pre["categorical_features"]
    maps = pre["category_maps"]
    mean = pre["numeric_mean"]
    std = pre["numeric_std"]
    for i, r in enumerate(rows):
        for j, name in enumerate(names_num):
            num[i, j] = (_num_value(r, name) - mean[j]) / std[j]
        for j, name in enumerate(names_cat):
            tok = _cat_token(r, name)
            cat[i, j] = maps[j].get(tok, 0)
    return num, cat


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------
if torch is not None:
    class DLRM(nn.Module):
        """Numeric bottom MLP -> 8d; per-field embeddings -> 8d; all pairwise dots."""

        def __init__(self, num_numeric, cat_vocab_sizes, emb_dim=EMB_DIM, top_hidden=TOP_HIDDEN):
            super().__init__()
            self.num_numeric = num_numeric
            self.cat_vocab_sizes = list(cat_vocab_sizes)
            self.emb_dim = emb_dim
            self.numeric_bottom = nn.Sequential(nn.Linear(num_numeric, emb_dim), nn.ReLU())
            self.embeddings = nn.ModuleList([nn.Embedding(v, emb_dim) for v in self.cat_vocab_sizes])
            n_vectors = 1 + len(self.cat_vocab_sizes)
            self.interaction_dim = n_vectors * (n_vectors - 1) // 2
            layers, prev = [], self.interaction_dim
            for h in top_hidden:
                layers += [nn.Linear(prev, h), nn.ReLU()]
                prev = h
            layers.append(nn.Linear(prev, 1))
            self.top = nn.Sequential(*layers)

        def forward(self, x_num, x_cat):
            dense = self.numeric_bottom(x_num).unsqueeze(1)
            embs = [emb(x_cat[:, i]) for i, emb in enumerate(self.embeddings)]
            stacked = torch.stack(embs, dim=1) if embs else None
            z = torch.cat([dense, stacked], dim=1) if stacked is not None else dense
            b, n, _d = z.shape
            iu = torch.triu_indices(n, n, offset=1, device=z.device)
            inter = (z[:, iu[0], :] * z[:, iu[1], :]).sum(dim=-1)
            return self.top(inter).squeeze(-1)


# --------------------------------------------------------------------------
# independent AUC (Mann-Whitney rank formulation, averaged ranks for ties)
# --------------------------------------------------------------------------
def roc_auc(y_true, y_score):
    y = np.asarray(y_true, dtype=np.float64)
    s = np.asarray(y_score, dtype=np.float64)
    if y.size == 0:
        return float("nan")
    order = np.argsort(s, kind="mergesort")
    s_sorted = s[order]
    y_sorted = y[order]
    ranks = np.arange(1, len(s) + 1, dtype=np.float64)
    i = 0
    while i < len(s_sorted):
        j = i
        while j + 1 < len(s_sorted) and s_sorted[j + 1] == s_sorted[i]:
            j += 1
        if j > i:
            ranks[i:j + 1] = ranks[i:j + 1].mean()
        i = j + 1
    n_pos = float(y_sorted.sum())
    n_neg = float(len(y_sorted) - n_pos)
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    return float((ranks[y_sorted == 1].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------
def cmd_doctor(args):
    missing = []
    notes = []
    input_dir = args.input
    required = ["train.jsonl", "validation.jsonl", "schema.json"]
    for f in required:
        p = os.path.join(input_dir, f)
        if os.path.isfile(p):
            notes.append("found %s (%d bytes)" % (p, os.path.getsize(p)))
        else:
            missing.append("input file missing: %s" % p)

    if torch is None:
        missing.append("python dependency unavailable: import torch -> %s" % TORCH_IMPORT_ERROR)
    else:
        notes.append("torch %s (cuda build %s)" % (torch.__version__, torch.version.cuda))
        if torch.cuda.is_available():
            notes.append("cuda available: %s" % torch.cuda.get_device_name(0))
        else:
            missing.append("CUDA device not available (required for real work)")
    notes.append("numpy %s" % np.__version__)

    manifest_path = os.path.join(input_dir, "manifest.json")
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            files = manifest.get("files", {}) if isinstance(manifest, dict) else {}
            for name, expected in files.items():
                p = os.path.join(input_dir, name)
                if not os.path.isfile(p):
                    missing.append("manifest file missing: %s" % p)
                    continue
                got = sha256_file(p)
                if got != expected:
                    missing.append("sha256 mismatch for %s (expected %s, got %s)" % (name, expected, got))
                else:
                    notes.append("sha256 ok: %s" % name)
        except Exception as e:
            missing.append("manifest.json unreadable: %s" % e)

    schema_path = os.path.join(input_dir, "schema.json")
    if os.path.isfile(schema_path):
        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                schema = json.load(f)
            nums, cats, label = parse_schema(schema)
            if not nums or not cats:
                missing.append("schema.json does not declare numeric/categorical feature lists")
            else:
                notes.append("schema: %d numeric, %d categorical, label=%s" % (len(nums), len(cats), label))
        except Exception as e:
            missing.append("schema.json unreadable: %s" % e)

    report = {"status": "missing" if missing else "ok", "missing": missing, "notes": notes}
    print(json.dumps(report, indent=2))
    return 78 if missing else 0


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------
def check_structure(model, expected_tables, expected_interaction):
    n_tables = len(model.embeddings)
    dims_ok = all(e.embedding_dim == EMB_DIM for e in model.embeddings)
    dev = next(model.parameters()).device
    dummy_num = torch.zeros(2, model.num_numeric, device=dev)
    dummy_cat = torch.zeros(2, n_tables, dtype=torch.long, device=dev)
    with torch.no_grad():
        out = model(dummy_num, dummy_cat)
    return {
        "num_embedding_tables": n_tables,
        "expected_embedding_tables": expected_tables,
        "all_embedding_dim_8": bool(dims_ok),
        "interaction_dim": int(model.interaction_dim),
        "expected_interaction_dim": expected_interaction,
        "forward_output_shape": list(out.shape),
        "pass": bool(n_tables == expected_tables and dims_ok
                     and model.interaction_dim == expected_interaction),
    }


def check_param_change(before_sd, model):
    after_sd = model.state_dict()
    total = changed = 0
    per_tensor = {}
    for k in after_sd:
        total += 1
        same = torch.equal(before_sd[k], after_sd[k])
        if not same:
            changed += 1
        per_tensor[k] = (not same)
    return {
        "total_tensors": total,
        "changed_tensors": changed,
        "numeric_bottom_changed": bool(per_tensor.get("numeric_bottom.0.weight", False)),
        "top_mlp_changed": bool(per_tensor.get("top.0.weight", False)),
        "first_embedding_changed": bool(per_tensor.get("embeddings.0.weight", False)),
        "pass": changed > 0,
    }


def check_reload_and_backward(ckpt_path, device):
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    pre = ckpt["preprocessor"]
    model = DLRM(pre["num_numeric"], pre["cat_vocab_sizes"])
    model.load_state_dict(ckpt["model_state_dict"])
    model.to(device).train()
    bs = 8
    x_num = torch.randn(bs, pre["num_numeric"], device=device)
    x_cat = torch.zeros(bs, pre["num_categorical"], dtype=torch.long, device=device)
    y = torch.randint(0, 2, (bs,), device=device).float()
    logits = model(x_num, x_cat)
    loss = nn.functional.binary_cross_entropy_with_logits(logits, y)
    loss.backward()
    grads_present = all(p.grad is not None for p in model.parameters() if p.requires_grad)
    nb_grad_norm = float(model.numeric_bottom[0].weight.grad.norm().item())
    return {
        "reload_ok": True,
        "backward_loss": float(loss.item()),
        "loss_finite": bool(torch.isfinite(loss).item()),
        "all_grads_present": bool(grads_present),
        "numeric_bottom_grad_norm": nb_grad_norm,
        "pass": bool(grads_present and torch.isfinite(loss).item()),
    }


# --------------------------------------------------------------------------
# train
# --------------------------------------------------------------------------
def cmd_train(args):
    t_start = time.perf_counter()
    device = require_cuda()

    input_dir = args.input
    output_dir = args.output
    train_path = os.path.join(input_dir, "train.jsonl")
    val_path = os.path.join(input_dir, "validation.jsonl")
    schema_path = os.path.join(input_dir, "schema.json")
    for p in (train_path, val_path, schema_path):
        if not os.path.isfile(p):
            print("ERROR: required input missing: %s" % p, file=sys.stderr)
            return 78

    torch.manual_seed(SEED)
    np.random.seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    train_rows = read_jsonl(train_path)
    val_rows = read_jsonl(val_path)
    if not train_rows:
        print("ERROR: train.jsonl is empty", file=sys.stderr)
        return 78

    numeric_names, categorical_names, label_name = parse_schema(schema)
    if not numeric_names or not categorical_names:
        numeric_names, categorical_names, label_name = infer_schema(train_rows)
    label_name = pick_label_name(train_rows, label_name)

    pre = build_preprocessor(numeric_names, categorical_names, label_name, train_rows)
    os.makedirs(output_dir, exist_ok=True)

    num_np, cat_np = encode_rows(train_rows, pre)
    labels = np.array([float(_num_value(r, label_name)) for r in train_rows], dtype=np.float32)

    num_t = torch.tensor(num_np, dtype=torch.float32, device=device)
    cat_t = torch.tensor(cat_np, dtype=torch.long, device=device)
    y_t = torch.tensor(labels, dtype=torch.float32, device=device)

    model = DLRM(pre["num_numeric"], pre["cat_vocab_sizes"]).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)
    criterion = nn.BCEWithLogitsLoss()

    before_sd = {k: v.detach().clone() for k, v in model.state_dict().items()}

    n_rows = len(train_rows)
    steps = 0
    losses = []
    covered = set()
    all_finite = True

    torch.cuda.synchronize()
    t_train = time.perf_counter()
    model.train()
    for _epoch in range(EPOCHS):
        perm = torch.randperm(n_rows, device=device)
        for start in range(0, n_rows, BATCH_SIZE):
            idx = perm[start:start + BATCH_SIZE]
            optimizer.zero_grad(set_to_none=True)
            logits = model(num_t[idx], cat_t[idx])
            loss = criterion(logits, y_t[idx])
            if not torch.isfinite(loss).item():
                all_finite = False
            loss.backward()
            optimizer.step()
            steps += 1
            losses.append(float(loss.item()))
            covered.update(idx.tolist())
    torch.cuda.synchronize()
    train_s = time.perf_counter() - t_train

    # ---- validation probabilities --------------------------------------
    val_num, val_cat = encode_rows(val_rows, pre)
    model.eval()
    with torch.no_grad():
        val_logits = model(
            torch.tensor(val_num, dtype=torch.float32, device=device),
            torch.tensor(val_cat, dtype=torch.long, device=device),
        )
        val_probs = torch.sigmoid(val_logits).detach().cpu().numpy().astype(np.float32)

    npy_path = os.path.join(output_dir, "validation_predictions.npy")
    np.save(npy_path, val_probs)

    # ---- train predictions (for the independent AUC report) -------------
    with torch.no_grad():
        train_probs = torch.sigmoid(model(num_t, cat_t)).detach().cpu().numpy().astype(np.float64)

    # ---- checkpoint ------------------------------------------------------
    rng = {
        "torch": torch.get_rng_state(),
        "numpy": np.random.get_state(),
        "cuda": torch.cuda.get_rng_state_all(),
    }
    ckpt_path = os.path.join(output_dir, "checkpoint.pt")
    checkpoint = {
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "step": steps,
        "epochs": EPOCHS,
        "seed": SEED,
        "rng": rng,
        "preprocessor": pre,
        "config": {
            "embedding_dim": EMB_DIM,
            "top_hidden": list(TOP_HIDDEN),
            "batch_size": BATCH_SIZE,
            "lr": LR,
            "loss": "BCEWithLogitsLoss",
            "optimizer": "Adam",
        },
        "torch_version": torch.__version__,
        "cuda_device": torch.cuda.get_device_name(0),
    }
    torch.save(checkpoint, ckpt_path)

    # ---- independent checks ---------------------------------------------
    n_vectors = 1 + pre["num_categorical"]
    expected_interaction = n_vectors * (n_vectors - 1) // 2
    checks = {}
    checks["structure"] = check_structure(model, pre["num_categorical"], expected_interaction)
    checks["parameter_change"] = check_param_change(before_sd, model)
    checks["input_coverage"] = {
        "train_rows": n_rows,
        "rows_updated": len(covered),
        "all_rows_updated": bool(len(covered) == n_rows),
        "pass": bool(len(covered) == n_rows),
    }
    checks["finite_bce"] = {
        "num_steps": steps,
        "all_losses_finite": bool(all_finite and all(np.isfinite(losses))),
        "first_loss": float(losses[0]) if losses else None,
        "final_loss": float(losses[-1]) if losses else None,
        "pass": bool(all_finite and all(np.isfinite(losses))),
    }
    torch.cuda.synchronize()
    checks["reload_cuda_backward"] = check_reload_and_backward(ckpt_path, device)
    checks["all_passed"] = bool(all(v.get("pass", False) for v in checks.values()
                                    if isinstance(v, dict)))

    # ---- independent AUC -------------------------------------------------
    train_auc = roc_auc(labels, train_probs)
    val_auc = None
    if val_rows and label_name and label_name in val_rows[0]:
        val_labels = np.array([float(_num_value(r, label_name)) for r in val_rows], dtype=np.float64)
        if len(np.unique(val_labels)) > 1:
            val_auc = roc_auc(val_labels, val_probs.astype(np.float64))

    wall_s = time.perf_counter() - t_start
    run = {
        "task_id": "GPUv1-A07",
        "scale": "debug_only",
        "formal_large_tested": False,
        "variant": "debug",
        "seed": SEED,
        "device": torch.cuda.get_device_name(0),
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "numpy_version": np.__version__,
        "config": checkpoint["config"],
        "data": {
            "train_rows": n_rows,
            "validation_rows": len(val_rows),
            "numeric_features": len(pre["numeric_features"]),
            "categorical_features": len(pre["categorical_features"]),
            "category_vocab_sizes": pre["cat_vocab_sizes"],
            "category_vocab_total": int(sum(pre["cat_vocab_sizes"])),
            "category_map_sha256": hashlib.sha256(
                json.dumps(pre["category_maps"], sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "numeric_mean": pre["numeric_mean"],
            "numeric_std": pre["numeric_std"],
            "label_field": label_name,
        },
        "training": {
            "epochs": EPOCHS,
            "steps": steps,
            "batch_size": BATCH_SIZE,
            "lr": LR,
            "mean_loss": float(np.mean(losses)) if losses else None,
            "final_loss": float(losses[-1]) if losses else None,
            "train_s": float(train_s),
        },
        "timing": {
            "wall_s": float(wall_s),
            "train_s": float(train_s),
            "cuda_synchronized": True,
        },
        "checks": checks,
        "auc": {
            "implementation": "independent Mann-Whitney rank AUC",
            "train": train_auc,
            "validation": val_auc,
            "quality_threshold_applied": False,
            "note": "AUC is reported for information only; no tiny-instance quality gate.",
        },
        "outputs": {
            "checkpoint": ckpt_path,
            "validation_predictions": npy_path,
            "validation_predictions_shape": list(val_probs.shape),
            "validation_predictions_finite": bool(np.all(np.isfinite(val_probs))),
            "validation_predictions_mean": float(val_probs.mean()) if val_probs.size else None,
            "validation_predictions_min": float(val_probs.min()) if val_probs.size else None,
            "validation_predictions_max": float(val_probs.max()) if val_probs.size else None,
        },
        "input_sha256": {
            "train.jsonl": sha256_file(train_path),
            "validation.jsonl": sha256_file(val_path),
            "schema.json": sha256_file(schema_path),
        },
        "status": "ok" if checks["all_passed"] else "checks_failed",
    }
    run_path = os.path.join(output_dir, "run.json")
    with open(run_path, "w", encoding="utf-8") as f:
        json.dump(run, f, indent=2)

    print(json.dumps({
        "status": run["status"],
        "steps": steps,
        "train_auc": train_auc,
        "validation_auc": val_auc,
        "validation_predictions": npy_path,
        "checkpoint": ckpt_path,
        "run_json": run_path,
        "wall_s": wall_s,
    }, indent=2))

    return 0 if run["status"] == "ok" else 1


# --------------------------------------------------------------------------
# predict
# --------------------------------------------------------------------------
def cmd_predict(args):
    device = require_cuda()
    if not os.path.isfile(args.checkpoint):
        print("ERROR: checkpoint not found: %s" % args.checkpoint, file=sys.stderr)
        return 78
    if not os.path.isfile(args.input):
        print("ERROR: input JSONL not found: %s" % args.input, file=sys.stderr)
        return 78

    ckpt = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    pre = ckpt["preprocessor"]
    model = DLRM(pre["num_numeric"], pre["cat_vocab_sizes"])
    model.load_state_dict(ckpt["model_state_dict"])
    model.to(device).eval()

    rows = read_jsonl(args.input)
    if not rows:
        print("ERROR: input JSONL is empty: %s" % args.input, file=sys.stderr)
        return 78

    num_np, cat_np = encode_rows(rows, pre)
    with torch.no_grad():
        logits = model(
            torch.tensor(num_np, dtype=torch.float32, device=device),
            torch.tensor(cat_np, dtype=torch.long, device=device),
        )
        probs = torch.sigmoid(logits).detach().cpu().numpy().astype(np.float32)

    out_dir = os.path.dirname(os.path.abspath(args.output))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    np.save(args.output, probs)
    print(json.dumps({
        "rows": len(rows),
        "probabilities_shape": list(probs.shape),
        "all_finite": bool(np.all(np.isfinite(probs))),
        "output": args.output,
    }, indent=2))
    return 0


# --------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="GPUv1-A07 debug: DLRM CTR training / prediction on a genuine Criteo_x1 subset.",
    )
    sub = parser.add_subparsers(dest="command")

    p_train = sub.add_parser("train", help="train the DLRM and write checkpoint/predictions/run.json")
    p_train.add_argument("--input", default="input", help="directory containing train.jsonl/validation.jsonl/schema.json")
    p_train.add_argument("--output", default="output", help="output directory")

    p_pred = sub.add_parser("predict", help="score a JSONL file with a saved checkpoint")
    p_pred.add_argument("--checkpoint", required=True)
    p_pred.add_argument("--input", required=True, help="newline-delimited JSON file")
    p_pred.add_argument("--output", required=True, help="output .npy path")

    p_doc = sub.add_parser("doctor", help="inspect inputs and dependencies without running training")
    p_doc.add_argument("--input", default="input")

    args = parser.parse_args(argv)
    if args.command == "train":
        return cmd_train(args)
    if args.command == "predict":
        return cmd_predict(args)
    if args.command == "doctor":
        return cmd_doctor(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
