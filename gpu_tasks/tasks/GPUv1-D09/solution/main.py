#!/usr/bin/env python3
"""GPUv1-D09: candidate-document reranker built on a CUDA cross-encoder.

Subcommands
-----------
run    --input INPUT_DIR --output OUTPUT_DIR
        Cross-encode every (query, passage) candidate pair of
        INPUT_DIR/requests.jsonl with /models/cross-encoder--ms-marco-MiniLM-L6-v2
        (AutoModelForSequenceClassification, max_length=256, raw logit score)
        and write OUTPUT_DIR/rankings.jsonl + OUTPUT_DIR/run.json.

serve  --port PORT
        Long-lived HTTP service exposing GET /health and
        POST /rerank {query, passages:[{id,text}]}.

The cross-encoder is instantiated once and reused for every ranking request
(no per-request reload, no stale result caching), so the service keeps working
for fresh candidate lists and after idle periods. SIGTERM/SIGINT shut the
service down cleanly (model released, status 0).
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
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

DEFAULT_MODEL_PATH = os.environ.get(
    "RERANKER_MODEL", "/models/cross-encoder--ms-marco-MiniLM-L6-v2"
)
DEFAULT_MAX_LENGTH = 256
DEFAULT_BATCH_SIZE = 32
RUN_VERSION = "1.0.0"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def id_sort_key(pid: Any) -> Tuple[int, int, str]:
    """Total order for passage ids: numeric ids numerically, others lexically."""
    s = str(pid)
    stripped = s[1:] if s.startswith("-") else s
    if stripped.isdigit():
        return (0, int(s), s)
    return (1, 0, s)


def _get_first(record: Dict[str, Any], names: Sequence[str], default: Any = None) -> Any:
    for name in names:
        if name in record and record[name] is not None:
            return record[name]
    return default


# --------------------------------------------------------------------------- #
# core reranker
# --------------------------------------------------------------------------- #
class CrossEncoderReranker:
    """Batched CUDA cross-encoder scoring (query, passage) -> raw logit."""

    def __init__(
        self,
        model_path: str = DEFAULT_MODEL_PATH,
        device: Optional[str] = None,
        max_length: int = DEFAULT_MAX_LENGTH,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self._torch = torch
        self.model_path = str(model_path)
        self.max_length = int(max_length)
        self.batch_size = max(1, int(batch_size))

        if device:
            self.device = torch.device(device)
        else:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_path, local_files_only=True
        )
        try:
            self.model = AutoModelForSequenceClassification.from_pretrained(
                self.model_path, dtype=torch.float32, local_files_only=True
            )
        except TypeError:  # older/newer kwarg name
            self.model = AutoModelForSequenceClassification.from_pretrained(
                self.model_path, torch_dtype=torch.float32, local_files_only=True
            )
        self.model.to(self.device)
        self.model.eval()
        try:
            self.model.config.use_cache = False
        except Exception:
            pass

        self.model_name_or_path = getattr(self.model.config, "_name_or_path", "") or ""
        self._lock = threading.Lock()
        self._scored_pairs = 0
        self._requests = 0

    # -- introspection ----------------------------------------------------- #
    @property
    def info(self) -> Dict[str, Any]:
        import torch
        import transformers

        dev = {
            "type": self.device.type,
            "index": self.device.index,
            "name": None,
        }
        if self.device.type == "cuda":
            dev["name"] = torch.cuda.get_device_name(self.device)
        return {
            "model_path": self.model_path,
            "model_repo": "cross-encoder/ms-marco-MiniLM-L6-v2",
            "model_revision": "233902d25c440f23af6f7d6e94d2946bac0bee0a",
            "model_class": "AutoModelForSequenceClassification",
            "hidden_activation": "identity (raw logit)",
            "max_length": self.max_length,
            "batch_size": self.batch_size,
            "device": dev,
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "scored_pairs": self._scored_pairs,
            "requests": self._requests,
        }

    # -- scoring ----------------------------------------------------------- #
    def score_pairs(self, query: str, texts: Sequence[str]) -> List[float]:
        """Raw logits for query paired with each passage text (input order)."""
        if not texts:
            return []
        torch = self._torch
        query = "" if query is None else str(query)
        out: List[float] = []
        with self._lock:  # one CUDA forward at a time; model is reused, not reloaded
            with torch.inference_mode():
                for start in range(0, len(texts), self.batch_size):
                    batch = ["" if t is None else str(t) for t in texts[start : start + self.batch_size]]
                    enc = self.tokenizer(
                        [query] * len(batch),
                        batch,
                        padding=True,
                        truncation=True,
                        max_length=self.max_length,
                        return_tensors="pt",
                    )
                    enc = {k: v.to(self.device) for k, v in enc.items()}
                    logits = self.model(**enc).logits
                    logits = logits.reshape(-1)
                    out.extend(float(x) for x in logits.detach().to("cpu").tolist())
        self._scored_pairs += len(texts)
        return out

    def rerank(self, query: str, passages: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Return ranked rows: score desc, ties broken by passage id asc."""
        normalized: List[Tuple[str, str]] = []
        seen = set()
        for p in passages:
            pid = str(_get_first(p, ("id", "passage_id", "pid"), ""))
            if pid in seen:  # never emit duplicate candidates
                continue
            seen.add(pid)
            text = _get_first(p, ("text", "passage", "content", "body"), "")
            normalized.append((pid, "" if text is None else str(text)))

        scores = self.score_pairs(query, [t for _, t in normalized])
        rows: List[Dict[str, Any]] = []
        for (pid, _), score in zip(normalized, scores):
            rows.append(
                {
                    "passage_id": pid,
                    "id": pid,
                    "raw_score": score,
                    "score": score,
                }
            )
        rows.sort(key=lambda r: (-r["raw_score"], id_sort_key(r["passage_id"])))
        for rank, row in enumerate(rows, start=1):
            row["rank"] = rank
        self._requests += 1
        return rows


