#!/usr/bin/env python3
"""GPUv1-E02 (debug variant): reusable Criteo_x1 recommendation feature pipeline.

Subcommands
-----------
  fit        --input INPUT_DIR  --output OUTPUT_DIR
  transform  --preprocessor PREPROCESSOR.json --input JSONL --output NPY
  doctor     --input INPUT_DIR

Algorithm (matches the frozen task specification)
-------------------------------------------------
* schema.json gives `dense_columns` (13 numerics, e.g. I1..I13),
  `categorical_columns` (26 categoricals, e.g. C1..C26) and `label_column`.
* 13 numerical columns: a missing value is filled with 0, then standardized
  with the training mean and training population standard deviation
  (ddof=0; a zero std is replaced by 1).
* 26 categorical columns: the distinct string values seen in the training
  set are sorted lexicographically and assigned integer ids starting at 1.
  A missing value or an unseen value maps to id 0.
* Numeric statistics, standardization and the final feature-tensor assembly
  run on CUDA. Category dictionaries are built on the CPU.
* The feature tensor is float32 of shape (rows, 39) = [13 standardized
  numerics | 26 category ids].
* The fitted preprocessor is persisted as preprocessor.json and can be
  reloaded by `transform` for new JSONL data.
* validation_labels.npy is written ONLY when the input validation rows
  actually carry labels; unknown labels are never fabricated.
"""

import argparse
import json
import os
import re
import sys
import time

import numpy as np


# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #

def natural_key(s):
    """Sort key so that I2 < I10 and C3 < C20."""
    m = re.search(r'(\d+)$', s)
    if m:
        return (s[:m.start()], int(m.group(1)))
    return (s, 0)


