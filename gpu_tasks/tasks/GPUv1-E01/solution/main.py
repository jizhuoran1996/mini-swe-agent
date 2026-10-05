#!/usr/bin/env python3
"""GPUv1-E01 debug variant: CUDA TPC-H Q1/Q6 materialization + re-query.

Input:  input/lineitem.npy  (float64, columns per TPC-H SF0.1)
Output: output/queries.json, output/dataset.npy, output/state.json, output/run.json

Subcommands:
  run    --input DIR  --output DIR      run Q1+Q6 on CUDA, verify vs CPU, write artifacts
  query  --state DIR  --start-date ... --end-date ... \
         --discount-low F --discount-high F --quantity-limit F --output FILE
                                         Q6 semantics with new conditions,
                                         reading only state/dataset (never the raw input)
  doctor --input DIR                    inspect required files/deps, exit 0 / 78
"""
import argparse
import hashlib
import json
import os
import sys
import time
from datetime import date

EPOCH = date(1970, 1, 1)
COLUMNS = [
    "quantity", "extendedprice", "discount", "tax",
    "shipdate_days_since1970", "returnflag_ascii", "linestatus_ascii",
]
Q1_CUTOFF = (1998, 9, 2)
Q6_DEFAULTS = {
    "start_date": "1994-01-01", "end_date": "1995-01-01",
    "discount_low": 0.05, "discount_high": 0.07, "quantity_limit": 24.0,
}
REL_TOL = 1e-8


def dse(y, m, d):
    """days since 1970-01-01"""
    return (date(y, m, d) - EPOCH).days


def parse_date(s):
    y, m, d = s.split("-")
    return int(y), int(m), int(d)


def die(msg, code=1):
    print("ERROR: " + str(msg), file=sys.stderr)
    sys.exit(code)


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def relerr(a, b):
    denom = abs(b)
    if denom < 1e-300:
        denom = 1.0
    return abs(a - b) / denom


