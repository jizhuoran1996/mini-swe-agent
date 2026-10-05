#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GPUv1-E05 (debug variant) - exact CUDA L2 top-k index over native SIFT1M.

Commands
--------
  build  --input input --output output
  query  --index output/index --queries PATH --output DIR [--k 10]
  serve  --index output/index --port PORT [--host HOST]
  doctor --input input

The index is a persisted, reloadable exact L2 database (float vectors + meta).
All distance math runs on CUDA; queries are processed in memory-bounded tiles
so a full N x N matrix is never materialised.  Distances are accumulated in
IEEE float64, which is exact for the integer-valued uint8 SIFT descriptors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import sys
import threading
import time
from urllib.parse import urlsplit

import numpy as np

TASK_ID = "GPUv1-E05"
INDEX_FORMAT = "e05-exact-l2-v1"
K_DEFAULT = 10
EXIT_MISSING = 78
EXIT_FAIL = 1


# ------------------------------------------------------------------ helpers
def log(msg):
    print("[%s] %s" % (TASK_ID, msg), flush=True)


def warn(msg):
    print("[%s][WARN] %s" % (TASK_ID, msg), file=sys.stderr, flush=True)


def die(msg, code=EXIT_FAIL):
    print("[%s][ERROR] %s" % (TASK_ID, msg), file=sys.stderr, flush=True)
    raise SystemExit(code)