def read_jsonl(path):
    rows = []
    with open(path, 'r', encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _f(x):
    """Finite float or 0.0."""
    if x != x or x in (float('inf'), float('-inf')):
        return 0.0
    return x


def to_float(v):
    """Numerical value; missing / unparseable / null -> 0.0."""
    if v is None:
        return 0.0
    if isinstance(v, bool):
        return float(int(v))
    if isinstance(v, (int, float)):
        return _f(float(v))
    s = str(v).strip()
    if s == "":
        return 0.0
    try:
        return _f(float(s))
    except ValueError:
        return 0.0


def to_cat_str(v):
    """Categorical value as string; null / empty -> None (missing)."""
    if v is None:
        return None
    if isinstance(v, bool):
        return str(int(v))
    s = str(v)
    if s == "":
        return None
    return s


def to_label(v):
    """Binary label; null -> 0."""
    if v is None:
        return 0
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip()
    if s == "":
        return 0
    try:
        return int(float(s))
    except ValueError:
        return 0


NUM_TYPES = {"num", "numerical", "numeric", "float", "float32", "float64",
             "double", "dense", "continuous", "int", "integer", "number"}
CAT_TYPES = {"cat", "categorical", "category", "string", "str", "sparse",
             "object", "text", "token"}
LABEL_KEYS = ("label", "Label", "target", "y", "label_column", "label_col",
              "target_column", "target_col")

# exact key names that the evaluator's schema.json uses
NUM_LIST_KEYS = (
    "dense_columns", "dense_features", "numerical", "numerical_features",
    "num_features", "numeric_features", "numeric_columns", "num_cols",
    "numeric_cols", "num_fields", "continuous", "continuous_features", "dense",
)
CAT_LIST_KEYS = (
    "categorical_columns", "categorical_features", "cat_features",
    "categorical", "cat_columns", "cat_cols", "categorical_cols",
    "cat_fields", "sparse", "sparse_features",
)
LABEL_KEY_KEYS = (
    "label_column", "label_col", "label_field", "label", "target_column",
    "target_col", "target_field", "target",
)


def _name_of(x):
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        for k in ("name", "field", "column", "key", "col"):
            if k in x and isinstance(x[k], str):
                return x[k]
    return None


# --------------------------------------------------------------------------- #
# schema handling                                                              #
# --------------------------------------------------------------------------- #

def infer_schema(schema):
    """Return (numerical, categorical, label_field) from schema.json."""
    numerical, categorical = [], []
    label = [None]

    def add_num(name):
        n = _name_of(name)
        if n is None:
            return
        n = str(n)
        if n not in numerical:
            numerical.append(n)

    def add_cat(name):
        n = _name_of(name)
        if n is None:
            return
        n = str(n)
        if n not in categorical:
            categorical.append(n)

    def classify(name, typ=None):
        if name is None:
            return
        n = str(name)
        t = str(typ).lower() if typ is not None else ""
        if n.lower() in ("label", "target", "y"):
            label[0] = n
            return
        if t in NUM_TYPES:
            add_num(n)
            return
        if t in CAT_TYPES:
            add_cat(n)
            return
        if re.fullmatch(r'[Ii]\d+', n):
            add_num(n)
        elif re.fullmatch(r'[Cc]\d+', n):
            add_cat(n)

    if isinstance(schema, dict):
        # Authoritative list keys (case-insensitive lookup).
        lower = {str(k).lower(): k for k in schema.keys()}

        for key in NUM_LIST_KEYS:
            k = lower.get(key.lower()) if key.lower() not in schema else key
            if k is None:
                continue
            v = schema.get(k)
            if isinstance(v, list):
                for x in v:
                    add_num(x)
        for key in CAT_LIST_KEYS:
            k = lower.get(key.lower()) if key.lower() not in schema else key
            if k is None:
                continue
            v = schema.get(k)
            if isinstance(v, list):
                for x in v:
                    add_cat(x)
        for key in LABEL_KEY_KEYS:
            k = lower.get(key.lower()) if key.lower() not in schema else key
            if k is None:
                continue
            v = schema.get(k)
            if isinstance(v, str) and v:
                label[0] = v
                break

        # If still nothing, scan values / nested dicts.
        if not numerical and not categorical:
            for k, v in schema.items():
                if isinstance(v, dict):
                    classify(k, v.get('type') or v.get('dtype') or v.get('kind'))
                elif isinstance(v, str):
                    # only classify as feature if key itself looks like one
                    if re.fullmatch(r'[Ii]\d+', k) or re.fullmatch(r'[Cc]\d+', k):
                        classify(k, v)
    elif isinstance(schema, list):
        for item in schema:
            if isinstance(item, str):
                classify(item, None)
            elif isinstance(item, dict):
                classify(_name_of(item),
                         item.get('type') or item.get('dtype') or item.get('kind'))

    numerical = sorted(set(numerical), key=natural_key)
    categorical = sorted(set(categorical), key=natural_key)
    return numerical, categorical, (label[0] or "label")


def infer_from_rows(rows, keys):
    """Fallback detection if schema.json does not fully describe the fields."""
    numerical, categorical = [], []
    for k in keys:
        is_str = is_num = False
        for row in rows[:64]:
            if not isinstance(row, dict) or k not in row:
                continue
            v = row[k]
            if v is None:
                continue
            if isinstance(v, str):
                is_str = True
            elif isinstance(v, (int, float)) or isinstance(v, bool):
                is_num = True
        if is_str and not is_num:
            categorical.append(k)
        elif is_num:
            numerical.append(k)
        elif re.fullmatch(r'[Ii]\d+', k):
            numerical.append(k)
        elif re.fullmatch(r'[Cc]\d+', k):
            categorical.append(k)
    return numerical, categorical


# --------------------------------------------------------------------------- #
# row extraction                                                               #
# --------------------------------------------------------------------------- #

def normalize_row(row, order, label):
    """Return (field_dict, raw_label) for a flat dict, features-list or list row."""
    if isinstance(row, dict):
        feats = row.get("features")
        if isinstance(feats, list):
            d = {}
            for i, name in enumerate(order):
                d[name] = feats[i] if i < len(feats) else None
            y = None
            for lk in (label,) + LABEL_KEYS:
                if lk in row:
                    y = row[lk]
                    break
            return d, y
        y = None
        for lk in (label,) + LABEL_KEYS:
            if lk in row:
                y = row[lk]
                break
        return row, y
    if isinstance(row, list):
        d = {}
        for i, name in enumerate(order):
            d[name] = row[i] if i < len(row) else None
        y = row[len(order)] if len(row) > len(order) else None
        return d, y
    return {}, None


def has_label(rows, label):
    """True if at least one row carries a non-null label value."""
    for row in rows[:256]:
        if not isinstance(row, dict):
            continue
        for lk in (label,) + LABEL_KEYS:
            if lk in row and row[lk] is not None:
                return True
    return False


def extract(rows, numerical, categorical, label, order):
    nums, cats, labs = [], [], []
    for row in rows:
        d, y = normalize_row(row, order, label)
        if y is None:
            y = d.get(label)
        nums.append([to_float(d.get(c)) for c in numerical])
        cats.append([to_cat_str(d.get(c)) for c in categorical])
        labs.append(to_label(y))
    return nums, cats, labs


def build_cat_tensor(cats, categorical, cat_dicts, device, torch):
    arr = np.zeros((len(cats), len(categorical)), dtype=np.float32)
    for j, col in enumerate(categorical):
        dd = cat_dicts.get(col, {})
        for i, crow in enumerate(cats):
            v = crow[j]
            if v is not None:
                arr[i, j] = dd.get(v, 0)
    return torch.tensor(arr, device=device)


def _require_cuda(torch):
    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA is required for this task but torch.cuda.is_available() is False")


# --------------------------------------------------------------------------- #
# fit                                                                          #
# --------------------------------------------------------------------------- #

def fit(args):
    import torch

    timings = {}
    t_start = time.time()

    in_dir = args.input
    out_dir = args.output
    os.makedirs(out_dir, exist_ok=True)

    # ---- read inputs -------------------------------------------------------
    t = time.time()
    with open(os.path.join(in_dir, "schema.json"), "r", encoding="utf-8") as fh:
        schema = json.load(fh)
    numerical, categorical, label = infer_schema(schema)
    train_rows = read_jsonl(os.path.join(in_dir, "train.jsonl"))
    val_rows = read_jsonl(os.path.join(in_dir, "validation.jsonl"))
    timings["read_input_seconds"] = time.time() - t

    # ---- reconcile field names against the actual rows ---------------------
    sample = train_rows[0] if train_rows else None
    if isinstance(sample, dict) and not isinstance(sample.get("features"), list):
        keys = set(sample.keys())
        label_like = {str(label).lower()} | {k.lower() for k in LABEL_KEYS}
        if not (set(numerical) <= keys and set(categorical) <= keys):
            cand = sorted([k for k in sample.keys() if k.lower() not in label_like],
                          key=natural_key)
            numerical, categorical = infer_from_rows(train_rows, cand)
    order = list(numerical) + list(categorical)
    if len(order) == 0:
        raise RuntimeError("Could not determine any feature columns from schema / rows")

    # ---- CUDA is mandatory -------------------------------------------------
    _require_cuda(torch)
    device = torch.device("cuda", 0)
    torch.cuda.synchronize()

    # ---- parse rows into python lists -------------------------------------
    t = time.time()
    tr_nums, tr_cats, tr_labels = extract(train_rows, numerical, categorical, label, order)
    va_nums, va_cats, va_labels = extract(val_rows, numerical, categorical, label, order)
    val_has_labels = has_label(val_rows, label)
    timings["extract_seconds"] = time.time() - t

    # ---- category dictionaries (CPU) --------------------------------------
    t = time.time()
    cat_dicts = {}
    for j, col in enumerate(categorical):
        vals = set()
        for crow in tr_cats:
            v = crow[j]
            if v is not None:
                vals.add(v)
        cat_dicts[col] = {v: i + 1 for i, v in enumerate(sorted(vals))}
    timings["category_dict_seconds"] = time.time() - t

    # ---- numerical statistics on CUDA -------------------------------------
    t = time.time()
    torch.cuda.synchronize()
    n_num = len(numerical)
    if n_num > 0:
        tr_num_t = torch.tensor(tr_nums, dtype=torch.float32, device=device)
        mean = tr_num_t.mean(dim=0)
        std = tr_num_t.std(dim=0, unbiased=False)
        std = torch.where(std == 0, torch.ones_like(std), std)
        tr_num_std = (tr_num_t - mean) / std
        torch.cuda.synchronize()
        mean_list = mean.detach().cpu().tolist()
        std_list = std.detach().cpu().tolist()
    else:
        tr_num_t = torch.zeros((len(tr_nums), 0), dtype=torch.float32, device=device)
        tr_num_std = tr_num_t
        mean_list, std_list = [], []
    torch.cuda.synchronize()
    timings["numeric_stats_standardize_gpu_seconds"] = time.time() - t

    # ---- assemble feature tensors on CUDA ---------------------------------
    t = time.time()
    torch.cuda.synchronize()
    tr_cat_t = build_cat_tensor(tr_cats, categorical, cat_dicts, device, torch)
    va_cat_t = build_cat_tensor(va_cats, categorical, cat_dicts, device, torch)

    if n_num > 0:
        m = torch.tensor(mean_list, dtype=torch.float32, device=device)
        s = torch.tensor(std_list, dtype=torch.float32, device=device)
        va_num_t = torch.tensor(va_nums, dtype=torch.float32, device=device)
        va_num_std = (va_num_t - m) / s
    else:
        va_num_std = torch.zeros((len(va_nums), 0), dtype=torch.float32, device=device)

    tr_X = torch.cat([tr_num_std, tr_cat_t], dim=1)
    va_X = torch.cat([va_num_std, va_cat_t], dim=1)
    torch.cuda.synchronize()
    timings["assemble_feature_tensor_gpu_seconds"] = time.time() - t

    # ---- move to host and persist -----------------------------------------
    t = time.time()
    tr_X_cpu = tr_X.detach().to("cpu").numpy().astype(np.float32, copy=False)
    va_X_cpu = va_X.detach().to("cpu").numpy().astype(np.float32, copy=False)
    tr_y = np.asarray(tr_labels, dtype=np.int64)

    tr_path = os.path.join(out_dir, "train_features.npy")
    va_path = os.path.join(out_dir, "validation_features.npy")
    ty_path = os.path.join(out_dir, "train_labels.npy")
    vy_path = os.path.join(out_dir, "validation_labels.npy")
    np.save(tr_path, tr_X_cpu)
    np.save(va_path, va_X_cpu)
    np.save(ty_path, tr_y)

    # validation labels are written ONLY if the input rows actually carry them
    if val_has_labels and len(va_labels) > 0:
        va_y = np.asarray(va_labels, dtype=np.int64)
        np.save(vy_path, va_y)
    else:
        if os.path.exists(vy_path):
            os.remove(vy_path)
        va_y = None

    preproc = {
        "version": 1,
        "task_id": "GPUv1-E02",
        "numerical": list(numerical),
        "categorical": list(categorical),
        "label": label,
        "feature_order": order,
        "num_mean": mean_list,
        "num_std": std_list,
        "category_dicts": {c: dict(cat_dicts[c]) for c in categorical},
        "n_numerical": len(numerical),
        "n_categorical": len(categorical),
        "total_features": len(order),
        "missing_numeric_fill": 0.0,
        "std_zero_replacement": 1.0,
        "category_id_start": 1,
        "unknown_category_id": 0,
    }
    pp_path = os.path.join(out_dir, "preprocessor.json")
    with open(pp_path, "w", encoding="utf-8") as fh:
        json.dump(preproc, fh, indent=2, sort_keys=True)

    timings["save_seconds"] = time.time() - t

    outputs = {}
    written = [pp_path, tr_path, va_path, ty_path]
    if va_y is not None:
        written.append(vy_path)
    for p in written:
        outputs[os.path.basename(p)] = {
            "path": os.path.abspath(p),
            "bytes": os.path.getsize(p),
        }
    outputs["train_features.npy"]["shape"] = list(tr_X_cpu.shape)
    outputs["validation_features.npy"]["shape"] = list(va_X_cpu.shape)
    outputs["train_labels.npy"]["shape"] = list(tr_y.shape)
    if va_y is not None:
        outputs["validation_labels.npy"]["shape"] = list(va_y.shape)

    timings["total_seconds"] = time.time() - t_start

    run = {
        "task_id": "GPUv1-E02",
        "variant": "debug",
        "command": "fit",
        "input_dir": os.path.abspath(in_dir),
        "output_dir": os.path.abspath(out_dir),
        "torch_version": torch.__version__,
        "cuda_available": True,
        "cuda_version": torch.version.cuda,
        "device_name": torch.cuda.get_device_name(0),
        "n_train_rows": len(train_rows),
        "n_validation_rows": len(val_rows),
        "n_numerical": len(numerical),
        "n_categorical": len(categorical),
        "n_features": len(order),
        "label_field": label,
        "validation_labels_available": bool(va_y is not None),
        "numerical_mean": mean_list,
        "numerical_std": std_list,
        "category_domain_sizes": {c: len(cat_dicts[c]) for c in categorical},
        "timings_seconds": timings,
        "outputs": outputs,
        "completed": True,
    }
    with open(os.path.join(out_dir, "run.json"), "w", encoding="utf-8") as fh:
        json.dump(run, fh, indent=2, sort_keys=True)

    print("fit ok: train %s validation %s (%d features)" % (
        tuple(tr_X_cpu.shape), tuple(va_X_cpu.shape), len(order)))
    return 0


# --------------------------------------------------------------------------- #
# transform                                                                    #
# --------------------------------------------------------------------------- #

def transform(args):
    import torch

    with open(args.preprocessor, "r", encoding="utf-8") as fh:
        preproc = json.load(fh)
    numerical = preproc["numerical"]
    categorical = preproc["categorical"]
    order = preproc.get("feature_order") or (list(numerical) + list(categorical))
    label = preproc.get("label", "label")
    mean_list = preproc["num_mean"]
    std_list = preproc["num_std"]
    cat_dicts = preproc.get("category_dicts", {})

    _require_cuda(torch)
    device = torch.device("cuda", 0)
    torch.cuda.synchronize()

    rows = read_jsonl(args.input)
    nums, cats, _ = extract(rows, numerical, categorical, label, order)

    n_num = len(numerical)
    if n_num > 0:
        num_t = torch.tensor(nums, dtype=torch.float32, device=device)
        m = torch.tensor(mean_list, dtype=torch.float32, device=device)
        s = torch.tensor(std_list, dtype=torch.float32, device=device)
        num_std = (num_t - m) / s
    else:
        num_std = torch.zeros((len(nums), 0), dtype=torch.float32, device=device)

    cat_t = build_cat_tensor(cats, categorical, cat_dicts, device, torch)
    X = torch.cat([num_std, cat_t], dim=1)
    torch.cuda.synchronize()
    X_cpu = X.detach().to("cpu").numpy().astype(np.float32, copy=False)

    out_path = args.output
    parent = os.path.dirname(os.path.abspath(out_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    np.save(out_path, X_cpu)
    print("transform ok: %s shape=%s dtype=%s" % (out_path, X_cpu.shape, X_cpu.dtype))
    return 0


# --------------------------------------------------------------------------- #
# doctor                                                                       #
# --------------------------------------------------------------------------- #

def doctor(args):
    """Inspect required files and dependencies without running fit/transform."""
    missing = []
    in_dir = args.input
    for fn in ("schema.json", "train.jsonl", "validation.jsonl"):
        p = os.path.join(in_dir, fn)
        if not os.path.isfile(p):
            missing.append("missing input file: %s" % os.path.abspath(p))

    try:
        import numpy  # noqa: F401
    except Exception as exc:  # pragma: no cover
        missing.append("missing dependency: numpy (%s)" % exc)

    try:
        import torch
        if not torch.cuda.is_available():
            missing.append(
                "CUDA not available: torch.cuda.is_available() returned False")
    except Exception as exc:  # pragma: no cover
        missing.append("missing dependency: torch (%s)" % exc)

    if missing:
        print("doctor: MISSING ITEMS")
        for m in missing:
            print("  - %s" % m)
        return 78

    print("doctor: all required input files and dependencies are present")
    return 0


# --------------------------------------------------------------------------- #
# entrypoint                                                                   #
# --------------------------------------------------------------------------- #

def build_parser():
    p = argparse.ArgumentParser(
        prog="solution/main.py",
        description="Criteo_x1 recommendation feature preprocessor (GPUv1-E02 debug).")
    sub = p.add_subparsers(dest="cmd")

    f = sub.add_parser("fit", help="fit the preprocessor and write feature artifacts")
    f.add_argument("--input", required=True, help="input directory (schema/train/validation)")
    f.add_argument("--output", required=True, help="output directory")

    t = sub.add_parser("transform", help="apply a saved preprocessor to a JSONL file")
    t.add_argument("--preprocessor", required=True, help="path to preprocessor.json")
    t.add_argument("--input", required=True, help="input JSONL file")
    t.add_argument("--output", required=True, help="output .npy path")

    d = sub.add_parser("doctor", help="check required files and dependencies only")
    d.add_argument("--input", required=True, help="input directory")
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 0
    if args.cmd == "fit":
        return fit(args)
    if args.cmd == "transform":
        return transform(args)
    if args.cmd == "doctor":
        return doctor(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