# ---------------------------------------------------------------------------
# CUDA kernels (real float64 device reductions)
# ---------------------------------------------------------------------------
def cuda_q1(torch, g):
    dev = g.device
    qty, ext, disc, tax = g[:, 0], g[:, 1], g[:, 2], g[:, 3]
    ship, rf, ls = g[:, 4], g[:, 5], g[:, 6]
    cutoff = float(dse(*Q1_CUTOFF))
    m = ship <= cutoff
    q, e, d, t = qty[m], ext[m], disc[m], tax[m]
    key = rf[m].to(torch.int64) * 1000 + ls[m].to(torch.int64)
    uniq, inv = torch.unique(key, return_inverse=True)
    n = int(uniq.numel())

    def agg(v):
        o = torch.zeros(n, dtype=torch.float64, device=dev)
        o.scatter_add_(0, inv, v)
        return o

    sum_qty = agg(q)
    sum_base = agg(e)
    sum_disc_price = agg(e * (1.0 - d))
    sum_charge = agg(e * (1.0 - d) * (1.0 + t))
    cnt = torch.zeros(n, dtype=torch.float64, device=dev)
    cnt.scatter_add_(0, inv, torch.ones_like(q))
    avg_qty = sum_qty / cnt
    avg_price = sum_base / cnt
    avg_disc = agg(d) / cnt

    rf_k = (uniq // 1000).to(torch.int64).cpu().tolist()
    ls_k = (uniq % 1000).to(torch.int64).cpu().tolist()
    out = {
        "sum_qty": sum_qty.cpu().tolist(),
        "sum_base_price": sum_base.cpu().tolist(),
        "sum_disc_price": sum_disc_price.cpu().tolist(),
        "sum_charge": sum_charge.cpu().tolist(),
        "avg_qty": avg_qty.cpu().tolist(),
        "avg_price": avg_price.cpu().tolist(),
        "avg_disc": avg_disc.cpu().tolist(),
        "count": cnt.cpu().tolist(),
    }
    rows = []
    for i in range(n):
        rows.append({
            "returnflag": chr(int(rf_k[i])),
            "linestatus": chr(int(ls_k[i])),
            "sum_qty": out["sum_qty"][i],
            "sum_base_price": out["sum_base_price"][i],
            "sum_disc_price": out["sum_disc_price"][i],
            "sum_charge": out["sum_charge"][i],
            "avg_qty": out["avg_qty"][i],
            "avg_price": out["avg_price"][i],
            "avg_disc": out["avg_disc"][i],
            "count": out["count"][i],
        })
    return rows


def cuda_q6(torch, g, sd, ed, dlow, dhigh, qlim):
    ship, disc, qty, ext = g[:, 4], g[:, 2], g[:, 0], g[:, 1]
    lo = float(dse(*sd))
    hi = float(dse(*ed))
    m = (ship >= lo) & (ship < hi) & (disc >= dlow) & (disc <= dhigh) & (qty < qlim)
    total = (ext * disc)[m].sum()
    return float(total.item())


# ---------------------------------------------------------------------------
# CPU reference (independent numpy full recompute)
# ---------------------------------------------------------------------------
def cpu_q1(arr):
    import numpy as np
    qty, ext, disc, tax = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]
    ship, rf, ls = arr[:, 4], arr[:, 5], arr[:, 6]
    m = ship <= float(dse(*Q1_CUTOFF))
    q, e, d, t = qty[m], ext[m], disc[m], tax[m]
    key = rf[m].astype(np.int64) * 1000 + ls[m].astype(np.int64)
    uniq, inv = np.unique(key, return_inverse=True)
    n = uniq.size

    def agg(v):
        o = np.zeros(n, dtype=np.float64)
        np.add.at(o, inv, v)
        return o

    sum_qty = agg(q)
    sum_base = agg(e)
    sum_disc = agg(e * (1.0 - d))
    sum_chg = agg(e * (1.0 - d) * (1.0 + t))
    cnt = agg(np.ones_like(q))
    rows = []
    for i in range(n):
        k = int(uniq[i])
        rows.append({
            "returnflag": chr(k // 1000),
            "linestatus": chr(k % 1000),
            "sum_qty": float(sum_qty[i]),
            "sum_base_price": float(sum_base[i]),
            "sum_disc_price": float(sum_disc[i]),
            "sum_charge": float(sum_chg[i]),
            "avg_qty": float(sum_qty[i] / cnt[i]),
            "avg_price": float(sum_base[i] / cnt[i]),
            "avg_disc": float(agg(d)[i] / cnt[i]),
            "count": int(cnt[i]),
        })
    return rows


def cpu_q6(arr, sd, ed, dlow, dhigh, qlim):
    import numpy as np
    ship, disc, qty, ext = arr[:, 4], arr[:, 2], arr[:, 0], arr[:, 1]
    lo, hi = float(dse(*sd)), float(dse(*ed))
    m = (ship >= lo) & (ship < hi) & (disc >= dlow) & (disc <= dhigh) & (qty < qlim)
    return float(np.sum(ext[m] * disc[m]))


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------
def cmd_doctor(args):
    missing = []
    for name in ("lineitem.npy", "manifest.json"):
        p = os.path.join(args.input, name)
        if not os.path.isfile(p):
            missing.append("input file: " + p)
    try:
        import numpy  # noqa: F401
    except Exception as e:  # pragma: no cover
        missing.append("numpy: %r" % (e,))
    try:
        import torch
        if not torch.cuda.is_available():
            missing.append("torch.cuda: no CUDA device visible")
    except Exception as e:  # pragma: no cover
        missing.append("torch: %r" % (e,))
    if missing:
        for m in missing:
            print("MISSING: " + m)
        return 78
    print("OK: required inputs and CUDA dependencies present")
    return 0


def require_cuda():
    import torch
    if not torch.cuda.is_available():
        die("CUDA is required for this task but no CUDA device is available")
    return torch


def cmd_run(args):
    torch = require_cuda()
    import numpy as np

    in_path = os.path.join(args.input, "lineitem.npy")
    if not os.path.isfile(in_path):
        die("missing input file: " + in_path)
    os.makedirs(args.output, exist_ok=True)

    t_all = time.perf_counter()

    # ---- load ----
    t0 = time.perf_counter()
    arr = np.load(in_path)
    if arr.dtype != np.float64 or arr.ndim != 2 or arr.shape[1] != 7:
        die("unexpected input array: shape=%r dtype=%r" % (arr.shape, arr.dtype))
    arr = np.ascontiguousarray(arr)
    in_sha = sha256_file(in_path)
    t_load = time.perf_counter() - t0
    rows_n = int(arr.shape[0])

    dev = torch.device("cuda")
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    g = torch.from_numpy(arr).to(device=dev, dtype=torch.float64)
    torch.cuda.synchronize()
    t_h2d = time.perf_counter() - t0
    h2d_bytes = int(arr.nbytes)

    # ---- GPU Q1 ----
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    q1 = cuda_q1(torch, g)
    torch.cuda.synchronize()
    t_q1 = time.perf_counter() - t0

    # ---- GPU Q6 ----
    sd = parse_date(Q6_DEFAULTS["start_date"])
    ed = parse_date(Q6_DEFAULTS["end_date"])
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    q6 = cuda_q6(torch, g, sd, ed, Q6_DEFAULTS["discount_low"],
                 Q6_DEFAULTS["discount_high"], Q6_DEFAULTS["quantity_limit"])
    torch.cuda.synchronize()
    t_q6 = time.perf_counter() - t0

    # ---- CPU reference ----
    t0 = time.perf_counter()
    q1_ref = cpu_q1(arr)
    q6_ref = cpu_q6(arr, sd, ed, Q6_DEFAULTS["discount_low"],
                    Q6_DEFAULTS["discount_high"], Q6_DEFAULTS["quantity_limit"])
    t_cpu = time.perf_counter() - t0

    # ---- verification ----
    verify = {"q1": {}, "q6": {}, "max_rel_err": 0.0, "passed": True}
    if len(q1) != len(q1_ref):
        verify["passed"] = False
        verify["q1"]["group_mismatch"] = [len(q1), len(q1_ref)]
    else:
        for i in range(len(q1)):
            for k in ("returnflag", "linestatus"):
                if q1[i][k] != q1_ref[i][k]:
                    verify["passed"] = False
            for k in ("sum_qty", "sum_base_price", "sum_disc_price",
                      "sum_charge", "avg_qty", "avg_price", "avg_disc"):
                r = relerr(q1[i][k], q1_ref[i][k])
                verify["max_rel_err"] = max(verify["max_rel_err"], r)
                if r > REL_TOL:
                    verify["passed"] = False
            if int(q1[i]["count"]) != int(q1_ref[i]["count"]):
                verify["passed"] = False
    r6 = relerr(q6, q6_ref)
    verify["q6"] = {"gpu": q6, "cpu": q6_ref, "rel_err": r6}
    verify["max_rel_err"] = max(verify["max_rel_err"], r6)
    if r6 > REL_TOL:
        verify["passed"] = False

    # ---- write artifacts ----
    np.save(os.path.join(args.output, "dataset.npy"), arr)

    queries = {
        "task": "GPUv1-E01",
        "scale": "debug_only",
        "Q1": {
            "filter": {"shipdate_lte": "1998-09-02"},
            "group_by": ["returnflag", "linestatus"],
            "aggregates": ["sum_qty", "sum_base_price", "sum_disc_price",
                           "sum_charge", "avg_qty", "avg_price", "avg_disc", "count"],
            "groups": q1,
        },
        "Q6": {
            "filter": {
                "shipdate_ge": Q6_DEFAULTS["start_date"],
                "shipdate_lt": Q6_DEFAULTS["end_date"],
                "discount_between": [Q6_DEFAULTS["discount_low"], Q6_DEFAULTS["discount_high"]],
                "quantity_lt": Q6_DEFAULTS["quantity_limit"],
            },
            "sum_extendedprice_discount": q6,
        },
        "verification": verify,
    }
    with open(os.path.join(args.output, "queries.json"), "w") as f:
        json.dump(queries, f, indent=2)

    state = {
        "task": "GPUv1-E01",
        "dataset": "dataset.npy",
        "columns": COLUMNS,
        "shape": [rows_n, 7],
        "dtype": "float64",
        "epoch": "1970-01-01",
        "q6_defaults": Q6_DEFAULTS,
        "input_sha256": in_sha,
    }
    with open(os.path.join(args.output, "state.json"), "w") as f:
        json.dump(state, f, indent=2)

    t_total = time.perf_counter() - t_all
    run = {
        "task": "GPUv1-E01",
        "status": "ok" if verify["passed"] else "verification_failed",
        "cuda": True,
        "cuda_device": torch.cuda.get_device_name(0),
        "rows": rows_n,
        "cols": 7,
        "input_sha256": in_sha,
        "h2d_bytes": h2d_bytes,
        "timings_s": {
            "load": t_load,
            "h2d": t_h2d,
            "q1_gpu": t_q1,
            "q6_gpu": t_q6,
            "cpu_reference": t_cpu,
            "total": t_total,
        },
        "verification": verify,
        "rel_tol": REL_TOL,
    }
    with open(os.path.join(args.output, "run.json"), "w") as f:
        json.dump(run, f, indent=2)

    if not verify["passed"]:
        die("verification failed: max_rel_err=%g" % verify["max_rel_err"], 2)
    print("run OK: rows=%d Q1_groups=%d Q6=%.10f" % (rows_n, len(q1), q6))
    return 0


def cmd_query(args):
    torch = require_cuda()
    import numpy as np

    state_path = os.path.join(args.state, "state.json")
    if not os.path.isfile(state_path):
        die("missing state file: " + state_path)
    with open(state_path) as f:
        state = json.load(f)
    ds_path = os.path.join(args.state, state["dataset"])
    if not os.path.isfile(ds_path):
        die("missing dataset file referenced by state: " + ds_path)

    sd = parse_date(args.start_date)
    ed = parse_date(args.end_date)
    if dse(*sd) >= dse(*ed):
        die("start-date must be before end-date")
    if args.discount_low > args.discount_high:
        die("discount-low must be <= discount-high")

    arr = np.load(ds_path)
    if arr.dtype != np.float64 or arr.ndim != 2 or arr.shape[1] != 7:
        die("unexpected dataset: %r %r" % (arr.shape, arr.dtype))
    arr = np.ascontiguousarray(arr)

    dev = torch.device("cuda")
    t0 = time.perf_counter()
    g = torch.from_numpy(arr).to(device=dev, dtype=torch.float64)
    torch.cuda.synchronize()
    gpu_val = cuda_q6(torch, g, sd, ed,
                      args.discount_low, args.discount_high, args.quantity_limit)
    torch.cuda.synchronize()
    t_gpu = time.perf_counter() - t0

    cpu_val = cpu_q6(arr, sd, ed,
                     args.discount_low, args.discount_high, args.quantity_limit)
    r = relerr(gpu_val, cpu_val)
    if r > REL_TOL:
        die("query verification failed: rel_err=%g" % r, 2)

    out = {
        "task": "GPUv1-E01",
        "query": "Q6",
        "sum_extendedprice_discount": gpu_val,
        "cpu_reference": cpu_val,
        "relative_error": r,
        "cuda": True,
        "conditions": {
            "start_date": args.start_date,
            "end_date": args.end_date,
            "discount_low": args.discount_low,
            "discount_high": args.discount_high,
            "quantity_limit": args.quantity_limit,
        },
        "gpu_time_s": t_gpu,
    }
    with open(args.output, "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out))
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="solution/main.py",
                                description="GPUv1-E01 CUDA Q1/Q6 materialization")
    sub = p.add_subparsers(dest="cmd")

    r = sub.add_parser("run", help="materialize Q1/Q6 on CUDA and write artifacts")
    r.add_argument("--input", required=True)
    r.add_argument("--output", required=True)
    r.set_defaults(func=cmd_run)

    q = sub.add_parser("query", help="re-run Q6 semantics with new conditions")
    q.add_argument("--state", required=True, help="previous output dir (state.json)")
    q.add_argument("--start-date", required=True)
    q.add_argument("--end-date", required=True)
    q.add_argument("--discount-low", type=float, required=True)
    q.add_argument("--discount-high", type=float, required=True)
    q.add_argument("--quantity-limit", type=float, required=True)
    q.add_argument("--output", required=True)
    q.set_defaults(func=cmd_query)

    d = sub.add_parser("doctor", help="inspect inputs and CUDA dependencies")
    d.add_argument("--input", required=True)
    d.set_defaults(func=cmd_doctor)

    return p


def main(argv=None):
    p = build_parser()
    args = p.parse_args(argv)
    if not getattr(args, "cmd", None) or not hasattr(args, "func"):
        p.print_help()
        return 0
    rc = args.func(args)
    return 0 if rc is None else rc


if __name__ == "__main__":
    sys.exit(main())