# --------------------------------------------------------------------------- #
# run mode
# --------------------------------------------------------------------------- #
def load_requests(input_path: Path) -> Tuple[Path, List[Dict[str, Any]]]:
    if input_path.is_dir():
        for name in ("requests.jsonl", "requests.json", "queries.jsonl"):
            cand = input_path / name
            if cand.exists():
                input_path = cand
                break
    if not input_path.exists():
        raise FileNotFoundError(f"input file not found: {input_path}")

    records: List[Dict[str, Any]] = []
    with open(input_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return input_path, records


def normalize_request(rec: Dict[str, Any], index: int) -> Tuple[str, str, List[Dict[str, Any]]]:
    qid = str(_get_first(rec, ("query_id", "id", "qid"), index))
    query = _get_first(rec, ("query", "question", "text"), "")
    passages = _get_first(rec, ("passages", "candidates", "docs"), []) or []
    return qid, "" if query is None else str(query), list(passages)


def cmd_run(args: argparse.Namespace) -> int:
    started = time.time()
    input_path = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    input_file, records = load_requests(input_path)
    reranker = CrossEncoderReranker(
        model_path=args.model,
        device=args.device,
        max_length=args.max_length,
        batch_size=args.batch_size,
    )

    rankings_path = output_dir / "rankings.jsonl"
    lines: List[str] = []
    total_pairs = 0
    total_ranked = 0
    per_query: List[Dict[str, Any]] = []

    for index, rec in enumerate(records):
        qid, query, passages = normalize_request(rec, index)
        rows = reranker.rerank(query, passages)
        total_pairs += len(passages)
        total_ranked += len(rows)
        record_out = {
            "query_id": qid,
            "query": query,
            "num_candidates": len(rows),
            "rankings": rows,
            "passages": rows,
        }
        lines.append(json.dumps(record_out, ensure_ascii=False))
        top = rows[0] if rows else None
        per_query.append(
            {
                "query_id": qid,
                "num_candidates": len(rows),
                "top_passage_id": top["passage_id"] if top else None,
                "top_raw_score": top["raw_score"] if top else None,
            }
        )

    with open(rankings_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + ("\n" if lines else ""))

    elapsed = time.time() - started
    run_info = {
        "task": "GPUv1-D09",
        "version": RUN_VERSION,
        "mode": "run",
        "status": "ok",
        "model": {
            "path": reranker.model_path,
            "repo_id": "cross-encoder/ms-marco-MiniLM-L6-v2",
            "revision": "233902d25c440f23af6f7d6e94d2946bac0bee0a",
            "class": "AutoModelForSequenceClassification",
            "score": "raw logit (identity activation)",
            "max_length": reranker.max_length,
            "batch_size": reranker.batch_size,
        },
        "device": reranker.info["device"],
        "environment": {
            "torch": reranker.info["torch"],
            "transformers": reranker.info["transformers"],
            "python": sys.version.split()[0],
        },
        "sorting": {
            "primary": "raw_score descending",
            "tie_break": "passage id ascending",
        },
        "input": {
            "path": str(input_file),
            "sha256": sha256_file(input_file),
            "queries": len(records),
            "candidate_pairs": total_pairs,
        },
        "output": {
            "rankings_path": str(rankings_path),
            "queries": len(lines),
            "ranked_candidates": total_ranked,
            "sha256": sha256_file(rankings_path),
        },
        "counts": {
            "queries": len(records),
            "passages": total_pairs,
            "ranked": total_ranked,
        },
        "per_query": per_query,
        "timing": {
            "started_utc": utc_now(),
            "elapsed_sec": round(elapsed, 4),
        },
    }
    run_path = output_dir / "run.json"
    with open(run_path, "w", encoding="utf-8") as fh:
        json.dump(run_info, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print(
        f"[run] {len(records)} queries / {total_pairs} candidate pairs scored on "
        f"{reranker.info['device']['type']} in {elapsed:.3f}s -> {rankings_path}"
    )
    return 0


# --------------------------------------------------------------------------- #
# serve mode
# --------------------------------------------------------------------------- #
class RerankHandler(BaseHTTPRequestHandler):
    server_version = "GPUv1-D09-reranker/" + RUN_VERSION
    protocol_version = "HTTP/1.1"
    reranker: CrossEncoderReranker = None  # set by serve()

    # -- plumbing ---------------------------------------------------------- #
    def log_message(self, fmt: str, *a: Any) -> None:  # keep stderr tidy
        sys.stderr.write("[serve] %s - %s\n" % (self.address_string(), fmt % a))

    def _send_json(self, code: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> Optional[Dict[str, Any]]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        raw = self.rfile.read(length) if length > 0 else b""
        if not raw:
            return None
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    # -- routes ------------------------------------------------------------ #
    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/health", "/healthz", "/"):
            info = self.reranker.info
            self._send_json(
                200,
                {
                    "status": "ok",
                    "healthy": True,
                    "model": info["model_path"],
                    "model_repo": info["model_repo"],
                    "model_class": info["model_class"],
                    "device": info["device"],
                    "max_length": info["max_length"],
                    "requests_served": info["requests"],
                    "pairs_scored": info["scored_pairs"],
                },
            )
        else:
            self._send_json(404, {"error": "not found", "path": path})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/rerank":
            self._send_json(404, {"error": "not found", "path": path})
            return
        body = self._read_json()
        if body is None:
            self._send_json(400, {"error": "invalid JSON body"})
            return
        query = _get_first(body, ("query", "question", "text"), None)
        passages = _get_first(body, ("passages", "candidates", "docs"), None)
        if query is None or not isinstance(query, str):
            self._send_json(400, {"error": "field 'query' (string) is required"})
            return
        if not isinstance(passages, list):
            self._send_json(400, {"error": "field 'passages' (list) is required"})
            return
        for p in passages:
            if not isinstance(p, dict) or "id" not in p:
                self._send_json(400, {"error": "each passage needs an 'id' and 'text'"})
                return
        try:
            rows = self.reranker.rerank(query, passages)
        except Exception as exc:  # pragma: no cover - defensive
            self._send_json(500, {"error": "rerank failed", "detail": str(exc)})
            return
        self._send_json(
            200,
            {
                "status": "ok",
                "query": query,
                "num_candidates": len(rows),
                "rankings": rows,
                "results": rows,
                "passages": rows,
                "model": self.reranker.model_path,
                "max_length": self.reranker.max_length,
            },
        )


def cmd_serve(args: argparse.Namespace) -> int:
    reranker = CrossEncoderReranker(
        model_path=args.model,
        device=args.device,
        max_length=args.max_length,
        batch_size=args.batch_size,
    )
    RerankHandler.reranker = reranker

    httpd = ThreadingHTTPServer((args.host, args.port), RerankHandler)
    httpd.daemon_threads = True
    stopping = threading.Event()

    def _shutdown(signum: int, _frame: Any) -> None:
        if stopping.is_set():
            return
        stopping.set()
        sys.stderr.write(f"[serve] signal {signum}: shutting down\n")
        sys.stderr.flush()
        # shutdown() must run off the serve_forever() thread.
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _shutdown)
        except (ValueError, OSError):  # not on main thread
            pass

    info = reranker.info
    print(
        f"[serve] ready on http://{args.host}:{args.port} | model={info['model_path']} | "
        f"device={info['device']['type']} | max_length={info['max_length']}",
        flush=True,
    )
    try:
        httpd.serve_forever(poll_interval=0.2)
    finally:
        httpd.server_close()
        reranker.model = None
        if reranker._torch.cuda.is_available():
            try:
                reranker._torch.cuda.empty_cache()
            except Exception:
                pass
        print("[serve] stopped cleanly", flush=True)
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py", description="GPUv1-D09 cross-encoder candidate reranker"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--model", default=DEFAULT_MODEL_PATH, help="local cross-encoder path")
        p.add_argument("--device", default=None, help="cuda / cuda:0 / cpu (default: auto)")
        p.add_argument("--max-length", type=int, default=DEFAULT_MAX_LENGTH)
        p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)

    run_p = sub.add_parser("run", help="rerank an input requests.jsonl")
    run_p.add_argument("--input", required=True, help="input directory or requests.jsonl")
    run_p.add_argument("--output", required=True, help="output directory")
    common(run_p)
    run_p.set_defaults(func=cmd_run)

    serve_p = sub.add_parser("serve", help="HTTP reranking service")
    serve_p.add_argument("--port", type=int, required=True)
    serve_p.add_argument("--host", default=os.environ.get("RERANKER_HOST", "0.0.0.0"))
    common(serve_p)
    serve_p.set_defaults(func=cmd_serve)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
