#!/usr/bin/env python3
"""GPUv1-D02: GovReport summarization with Qwen2.5-0.5B-Instruct on CUDA.

Subcommands
-----------
run    --input input --output output [--serve] [--port N] [--host H]
infer  --input input/requests.jsonl --output output/reloaded.jsonl
serve  --input input --output output [--port N] [--host H]

All generation is deterministic greedy decoding over a fixed chat-template
prompt.  The document is tokenized first and the first ``--max-input-tokens``
tokens are kept; ``truncated`` records whether tokens were dropped.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import torch  # noqa: E402
from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: E402

DEFAULT_MODEL_PATH = "/models/Qwen--Qwen2.5-0.5B-Instruct"
DEFAULT_MODEL_REPO = "Qwen/Qwen2.5-0.5B-Instruct"
DEFAULT_MAX_INPUT_TOKENS = 2048
DEFAULT_MAX_NEW_TOKENS = 128

# A private-use code point used only as a split marker in the chat template
# text; it never appears in real GovReport text.
MARKER = "\ue000"
SYSTEM_PROMPT = (
    "You are a careful assistant that writes accurate, readable summaries of "
    "long U.S. government reports."
)
USER_TEMPLATE = (
    "Write a concise, faithful summary of the following U.S. government report "
    "in 3 to 5 sentences. Keep the main topic, key findings, and any "
    "recommendations stated in the report.\n\n"
    "Report:\n" + MARKER + "\n\nSummary:"
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def read_jsonl(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:  # pragma: no cover
                raise SystemExit(f"bad JSON on {path}:{lineno}: {exc}")
            if "id" not in obj or "document" not in obj:
                raise SystemExit(f"missing id/document on {path}:{lineno}")
            rows.append({"id": str(obj["id"]), "document": str(obj["document"])})
    return rows


def write_jsonl(path: str, rows: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def write_json(path: str, obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def model_revision(model_path: str) -> str:
    """Return the real revision recorded in the local model asset lock."""
    lock = os.path.join(model_path, "asset_lock.json")
    if os.path.isfile(lock):
        try:
            with open(lock, "r", encoding="utf-8") as fh:
                return str(json.load(fh).get("revision", "unknown"))
        except Exception:
            pass
    cfg = os.path.join(model_path, "config.json")
    if os.path.isfile(cfg):
        try:
            with open(cfg, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            return str(raw.get("_name_or_path", "local")) + "@" + str(
                os.path.getmtime(cfg)
            )
        except Exception:
            pass
    return "unknown"


def free_port(host: str, port: int) -> int:
    if port != 0:
        return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


# --------------------------------------------------------------------------- #
# summarizer
# --------------------------------------------------------------------------- #
class Summarizer:
    def __init__(
        self,
        model_path: str = DEFAULT_MODEL_PATH,
        device: str = "cuda",
        max_input_tokens: int = DEFAULT_MAX_INPUT_TOKENS,
        max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
    ) -> None:
        self.model_path = model_path
        self.device = device
        self.max_input_tokens = int(max_input_tokens)
        self.max_new_tokens = int(max_new_tokens)
        self.lock = threading.Lock()

        if device.startswith("cuda"):
            if not torch.cuda.is_available():
                raise RuntimeError("CUDA requested but torch.cuda.is_available() is False")
            self.device_name = torch.cuda.get_device_name(0)
        else:
            self.device_name = device

        t0 = time.perf_counter()
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_path, local_files_only=True, trust_remote_code=False
        )
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        load_kwargs: Dict[str, Any] = {"local_files_only": True, "trust_remote_code": False}
        try:
            self.model = AutoModelForCausalLM.from_pretrained(
                model_path, dtype=torch.bfloat16, **load_kwargs
            )
        except TypeError:
            self.model = AutoModelForCausalLM.from_pretrained(
                model_path, torch_dtype=torch.bfloat16, **load_kwargs
            )
        self.model.to(device)
        self.model.eval()
        self.model.config.use_cache = True
        if device.startswith("cuda"):
            torch.cuda.synchronize()
        self.load_ms = (time.perf_counter() - t0) * 1000.0
        self.dtype = str(next(self.model.parameters()).dtype)

        self._build_prompt_parts()

    # -- prompt ------------------------------------------------------------ #
    def _build_prompt_parts(self) -> None:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_TEMPLATE},
        ]
        text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        if text.count(MARKER) != 1:
            raise RuntimeError("prompt marker is not unique in chat template")
        head, tail = text.split(MARKER)
        self.head_ids = self.tokenizer(head, add_special_tokens=False)["input_ids"]
        self.tail_ids = self.tokenizer(tail, add_special_tokens=False)["input_ids"]
        self.prompt_template = text.replace(MARKER, "{DOCUMENT}")

    # -- inference --------------------------------------------------------- #
    def summarize(self, document: str) -> Dict[str, Any]:
        tok_t0 = time.perf_counter()
        doc_ids = self.tokenizer(document, add_special_tokens=False)["input_ids"]
        raw_count = len(doc_ids)
        truncated = raw_count > self.max_input_tokens
        doc_ids = doc_ids[: self.max_input_tokens]
        input_ids = self.head_ids + doc_ids + self.tail_ids
        tokenize_ms = (time.perf_counter() - tok_t0) * 1000.0

        input_tensor = torch.tensor([input_ids], dtype=torch.long, device=self.device)
        attention_mask = torch.ones_like(input_tensor)
        gen_kwargs = dict(
            max_new_tokens=self.max_new_tokens,
            do_sample=False,
            num_beams=1,
            repetition_penalty=1.0,
            use_cache=True,
            pad_token_id=self.tokenizer.pad_token_id,
            eos_token_id=self.tokenizer.eos_token_id,
        )
        with self.lock, torch.inference_mode():
            if self.device.startswith("cuda"):
                start_evt = torch.cuda.Event(enable_timing=True)
                end_evt = torch.cuda.Event(enable_timing=True)
                start_evt.record()
                output = self.model.generate(input_tensor, attention_mask=attention_mask, **gen_kwargs)
                end_evt.record()
                torch.cuda.synchronize()
                generate_ms = float(start_evt.elapsed_time(end_evt))
            else:
                t1 = time.perf_counter()
                output = self.model.generate(input_tensor, attention_mask=attention_mask, **gen_kwargs)
                generate_ms = (time.perf_counter() - t1) * 1000.0

        new_ids = output[0][len(input_ids):].tolist()
        summary = self.tokenizer.decode(new_ids, skip_special_tokens=True).strip()
        return {
            "summary": summary,
            "token_ids": [int(t) for t in new_ids],
            "input_token_count": len(doc_ids),
            "prompt_token_count": len(input_ids),
            "original_document_token_count": raw_count,
            "truncated": bool(truncated),
            "num_new_tokens": len(new_ids),
            "timings_ms": {
                "tokenize": tokenize_ms,
                "generate": generate_ms,
                "total": tokenize_ms + generate_ms,
            },
        }

    def release(self) -> None:
        try:
            if self.device.startswith("cuda"):
                torch.cuda.empty_cache()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def make_run_meta(summarizer: Summarizer, args) -> Dict[str, Any]:
    return {
        "task_id": "GPUv1-D02",
        "scale": "debug_only",
        "formal_large_tested": False,
        "model_repo": DEFAULT_MODEL_REPO,
        "model_revision": model_revision(summarizer.model_path),
        "model_path": summarizer.model_path,
        "device": summarizer.device,
        "device_name": summarizer.device_name,
        "torch_version": torch.__version__,
        "torch_cuda_version": getattr(torch.version, "cuda", None),
        "dtype": summarizer.dtype,
        "parameters": {
            "max_input_tokens": summarizer.max_input_tokens,
            "max_new_tokens": summarizer.max_new_tokens,
            "do_sample": False,
            "num_beams": 1,
            "repetition_penalty": 1.0,
            "use_cache": True,
            "chunking": "none (first max_input_tokens tokens of the report)",
            "prompt_template": summarizer.prompt_template,
            "system_prompt": SYSTEM_PROMPT,
        },
    }


def cmd_run(args) -> int:
    in_path = os.path.join(args.input, "requests.jsonl")
    if not os.path.isfile(in_path):
        in_path = args.input
    rows = read_jsonl(in_path)
    os.makedirs(args.output, exist_ok=True)
    summarizer = Summarizer(
        model_path=args.model,
        device=args.device,
        max_input_tokens=args.max_input_tokens,
        max_new_tokens=args.max_new_tokens,
    )

    results: List[Dict[str, Any]] = []
    for row in rows:
        res = summarizer.summarize(row["document"])
        results.append({"id": row["id"], **res})

    summaries = [
        {
            "id": r["id"],
            "summary": r["summary"],
            "token_ids": r["token_ids"],
            "input_token_count": r["input_token_count"],
            "truncated": r["truncated"],
            "prompt_token_count": r["prompt_token_count"],
            "original_document_token_count": r["original_document_token_count"],
            "num_new_tokens": r["num_new_tokens"],
        }
        for r in results
    ]
    write_jsonl(os.path.join(args.output, "summaries.jsonl"), summaries)

    meta = make_run_meta(summarizer, args)
    ids_in = [r["id"] for r in rows]
    ids_out = [r["id"] for r in summaries]
    per_report = [
        {"id": r["id"], "input_token_count": r["input_token_count"],
         "num_new_tokens": r["num_new_tokens"], "truncated": r["truncated"],
         **r["timings_ms"]}
        for r in results
    ]
    meta.update(
        {
            "counts": {
                "num_reports": len(rows),
                "num_summaries": len(summaries),
                "num_unique_ids": len(set(ids_out)),
                "num_truncated": sum(1 for r in summaries if r["truncated"]),
                "total_new_tokens": sum(r["num_new_tokens"] for r in summaries),
                "coverage_complete": sorted(ids_in) == sorted(ids_out)
                and len(ids_out) == len(set(ids_out)),
            },
            "ids": ids_out,
            "gpu_stage_timings_ms": {
                "model_load": summarizer.load_ms,
                "tokenize_total": sum(r["timings_ms"]["tokenize"] for r in results),
                "generate_total": sum(r["timings_ms"]["generate"] for r in results),
                "wall_total": summarizer.load_ms
                + sum(r["timings_ms"]["total"] for r in results),
            },
            "per_report": per_report,
            "peak_cuda_memory_mb": (
                torch.cuda.max_memory_allocated() / (1024 ** 2)
                if args.device.startswith("cuda")
                else 0.0
            ),
            "generated_at_unix": time.time(),
            "argv": sys.argv,
        }
    )
    write_json(os.path.join(args.output, "run.json"), meta)
    print(
        f"[run] wrote {len(summaries)} summaries to "
        f"{os.path.join(args.output, 'summaries.jsonl')}"
    )
    print(
        f"[run] coverage_complete={meta['counts']['coverage_complete']} "
        f"model_load={summarizer.load_ms:.0f}ms "
        f"generate_total={meta['gpu_stage_timings_ms']['generate_total']:.0f}ms"
    )

    if args.serve:
        rc = serve(args, summarizer)
        summarizer.release()
        return rc
    summarizer.release()
    return 0


def cmd_infer(args) -> int:
    rows = read_jsonl(args.input)
    summarizer = Summarizer(
        model_path=args.model,
        device=args.device,
        max_input_tokens=args.max_input_tokens,
        max_new_tokens=args.max_new_tokens,
    )
    out: List[Dict[str, Any]] = []
    t0 = time.perf_counter()
    for row in rows:
        res = summarizer.summarize(row["document"])
        out.append(
            {
                "id": row["id"],
                "summary": res["summary"],
                "token_ids": res["token_ids"],
                "input_token_count": res["input_token_count"],
                "truncated": res["truncated"],
                "prompt_token_count": res["prompt_token_count"],
                "original_document_token_count": res["original_document_token_count"],
                "num_new_tokens": res["num_new_tokens"],
            }
        )
    write_jsonl(args.output, out)
    summarizer.release()
    print(
        f"[infer] reloaded model revision={model_revision(args.model)} "
        f"and wrote {len(out)} rows to {args.output} "
        f"in {time.perf_counter() - t0:.1f}s"
    )
    return 0


# --------------------------------------------------------------------------- #
# HTTP service
# --------------------------------------------------------------------------- #
class _Handler(BaseHTTPRequestHandler):
    server_version = "gpuv1d02/1.0"
    protocol_version = "HTTP/1.1"

    @property
    def summarizer(self) -> Summarizer:
        return self.server.summarizer  # type: ignore[attr-defined]

    def _send(self, code: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *a) -> None:  # keep stdout clean
        sys.stderr.write("[serve] " + fmt % a + "\n")

    def do_GET(self) -> None:
        if self.path.split("?")[0] in ("/health", "/healthz"):
            s = self.summarizer
            self._send(
                200,
                {
                    "status": "ok",
                    "ready": True,
                    "device": s.device,
                    "device_name": s.device_name,
                    "cuda": torch.cuda.is_available(),
                    "model_repo": DEFAULT_MODEL_REPO,
                    "model_revision": model_revision(s.model_path),
                },
            )
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path.split("?")[0] != "/infer":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            req = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            self._send(400, {"error": f"bad request body: {exc}"})
            return
        if not isinstance(req, dict) or "document" not in req:
            self._send(400, {"error": "body must be JSON with 'document'"})
            return
        doc = req.get("document")
        if not isinstance(doc, str) or not doc.strip():
            self._send(400, {"error": "'document' must be a non-empty string"})
            return
        rid = str(req.get("id", ""))
        try:
            res = self.summarizer.summarize(doc)
        except Exception as exc:  # pragma: no cover
            self._send(500, {"error": f"inference failed: {exc}"})
            return
        res["id"] = rid
        res.pop("timings_ms", None)
        self._send(200, res)


def serve(args, summarizer: Optional[Summarizer] = None) -> int:
    own = summarizer is None
    if own:
        summarizer = Summarizer(
            model_path=args.model,
            device=args.device,
            max_input_tokens=args.max_input_tokens,
            max_new_tokens=args.max_new_tokens,
        )
    port = free_port(args.host, args.port)
    httpd = ThreadingHTTPServer((args.host, port), _Handler)
    httpd.daemon_threads = True
    httpd.summarizer = summarizer  # type: ignore[attr-defined]

    stop = threading.Event()

    def _shutdown(signum, _frame):
        sys.stderr.write(f"[serve] received signal {signum}, shutting down\n")
        stop.set()
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    meta = make_run_meta(summarizer, args) if not hasattr(args, "output") else make_run_meta(summarizer, args)
    meta.update(
        {
            "serve": {"host": args.host, "port": port, "ready": True,
                      "active": True, "pid": os.getpid(),
                      "ready_at_unix": time.time()},
            "readiness": "true only after real CUDA model load completed",
        }
    )
    if getattr(args, "output", None):
        os.makedirs(args.output, exist_ok=True)
        write_json(os.path.join(args.output, "serve.json"), meta)

    print(f"[serve] ready on http://{args.host}:{port} (device={summarizer.device_name})", flush=True)
    try:
        httpd.serve_forever(poll_interval=0.25)
    finally:
        httpd.server_close()
        if getattr(args, "output", None):
            meta["serve"]["active"] = False
            meta["serve"]["stopped_at_unix"] = time.time()
            write_json(os.path.join(args.output, "serve.json"), meta)
        if own:
            summarizer.release()
        print("[serve] stopped", flush=True)
    return 0


def cmd_serve(args) -> int:
    return serve(args, None)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="GPUv1-D02 GovReport summarization service")
    p.add_argument("command", choices=["run", "infer", "serve"])
    p.add_argument("--input", default="input")
    p.add_argument("--output", default="output")
    p.add_argument("--model", default=DEFAULT_MODEL_PATH)
    p.add_argument("--device", default="cuda")
    p.add_argument("--max-input-tokens", type=int, default=DEFAULT_MAX_INPUT_TOKENS)
    p.add_argument("--max-new-tokens", type=int, default=DEFAULT_MAX_NEW_TOKENS)
    p.add_argument("--serve", action="store_true", help="after 'run', start HTTP service")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        return cmd_run(args)
    if args.command == "infer":
        return cmd_infer(args)
    if args.command == "serve":
        return cmd_serve(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