def utcnow():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_file(path, bufsize=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(bufsize)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def require_cuda():
    """Return the torch module, or abort: this task must run on a real GPU."""
    try:
        import torch
    except Exception as exc:  # pragma: no cover
        die("PyTorch is not importable: %s" % exc)
    if not torch.cuda.is_available():
        die("CUDA is required for this task but torch.cuda.is_available() is False")
    try:
        torch.cuda.set_device(0)
        torch.zeros(1, device="cuda")
        torch.cuda.synchronize()
    except Exception as exc:
        die("CUDA device initialisation failed: %s" % exc)
    return torch


def gpu_info(torch):
    if not torch.cuda.is_available():
        return {"available": False, "torch_version": getattr(torch, "__version__", None)}
    p = torch.cuda.get_device_properties(0)
    return {
        "available": True,
        "device_count": torch.cuda.device_count(),
        "device_name": p.name,
        "capability": [int(p.major), int(p.minor)],
        "total_memory_bytes": int(p.total_memory),
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
    }


# ------------------------------------------------------------- GPU searcher
class ExactL2Index:
    """Exact squared-L2 top-k over a vector database that lives in GPU memory."""

    def __init__(self, base_np, device=None, verbose=True):
        import torch

        self.torch = torch
        self.device = torch.device("cuda" if device is None else device)
        if self.device.type != "cuda":
            raise RuntimeError("ExactL2Index requires a CUDA device")
        b = np.ascontiguousarray(np.asarray(base_np))
        if b.dtype not in (np.float32, np.float64):
            b = b.astype(np.float64)
        t0 = time.perf_counter()
        self.base = torch.from_numpy(np.ascontiguousarray(b, dtype=np.float64)).to(self.device)
        self.n, self.d = int(self.base.shape[0]), int(self.base.shape[1])
        self.b2 = (self.base * self.base).sum(dim=1)
        torch.cuda.synchronize(self.device)
        self.gpu_load_s = time.perf_counter() - t0
        self.device_name = torch.cuda.get_device_properties(self.device).name
        self._lock = threading.Lock()
        free, _ = torch.cuda.mem_get_info(self.device)
        self.Qc, self.Bc = self._pick_chunks(free)
        if verbose:
            log(
                "index resident on GPU: n=%d d=%d (%.2f GiB fp64), tiles Q=%d B=%d"
                % (self.n, self.d, self.base.numel() * 8 / float(1 << 30), self.Qc, self.Bc)
            )

    def _pick_chunks(self, free_bytes):
        budget = int(min(768 * (1 << 20), max(64 * (1 << 20), 0.20 * free_bytes)))
        bc = min(self.n, 1 << 18)
        qc = int(budget // max(1, bc * 8))
        qc = max(8, min(2048, qc))
        return qc, bc

    def search(self, queries, k=K_DEFAULT):
        torch = self.torch
        q_np = np.ascontiguousarray(np.asarray(queries))
        if q_np.ndim == 1:
            q_np = q_np.reshape(1, -1)
        if q_np.ndim != 2 or q_np.shape[1] != self.d:
            raise ValueError("query shape %s incompatible with index dim %d" % (q_np.shape, self.d))
        k = int(k)
        if k < 1 or k > self.n:
            raise ValueError("k must be in [1, %d]" % self.n)
        nq = int(q_np.shape[0])
        out_i = np.empty((nq, k), dtype=np.int64)
        out_d = np.empty((nq, k), dtype=np.float32)
        with self._lock:
            for q0 in range(0, nq, self.Qc):
                qb = q_np[q0:q0 + self.Qc]
                q = torch.from_numpy(np.ascontiguousarray(qb, dtype=np.float64)).to(self.device)
                q2 = (q * q).sum(dim=1, keepdim=True)
                best_d = None
                best_i = None
                for b0 in range(0, self.n, self.Bc):
                    b1 = min(b0 + self.Bc, self.n)
                    bc = self.base[b0:b1]
                    # (q2 + b2) - 2 q.b^T  -- no N x N tile is ever materialised
                    dd = torch.addmm(
                        q2 + self.b2[b0:b1].unsqueeze(0), q, bc.t(), beta=1.0, alpha=-2.0
                    )
                    dd.clamp_(min=0.0)
                    kk = min(k, b1 - b0)
                    v, i = torch.topk(dd, kk, dim=1, largest=False, sorted=True)
                    i = i + b0
                    if best_d is None:
                        best_d, best_i = v, i
                    else:
                        cd = torch.cat((best_d, v), dim=1)
                        ci = torch.cat((best_i, i), dim=1)
                        order = torch.argsort(cd, dim=1, stable=True)[:, :k]
                        best_d = torch.gather(cd, 1, order)
                        best_i = torch.gather(ci, 1, order)
                torch.cuda.synchronize(self.device)
                out_i[q0:q0 + qb.shape[0], :] = best_i.to("cpu").numpy().astype(np.int64)
                out_d[q0:q0 + qb.shape[0], :] = (
                    torch.clamp(best_d, min=0.0).to("cpu").numpy().astype(np.float32)
                )
        return out_i, out_d


# ------------------------------------------------------------ CPU oracle
def cpu_oracle_topk(base_np, q_np, k=K_DEFAULT, batch=32, chunk=1 << 16):
    """Independent float64 CPU brute-force reference used for the self check."""
    b = np.ascontiguousarray(base_np, dtype=np.float64)
    n, d = b.shape
    b2 = np.einsum("ij,ij->i", b, b)
    qs = np.ascontiguousarray(q_np, dtype=np.float64)
    nq = qs.shape[0]
    out_i = np.empty((nq, k), dtype=np.int64)
    out_d = np.empty((nq, k), dtype=np.float64)
    for q0 in range(0, nq, batch):
        qb = qs[q0:q0 + batch]
        nb = qb.shape[0]
        q2 = np.einsum("ij,ij->i", qb, qb)
        prod = b @ qb.T                      # (n, nb)
        cols = np.arange(nb)[None, :]
        best_v = np.full((k, nb), np.inf)
        best_i = np.full((k, nb), -1, dtype=np.int64)
        for b0 in range(0, n, chunk):
            b1 = min(b0 + chunk, n)
            dd = b2[b0:b1, None] + q2[None, :] - 2.0 * prod[b0:b1]
            dd = np.maximum(dd, 0.0)
            kk = min(k, b1 - b0)
            part = np.argpartition(dd, kk - 1, axis=0)[:kk, :]
            vals = dd[part, cols]
            ridx = part + b0
            cv = np.concatenate([best_v, vals], axis=0)
            ci = np.concatenate([best_i, ridx], axis=0)
            order = np.argsort(cv, axis=0, kind="stable")[:k, :]
            best_v = np.take_along_axis(cv, order, axis=0)
            best_i = np.take_along_axis(ci, order, axis=0)
        out_i[q0:q0 + nb] = best_i.T
        out_d[q0:q0 + nb] = best_v.T
    return out_i, out_d


def recall_report(idx, dist, ref_i, ref_d, k):
    nq = int(idx.shape[0])
    hits, exact_rows = 0, 0
    for r in range(nq):
        a = idx[r].tolist()
        b = ref_i[r].tolist()
        hits += len(set(a) & set(b))
        if a == b:
            exact_rows += 1
    diff = np.abs(np.asarray(dist, dtype=np.float64) - np.asarray(ref_d, dtype=np.float64))
    return {
        "n_queries": nq,
        "k": int(k),
        "recall_at_k": hits / float(nq * k),
        "exact_row_match_frac": exact_rows / float(nq),
        "max_abs_squared_distance_diff": float(np.max(diff)) if diff.size else 0.0,
    }


# ------------------------------------------------------------------- build
def cmd_build(args):
    t_start = time.perf_counter()
    timings = {}
    inp = os.path.abspath(args.input)
    out = os.path.abspath(args.output)
    if not os.path.isdir(inp):
        die("input directory does not exist: %s" % inp, EXIT_MISSING)
    os.makedirs(out, exist_ok=True)

    missing = [n for n in ("base.npy", "queries.npy") if not os.path.isfile(os.path.join(inp, n))]
    if missing:
        die("missing required input file(s) in %s: %s" % (inp, ", ".join(missing)), EXIT_MISSING)

    manifest = {}
    mpath = os.path.join(inp, "manifest.json")
    if os.path.isfile(mpath):
        try:
            manifest = read_json(mpath)
        except Exception as exc:
            warn("could not parse manifest.json: %s" % exc)

    t0 = time.perf_counter()
    hashes = {}
    for name in ("base.npy", "queries.npy"):
        hashes[name] = sha256_file(os.path.join(inp, name))
    timings["hashing_s"] = time.perf_counter() - t0
    declared = manifest.get("files") or {}
    for name, h in hashes.items():
        exp = declared.get(name)
        if exp and exp != h:
            die("sha256 mismatch for %s: manifest=%s actual=%s" % (name, exp, h))
        log("sha256 %s %s" % (name, h))

    torch = require_cuda()
    torch.manual_seed(0)
    torch.cuda.manual_seed_all(0)

    t0 = time.perf_counter()
    base = np.load(os.path.join(inp, "base.npy"), mmap_mode="r")
    queries = np.load(os.path.join(inp, "queries.npy"), mmap_mode="r")
    timings["load_inputs_s"] = time.perf_counter() - t0
    if base.ndim != 2 or queries.ndim != 2 or base.shape[1] != queries.shape[1]:
        die("unexpected shapes: base=%s queries=%s" % (base.shape, queries.shape))
    log("base %s %s / queries %s %s" % (base.shape, base.dtype, queries.shape, queries.dtype))

    # ---- persist the searchable database -------------------------------------------------
    index_dir = os.path.join(out, "index")
    os.makedirs(index_dir, exist_ok=True)
    vec_dtype = base.dtype if base.dtype in (np.float32, np.float64) else np.float32
    vectors_path = os.path.join(index_dir, "vectors.npy")
    t0 = time.perf_counter()
    np.save(vectors_path, np.asarray(base, dtype=vec_dtype))
    timings["index_write_s"] = time.perf_counter() - t0
    vec_sha = sha256_file(vectors_path)

    index_meta = {
        "task_id": TASK_ID,
        "format": INDEX_FORMAT,
        "metric": "l2_squared",
        "exact": True,
        "ntotal": int(base.shape[0]),
        "dim": int(base.shape[1]),
        "vectors_file": "vectors.npy",
        "vectors_dtype": str(np.dtype(vec_dtype)),
        "vectors_sha256": vec_sha,
        "created_utc": utcnow(),
        "source": {
            "base.npy": hashes["base.npy"],
            "queries.npy": hashes["queries.npy"],
            "manifest_task_id": manifest.get("task_id"),
        },
    }
    write_json(os.path.join(index_dir, "meta.json"), index_meta)

    # ---- load to GPU and query every source query ---------------------------------------
    t0 = time.perf_counter()
    searcher = ExactL2Index(np.asarray(base, dtype=vec_dtype), device=torch.device("cuda"))
    timings["index_load_gpu_s"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    idx_arr, dist_arr = searcher.search(np.asarray(queries), k=args.k)
    torch.cuda.synchronize()
    timings["search_s"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    np.save(os.path.join(out, "indices.npy"), idx_arr)
    np.save(os.path.join(out, "squared_distances.npy"), dist_arr)
    timings["save_outputs_s"] = time.perf_counter() - t0
    log("indices %s / squared_distances %s" % (idx_arr.shape, dist_arr.shape))

    # ---- independent CPU oracle self check (subset) -------------------------------------
    selfcheck = None
    if not args.no_selfcheck:
        m = int(min(args.selfcheck_queries, queries.shape[0]))
        if m > 0:
            log("running independent float64 CPU oracle on %d queries ..." % m)
            t0 = time.perf_counter()
            ref_i, ref_d = cpu_oracle_topk(np.asarray(base), np.asarray(queries[:m]), k=args.k)
            selfcheck = recall_report(idx_arr[:m], dist_arr[:m], ref_i, ref_d, args.k)
            timings["selfcheck_s"] = time.perf_counter() - t0
            log("selfcheck recall@%d = %.6f, exact rows = %.4f"
                % (args.k, selfcheck["recall_at_k"], selfcheck["exact_row_match_frac"]))

    timings["total_s"] = time.perf_counter() - t_start
    run = {
        "task_id": TASK_ID,
        "mode": "build",
        "timestamp_utc": utcnow(),
        "cuda": gpu_info(torch),
        "numpy_version": np.__version__,
        "inputs": {
            "base.npy": {"path": os.path.join(inp, "base.npy"), "sha256": hashes["base.npy"],
                          "shape": list(base.shape), "dtype": str(base.dtype)},
            "queries.npy": {"path": os.path.join(inp, "queries.npy"), "sha256": hashes["queries.npy"],
                             "shape": list(queries.shape), "dtype": str(queries.dtype)},
        },
        "index": index_meta,
        "params": {
            "k": int(args.k),
            "precision": "float64",
            "tile_queries": int(searcher.Qc),
            "tile_base": int(searcher.Bc),
            "exact": True,
        },
        "timings": timings,
        "outputs": {
            "indices.npy": {"path": os.path.join(out, "indices.npy"), "shape": list(idx_arr.shape),
                             "dtype": str(idx_arr.dtype)},
            "squared_distances.npy": {"path": os.path.join(out, "squared_distances.npy"),
                                      "shape": list(dist_arr.shape), "dtype": str(dist_arr.dtype)},
            "index": index_dir,
        },
        "selfcheck": selfcheck,
    }
    write_json(os.path.join(out, "run.json"), run)
    log("build done in %.2f s" % timings["total_s"])
    return 0


# ------------------------------------------------------------------- query
def load_index(index_dir):
    index_dir = os.path.abspath(index_dir)
    meta_path = os.path.join(index_dir, "meta.json")
    if not os.path.isfile(meta_path):
        die("index meta not found: %s" % meta_path, EXIT_MISSING)
    meta = read_json(meta_path)
    vec_path = os.path.join(index_dir, meta.get("vectors_file", "vectors.npy"))
    if not os.path.isfile(vec_path):
        die("index vectors not found: %s" % vec_path, EXIT_MISSING)
    return meta, vec_path


def cmd_query(args):
    t_start = time.perf_counter()
    timings = {}
    torch = require_cuda()
    out = os.path.abspath(args.output)
    os.makedirs(out, exist_ok=True)
    meta, vec_path = load_index(args.index)
    if not os.path.isfile(args.queries):
        die("query file not found: %s" % args.queries, EXIT_MISSING)

    t0 = time.perf_counter()
    base = np.load(vec_path, mmap_mode="r")
    queries = np.load(args.queries)
    timings["load_s"] = time.perf_counter() - t0
    if int(base.shape[1]) != int(meta.get("dim", base.shape[1])):
        die("index meta dim %s disagrees with vectors shape %s" % (meta.get("dim"), base.shape))
    if queries.ndim != 2 or queries.shape[1] != base.shape[1]:
        die("query shape %s incompatible with index dim %d" % (queries.shape, base.shape[1]))

    t0 = time.perf_counter()
    searcher = ExactL2Index(np.asarray(base, dtype=base.dtype), device=torch.device("cuda"))
    timings["index_load_gpu_s"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    idx_arr, dist_arr = searcher.search(np.asarray(queries), k=args.k)
    torch.cuda.synchronize()
    timings["search_s"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    np.save(os.path.join(out, "indices.npy"), idx_arr)
    np.save(os.path.join(out, "squared_distances.npy"), dist_arr)
    timings["save_outputs_s"] = time.perf_counter() - t0
    timings["total_s"] = time.perf_counter() - t_start

    run = {
        "task_id": TASK_ID,
        "mode": "query",
        "timestamp_utc": utcnow(),
        "cuda": gpu_info(torch),
        "index": {"path": os.path.abspath(args.index), "ntotal": int(meta.get("ntotal", base.shape[0])),
                  "dim": int(meta.get("dim", base.shape[1])), "format": meta.get("format")},
        "queries": {"path": os.path.abspath(args.queries), "sha256": sha256_file(args.queries),
                    "shape": list(queries.shape), "dtype": str(queries.dtype)},
        "params": {"k": int(args.k), "precision": "float64", "exact": True,
                   "tile_queries": int(searcher.Qc), "tile_base": int(searcher.Bc)},
        "timings": timings,
        "outputs": {"indices.npy": os.path.join(out, "indices.npy"),
                    "squared_distances.npy": os.path.join(out, "squared_distances.npy")},
    }
    write_json(os.path.join(out, "run.json"), run)
    log("query done in %.2f s -> %s" % (timings["total_s"], out))
    return 0


# ------------------------------------------------------------------- serve
def make_handler(searcher, index_meta):
    from http.server import BaseHTTPRequestHandler

    class SearchHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "%s/1.0" % TASK_ID

        def log_message(self, fmt, *a):  # keep stdout clean
            pass

        def _send(self, code, obj):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path.rstrip("/") or "/"
            if path in ("/health", "/healthz", "/"):
                self._send(200, {
                    "status": "ok",
                    "task_id": TASK_ID,
                    "cuda": True,
                    "device": searcher.device_name,
                    "metric": "l2_squared",
                    "exact": True,
                    "ntotal": int(searcher.n),
                    "dim": int(searcher.d),
                    "index_format": index_meta.get("format"),
                })
            else:
                self._send(404, {"error": "not found", "path": path})

        def do_POST(self):
            path = urlsplit(self.path).path.rstrip("/") or "/"
            if path != "/search":
                self._send(404, {"error": "not found", "path": path})
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except Exception:
                length = 0
            if length <= 0:
                self._send(400, {"error": "empty body"})
                return
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except Exception as exc:
                self._send(400, {"error": "invalid json: %s" % exc})
                return
            if not isinstance(payload, dict):
                self._send(400, {"error": "body must be a json object"})
                return
            vectors = payload.get("vectors")
            try:
                k = int(payload.get("k", K_DEFAULT))
            except Exception:
                self._send(400, {"error": "k must be an integer"})
                return
            if not isinstance(vectors, list) or not vectors:
                self._send(400, {"error": "vectors must be a non-empty list"})
                return
            arr = np.asarray(vectors, dtype=np.float64)
            if arr.ndim == 1:
                arr = arr.reshape(1, -1)
            if arr.ndim != 2 or arr.shape[1] != searcher.d or not np.isfinite(arr).all():
                self._send(400, {"error": "vectors must be finite [nq, %d]" % searcher.d})
                return
            if k < 1 or k > searcher.n:
                self._send(400, {"error": "k must be in [1, %d]" % searcher.n})
                return
            try:
                idx, dist = searcher.search(arr, k=k)
            except Exception as exc:
                self._send(500, {"error": "search failed: %s" % exc})
                return
            self._send(200, {
                "indices": idx.tolist(),
                "squared_distances": dist.tolist(),
                "k": k,
                "nq": int(arr.shape[0]),
                "ntotal": int(searcher.n),
                "dim": int(searcher.d),
                "metric": "l2_squared",
                "exact": True,
            })

    return SearchHandler


def cmd_serve(args):
    from http.server import ThreadingHTTPServer

    torch = require_cuda()
    meta, vec_path = load_index(args.index)
    log("serve: loading %s ..." % vec_path)
    base = np.load(vec_path, mmap_mode="r")
    searcher = ExactL2Index(np.asarray(base, dtype=base.dtype), device=torch.device("cuda"))
    handler = make_handler(searcher, meta)
    httpd = ThreadingHTTPServer((args.host, int(args.port)), handler)
    httpd.daemon_threads = True
    port = httpd.server_address[1]

    def _shutdown(signum, _frame):
        log("received signal %d, shutting down" % signum)
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    log("READY serving on http://%s:%d (ntotal=%d dim=%d device=%s)"
        % (args.host, port, searcher.n, searcher.d, searcher.device_name))
    try:
        httpd.serve_forever(poll_interval=0.2)
    finally:
        httpd.server_close()
        if args.output:
            try:
                os.makedirs(os.path.abspath(args.output), exist_ok=True)
                write_json(os.path.join(os.path.abspath(args.output), "serve_run.json"), {
                    "task_id": TASK_ID,
                    "mode": "serve",
                    "timestamp_utc": utcnow(),
                    "host": args.host,
                    "port": int(port),
                    "index": {"path": os.path.abspath(args.index), "ntotal": int(searcher.n),
                              "dim": int(searcher.d)},
                    "cuda": gpu_info(torch),
                })
            except Exception as exc:
                warn("could not write serve run record: %s" % exc)
    log("serve: stopped")
    return 0


# ------------------------------------------------------------------ doctor
def cmd_doctor(args):
    inp = os.path.abspath(args.input)
    missing, notes = [], {}
    checks = {}

    checks["input_dir"] = os.path.isdir(inp)
    if not checks["input_dir"]:
        missing.append("input directory '%s'" % inp)
        notes["input_dir"] = inp

    for name in ("base.npy", "queries.npy", "manifest.json"):
        p = os.path.join(inp, name)
        ok = os.path.isfile(p)
        checks[name] = ok
        if not ok:
            missing.append("input file '%s'" % p)

    # hash check against manifest (only when both present)
    if checks.get("manifest.json") and checks.get("base.npy") and checks.get("queries.npy"):
        try:
            manifest = read_json(os.path.join(inp, "manifest.json"))
            declared = manifest.get("files") or {}
            for name in ("base.npy", "queries.npy"):
                actual = sha256_file(os.path.join(inp, name))
                expected = declared.get(name)
                if expected and expected != actual:
                    missing.append("sha256 mismatch for %s (expected %s, got %s)" % (name, expected, actual))
                else:
                    notes.setdefault("sha256", {})[name] = actual
        except Exception as exc:
            missing.append("manifest.json unreadable: %s" % exc)

    # shapes
    for name in ("base.npy", "queries.npy"):
        p = os.path.join(inp, name)
        if checks.get(name):
            try:
                a = np.load(p, mmap_mode="r")
                notes[name] = {"shape": list(a.shape), "dtype": str(a.dtype)}
                if a.ndim != 2:
                    missing.append("%s is not 2-D (shape %s)" % (name, a.shape))
                del a
            except Exception as exc:
                missing.append("%s unreadable: %s" % (name, exc))

    checks["numpy"] = True
    try:
        import numpy as _np  # noqa: F401
        notes["numpy_version"] = np.__version__
    except Exception as exc:
        checks["numpy"] = False
        missing.append("numpy import failed: %s" % exc)

    checks["torch"] = False
    checks["cuda"] = False
    try:
        import torch
        checks["torch"] = True
        notes["torch_version"] = torch.__version__
        if torch.cuda.is_available():
            checks["cuda"] = True
            notes["cuda"] = gpu_info(torch)
            try:
                t = torch.zeros(1, device="cuda")
                torch.cuda.synchronize()
                del t
            except Exception as exc:
                checks["cuda"] = False
                missing.append("CUDA allocation failed: %s" % exc)
        else:
            missing.append("torch.cuda.is_available() is False (a real CUDA device is required)")
    except Exception as exc:
        missing.append("torch import failed: %s" % exc)

    # writable workspace
    try:
        probe = os.path.join(os.path.abspath(args.output_dir), ".e05_write_probe")
        os.makedirs(os.path.dirname(probe), exist_ok=True)
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        checks["output_writable"] = True
    except Exception as exc:
        checks["output_writable"] = False
        missing.append("output directory not writable (%s): %s" % (args.output_dir, exc))

    report = {
        "task_id": TASK_ID,
        "mode": "doctor",
        "timestamp_utc": utcnow(),
        "input": inp,
        "checks": checks,
        "details": notes,
        "missing": missing,
        "status": "ok" if not missing else "missing",
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if missing:
        sys.stderr.write("[%s] doctor: %d missing/unavailable item(s)\n" % (TASK_ID, len(missing)))
        return EXIT_MISSING
    return 0


# -------------------------------------------------------------------- main
def build_parser():
    ap = argparse.ArgumentParser(
        prog="main.py",
        description="%s: exact CUDA L2 top-k retrieval index over native SIFT1M (debug variant)" % TASK_ID,
    )
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("build", help="build the persisted index and query every source query")
    p.add_argument("--input", required=True, help="input directory with base.npy/queries.npy")
    p.add_argument("--output", required=True, help="output directory (index/, indices.npy, squared_distances.npy, run.json)")
    p.add_argument("--k", type=int, default=K_DEFAULT)
    p.add_argument("--selfcheck-queries", type=int, default=128)
    p.add_argument("--no-selfcheck", action="store_true")

    p = sub.add_parser("query", help="query an already built index with new vectors")
    p.add_argument("--index", required=True, help="index directory produced by build")
    p.add_argument("--queries", required=True, help="path to a .npy file of query vectors")
    p.add_argument("--output", required=True, help="output directory for indices.npy/squared_distances.npy")
    p.add_argument("--k", type=int, default=K_DEFAULT)

    p = sub.add_parser("serve", help="serve /health and POST /search on CUDA")
    p.add_argument("--index", required=True)
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--output", default=None, help="optional directory for a serve run record")

    p = sub.add_parser("doctor", help="inspect inputs and dependencies without running the job")
    p.add_argument("--input", required=True)
    p.add_argument("--output-dir", default="output")

    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if not args.cmd:
        ap.print_help()
        return 0
    if args.cmd == "build":
        return cmd_build(args)
    if args.cmd == "query":
        return cmd_query(args)
    if args.cmd == "serve":
        return cmd_serve(args)
    if args.cmd == "doctor":
        return cmd_doctor(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
