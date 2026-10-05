#!/usr/bin/env python
"""GPUv1-D08 - multilingual document embeddings (encode) + resident CUDA HTTP encoder (serve).

Pipeline (single code path shared by both subcommands):
    raw text -> original model tokenizer (max_length=128, truncation=True,
    padding to longest in batch) -> Transformer encoder (real CUDA forward)
    -> attention-mask mean pooling -> L2 normalization -> float32 vector.

Only `transformers` + `torch` + `numpy` (stdlib http.server for the service)
are used; the `sentence-transformers` package is intentionally not required.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import signal
import sys
import threading
import time
from typing import Dict, List, Sequence, Tuple

import numpy as np
import torch
import torch.nn.functional as F
from transformers import AutoConfig, AutoModel, AutoTokenizer

DEFAULT_MODEL = "/models/sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_MAX_LENGTH = 128
DEFAULT_BATCH_SIZE = 32
MODEL_REPO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MODEL_REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def hash_model_dir(model_path: str) -> Dict[str, object]:
    """Hash the model artifacts actually consumed (weights + config + tokenizer)."""
    files = sorted(
        f
        for f in os.listdir(model_path)
        if os.path.isfile(os.path.join(model_path, f))
    )
    per_file = {f: sha256_file(os.path.join(model_path, f)) for f in files}
    h = hashlib.sha256()
    for name in files:
        h.update(name.encode("utf-8"))
        h.update(b"\0")
        h.update(per_file[name].encode("ascii"))
        h.update(b"\n")
    weights = per_file.get("model.safetensors") or per_file.get("pytorch_model.bin")
    return {
        "path": os.path.abspath(model_path),
        "aggregate_sha256": h.hexdigest(),
        "weights_file": "model.safetensors" if "model.safetensors" in per_file else None,
        "weights_sha256": weights,
        "files": per_file,
    }


def read_jsonl(path: str) -> List[dict]:
    rows: List[dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:  # pragma: no cover
                raise ValueError(f"invalid JSON on line {lineno} of {path}: {exc}") from exc
    return rows


def document_text(row: dict, template: str) -> str:
    """Compose the string that is embedded for a document.

    Default template ``{text}`` embeds the paragraph body verbatim, which is the
    convention declared in output/run.json ("parameters.text_template").
    """
    return template.format(
        id=row.get("id", ""),
        lang=row.get("lang", ""),
        title=row.get("title", ""),
        text=row.get("text", ""),
    )


# --------------------------------------------------------------------------- #
# encoder
# --------------------------------------------------------------------------- #
class Encoder:
    """Thin wrapper around the original tokenizer + Transformer encoder."""

    def __init__(
        self,
        model_path: str = DEFAULT_MODEL,
        device: str = "cuda",
        max_length: int = DEFAULT_MAX_LENGTH,
        batch_size: int = DEFAULT_BATCH_SIZE,
        template: str = "{text}",
    ) -> None:
        if device.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError("CUDA requested but torch.cuda.is_available() is False")
        self.model_path = model_path
        self.max_length = int(max_length)
        self.batch_size = int(batch_size)
        self.template = template
        self.device = torch.device(device)
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModel.from_pretrained(model_path, dtype=torch.float32)
        self.model.eval().to(self.device)
        for p in self.model.parameters():
            p.requires_grad_(False)
        self.hidden_size = int(self.model.config.hidden_size)
        self._lock = threading.Lock()

    # -- introspection ----------------------------------------------------- #
    @property
    def device_name(self) -> str:
        if self.device.type == "cuda":
            return torch.cuda.get_device_name(self.device)
        return platform.processor() or "cpu"

    def info(self) -> Dict[str, object]:
        return {
            "model": MODEL_REPO,
            "model_path": os.path.abspath(self.model_path),
            "device": str(self.device),
            "device_name": self.device_name,
            "dtype": "float32",
            "max_length": self.max_length,
            "pooling": "attention_mask_mean",
            "normalize": "l2",
            "embedding_dim": self.hidden_size,
        }

    # -- core -------------------------------------------------------------- #
    def _encode_batch(self, texts: Sequence[str]) -> np.ndarray:
        batch = self.tokenizer(
            list(texts),
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )
        batch = {k: v.to(self.device, non_blocking=True) for k, v in batch.items()}
        with torch.inference_mode():
            hidden = self.model(**batch).last_hidden_state
            mask = batch["attention_mask"].unsqueeze(-1).to(hidden.dtype)
            summed = (hidden * mask).sum(dim=1)
            counts = mask.sum(dim=1).clamp(min=1e-9)
            pooled = summed / counts
            normalized = F.normalize(pooled, p=2, dim=-1)
        return normalized.to(torch.float32).cpu().numpy()

    def encode(self, texts: Sequence[str], batch_size: int | None = None) -> np.ndarray:
        if len(texts) == 0:
            return np.zeros((0, self.hidden_size), dtype=np.float32)
        bs = int(batch_size or self.batch_size)
        chunks = [self._encode_batch(texts[i : i + bs]) for i in range(0, len(texts), bs)]
        return np.concatenate(chunks, axis=0).astype(np.float32, copy=False)

    def encode_documents(self, rows: Sequence[dict]) -> np.ndarray:
        return self.encode([document_text(r, self.template) for r in rows])

    def token_lengths(self, texts: Sequence[str]) -> List[int]:
        encoded = self.tokenizer(
            list(texts), truncation=False, add_special_tokens=True
        )["input_ids"]
        return [len(ids) for ids in encoded]

    # -- lifecycle --------------------------------------------------------- #
    def close(self) -> None:
        try:
            self.model.to("cpu")
        except Exception:
            pass
        self.model = None  # type: ignore[assignment]
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()


# --------------------------------------------------------------------------- #
# encode subcommand
# --------------------------------------------------------------------------- #
def cmd_encode(args: argparse.Namespace) -> int:
    t_start = time.perf_counter()
    out_dir = os.path.abspath(args.output)
    os.makedirs(out_dir, exist_ok=True)

    t0 = time.perf_counter()
    rows = read_jsonl(args.input)
    src_hash = sha256_file(args.input)
    t_read = time.perf_counter() - t0
    if not rows:
        raise SystemExit("input contains no documents")

    texts = [document_text(r, args.text_template) for r in rows]
    ids = [r["id"] for r in rows]

    t0 = time.perf_counter()
    model_meta = hash_model_dir(args.model)
    t_hash = time.perf_counter() - t0

    t0 = time.perf_counter()
    encoder = Encoder(
        model_path=args.model,
        device=args.device,
        max_length=args.max_length,
        batch_size=args.batch_size,
        template=args.text_template,
    )
    t_load = time.perf_counter() - t0

    if args.device.startswith("cuda"):
        torch.cuda.synchronize()
    t0 = time.perf_counter()
    embeddings = encoder.encode(texts)
    if args.device.startswith("cuda"):
        torch.cuda.synchronize()
    t_encode = time.perf_counter() - t0

    # independent re-encoding of the identical texts (cosine stability report)
    t0 = time.perf_counter()
    check = encoder.encode(texts)
    if args.device.startswith("cuda"):
        torch.cuda.synchronize()
    t_recheck = time.perf_counter() - t0
    cos = np.einsum("ij,ij->i", embeddings, check)

    lengths = encoder.token_lengths(texts)
    arr = np.asarray(lengths, dtype=np.int64)
    truncated = int((arr > args.max_length).sum())

    emb_path = os.path.join(out_dir, "embeddings.npy")
    ids_path = os.path.join(out_dir, "document_ids.json")
    run_path = os.path.join(out_dir, "run.json")

    np.save(emb_path, embeddings.astype(np.float32, copy=False))
    with open(ids_path, "w", encoding="utf-8") as fh:
        json.dump(ids, fh, ensure_ascii=False, indent=0)
        fh.write("\n")

    t_total = time.perf_counter() - t_start
    run = {
        "task_id": "GPUv1-D08",
        "scale": "debug_only",
        "formal_large_tested": False,
        "model_repo": MODEL_REPO,
        "model_revision": MODEL_REVISION,
        "model_path": os.path.abspath(args.model),
        "model_hash": model_meta,
        "source": {
            "path": os.path.abspath(args.input),
            "sha256": src_hash,
            "num_documents": len(rows),
            "langs": sorted({r.get("lang", "") for r in rows}),
            "order_preserved": True,
        },
        "parameters": {
            "text_field": "text",
            "text_template": args.text_template,
            "max_length": int(args.max_length),
            "padding": "longest_in_batch",
            "truncation": True,
            "pooling": "attention_mask_mean",
            "normalize": "l2",
            "batch_size": int(args.batch_size),
            "dtype": "float32",
            "device": str(encoder.device),
            "device_name": encoder.device_name,
            "do_lower_case": False,
            "library": "transformers.AutoModel/AutoTokenizer (no sentence-transformers package)",
        },
        "overrides": {
            "text_template": args.text_template != "{text}",
            "max_length_vs_model_default": {
                "model_max_seq_length": 128,
                "used": int(args.max_length),
            },
            "notes": (
                "Transformer tokenizer/encoder + attention-mask mean pooling + L2 "
                "normalization; no sentence-transformers pipeline module is used."
            ),
        },
        "coverage": {
            "texts_total": len(texts),
            "texts_truncated_at_max_length": truncated,
            "covered_fraction": float((len(texts) - truncated) / len(texts)),
            "token_length": {
                "min": int(arr.min()),
                "mean": float(arr.mean()),
                "median": float(np.median(arr)),
                "p95": float(np.percentile(arr, 95)),
                "max": int(arr.max()),
            },
        },
        "timings_sec": {
            "read_input": round(t_read, 6),
            "hash_model": round(t_hash, 6),
            "model_load": round(t_load, 6),
            "encode_documents": round(t_encode, 6),
            "reencode_check": round(t_recheck, 6),
            "total_sync": round(t_total, 6),
        },
        "throughput_docs_per_sec": round(len(texts) / max(t_encode, 1e-9), 3),
        "determinism_check": {
            "method": "same-process repeat encode of identical texts",
            "min_cosine": float(cos.min()),
            "mean_cosine": float(cos.mean()),
        },
        "outputs": {
            "embeddings.npy": {
                "shape": list(embeddings.shape),
                "dtype": "float32",
                "sha256": sha256_file(emb_path),
            },
            "document_ids.json": {
                "count": len(ids),
                "sha256": sha256_file(ids_path),
            },
        },
        "environment": {
            "python": sys.version.split()[0],
            "torch": torch.__version__,
            "transformers": __import__("transformers").__version__,
            "numpy": np.__version__,
            "cuda_available": torch.cuda.is_available(),
            "cuda_device_name": encoder.device_name,
            "torch_cuda_version": torch.version.cuda,
        },
    }
    with open(run_path, "w", encoding="utf-8") as fh:
        json.dump(run, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    encoder.close()
    print(
        json.dumps(
            {
                "ok": True,
                "output": out_dir,
                "documents": len(ids),
                "embeddings_shape": list(embeddings.shape),
                "min_self_cosine": float(cos.min()),
                "total_sync_sec": run["timings_sec"]["total_sync"],
                "device": run["parameters"]["device"],
            },
            ensure_ascii=False,
        )
    )
    return 0


# --------------------------------------------------------------------------- #
# serve subcommand
# --------------------------------------------------------------------------- #
def make_handler(encoder: Encoder, ready_flag: Dict[str, object]):
    from http.server import BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        server_version = "GPUv1D08/1.0"
        protocol_version = "HTTP/1.1"

        # -- plumbing -------------------------------------------------- #
        def log_message(self, fmt, *a):  # quieter but still observable
            sys.stderr.write("[serve] " + (fmt % a) + "\n")

        def _send(self, code: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            if not raw:
                return {}
            try:
                return json.loads(raw.decode("utf-8"))
            except Exception as exc:
                raise ValueError(f"invalid JSON body: {exc}") from exc

        # -- routes ---------------------------------------------------- #
        def do_GET(self):
            path = self.path.split("?", 1)[0].rstrip("/") or "/"
            if path in ("/health", "/healthz", "/"):
                info = encoder.info()
                self._send(
                    200,
                    {
                        "status": "ok" if ready_flag.get("ready") else "starting",
                        "ready": bool(ready_flag.get("ready")),
                        "model": info["model"],
                        "device": info["device"],
                        "device_name": info["device_name"],
                        "cuda": torch.cuda.is_available(),
                        "dtype": info["dtype"],
                        "max_length": info["max_length"],
                        "embedding_dim": info["embedding_dim"],
                        "pooling": info["pooling"],
                        "normalize": info["normalize"],
                        "pid": os.getpid(),
                        "uptime_sec": round(time.time() - float(ready_flag.get("t0", time.time())), 3),
                    },
                )
            else:
                self._send(404, {"error": "not found", "path": path})

        def do_POST(self):
            path = self.path.split("?", 1)[0].rstrip("/")
            if path != "/encode":
                self._send(404, {"error": "not found", "path": path})
                return
            try:
                payload = self._read_json()
                texts = payload.get("texts")
                if not isinstance(texts, list) or not all(isinstance(t, str) for t in texts):
                    raise ValueError("body must be {\"texts\": [str, ...]}")
                t0 = time.perf_counter()
                with encoder._lock:  # one CUDA context, serialized forwards
                    vecs = encoder.encode(texts)
                if torch.cuda.is_available():
                    torch.cuda.synchronize()
                dt = time.perf_counter() - t0
                self._send(
                    200,
                    {
                        "model": MODEL_REPO,
                        "device": str(encoder.device),
                        "normalized": True,
                        "pooling": "attention_mask_mean",
                        "max_length": encoder.max_length,
                        "count": int(vecs.shape[0]),
                        "dim": int(vecs.shape[1]) if vecs.ndim == 2 else 0,
                        "elapsed_sec": round(dt, 6),
                        "embeddings": vecs.astype(np.float64).tolist(),
                    },
                )
            except ValueError as exc:
                self._send(400, {"error": str(exc)})
            except Exception as exc:  # pragma: no cover - defensive
                self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

    return Handler


def cmd_serve(args: argparse.Namespace) -> int:
    from http.server import ThreadingHTTPServer

    ready_flag: Dict[str, object] = {"ready": False, "t0": time.time()}
    print(
        json.dumps({"event": "loading", "model": args.model, "device": args.device}),
        flush=True,
    )
    t0 = time.perf_counter()
    encoder = Encoder(
        model_path=args.model,
        device=args.device,
        max_length=args.max_length,
        batch_size=args.batch_size,
    )
    with encoder._lock:
        encoder.encode(["\u0645\u0627\u0621", "\u0939\u093f\u0928\u094d\u0926\u0940"])  # real CUDA warm-up
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    ready_flag["ready"] = True
    load_sec = time.perf_counter() - t0

    handler = make_handler(encoder, ready_flag)
    httpd = ThreadingHTTPServer((args.host, args.port), handler)
    httpd.daemon_threads = True
    shutdown_started = threading.Event()

    def _graceful(signum, _frame):
        if shutdown_started.is_set():
            return
        shutdown_started.set()
        print(json.dumps({"event": "signal", "signum": int(signum)}), flush=True)
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _graceful)
    signal.signal(signal.SIGINT, _graceful)

    bound_port = httpd.server_address[1]
    print(
        json.dumps(
            {
                "event": "ready",
                "port": int(bound_port),
                "host": args.host,
                "device": str(encoder.device),
                "device_name": encoder.device_name,
                "model": MODEL_REPO,
                "load_sec": round(load_sec, 6),
                "pid": os.getpid(),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    try:
        httpd.serve_forever(poll_interval=0.2)
    finally:
        httpd.server_close()
        encoder.close()
        print(json.dumps({"event": "stopped", "pid": os.getpid()}), flush=True)
    return 0


# --------------------------------------------------------------------------- #
# cli
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="main.py", description="GPUv1-D08 document embeddings")
    sub = p.add_subparsers(dest="command", required=True)

    pe = sub.add_parser("encode", help="encode a JSONL corpus into embeddings.npy/run.json")
    pe.add_argument("--input", required=True, help="input .jsonl (id/lang/title/text)")
    pe.add_argument("--output", required=True, help="output directory")
    pe.add_argument("--model", default=DEFAULT_MODEL)
    pe.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    pe.add_argument("--max-length", type=int, default=DEFAULT_MAX_LENGTH)
    pe.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    pe.add_argument(
        "--text-template",
        default="{text}",
        help="Python format string over id/lang/title/text used as the embedded string",
    )
    pe.set_defaults(func=cmd_encode)

    ps = sub.add_parser("serve", help="resident CUDA HTTP encoder")
    ps.add_argument("--port", type=int, default=8080)
    ps.add_argument("--host", default="0.0.0.0")
    ps.add_argument("--model", default=DEFAULT_MODEL)
    ps.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    ps.add_argument("--max-length", type=int, default=DEFAULT_MAX_LENGTH)
    ps.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    ps.set_defaults(func=cmd_serve)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    torch.manual_seed(0)
    np.random.seed(0)
    if torch.cuda.is_available():
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
