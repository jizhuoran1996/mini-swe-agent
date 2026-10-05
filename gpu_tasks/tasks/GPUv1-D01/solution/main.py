#!/usr/bin/env python3
"""GPUv1-D01 (debug variant): CUDA Qasper document QA reader.

Qwen2.5-0.5B-Instruct on a real CUDA device answers eight native LongBench
Qasper questions (document <= 2048 tokens, chat template, greedy, <= 128 new
tokens).  Subcommands:

  run     --input input --output output   batch QA -> answers.jsonl + run.json
  serve   --port PORT                     resident CUDA model + /health, /infer
  doctor  --input input                   static preflight, never loads a model

Exit codes: 0 ok, 78 missing prerequisite/input, 1 runtime failure.
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
from pathlib import Path

TASK_ID = "GPUv1-D01"
MODEL_REPO = "Qwen/Qwen2.5-0.5B-Instruct"
DEFAULT_MODEL = "/models/Qwen--Qwen2.5-0.5B-Instruct"
EXPECTED_REVISION = "7ae557604adf67be50417f59c2c2f167def9a775"
EXPECTED_REQUESTS_SHA256 = "55d4fd2c2d4dcb11af9c46f9f6256deb71a26fa094d554c31b9e0591a613e334"
EXIT_OK, EXIT_FAILED, EXIT_MISSING = 0, 1, 78

# Document placeholder: survives the chat template untouched, so the prompt can
# be tokenized part-wise and truncated token-exactly without breaking the template.
DOC_SENTINEL = "\ue000DOC\ue001"
SYSTEM_PROMPT = (
    "You are a careful scientific-paper reading assistant. "
    "Answer the question using only the provided document."
)
TEMPLATE = (
    "Write a high-quality answer for the given question using only the "
    "provided search results (some of which might be irrelevant).\n\n"
    "Document:\n" + DOC_SENTINEL + "\n\nQuestion: {Q}\nAnswer:"
)

ID_KEYS = ("id", "_id", "request_id", "qid")
DOC_KEYS = ("document", "context", "doc", "passage", "text")
Q_KEYS = ("question", "input", "query")


class PrereqError(RuntimeError):
    """A required input file, package, model artifact or the CUDA device is absent."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _as_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n\n".join(_as_text(v) for v in value)
    if isinstance(value, dict):
        for key in ("text", "content", "paragraph", "body"):
            if key in value:
                return _as_text(value[key])
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def load_requests(path: Path):
    """Parse requests.jsonl.  Gold answers (if any) are deliberately never read."""
    requests = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON ({exc})") from exc
            if not isinstance(obj, dict):
                raise ValueError(f"{path}:{lineno}: expected a JSON object")
            rid = next((obj[k] for k in ID_KEYS if isinstance(obj.get(k), str) and obj[k]), None)
            question = next((obj[k] for k in Q_KEYS if isinstance(obj.get(k), str) and obj[k]), None)
            document = next((obj[k] for k in DOC_KEYS if obj.get(k) is not None), None)
            if rid is None:
                raise ValueError(f"{path}:{lineno}: no id field among {ID_KEYS}")
            if question is None or not question.strip():
                raise ValueError(f"{path}:{lineno}: no non-empty question among {Q_KEYS}")
            if document is None:
                raise ValueError(f"{path}:{lineno}: no document field among {DOC_KEYS}")
            requests.append({
                "id": rid,
                "question": question,
                "document": _as_text(document),
                "doc_sha256": hashlib.sha256(_as_text(document).encode("utf-8")).hexdigest(),
            })
    return requests


def build_input_ids(tokenizer, document: str, question: str, max_tokens: int):
    """Return (input_ids <= max_tokens, meta).

    The instruction prefix and the question tail are tokenized separately from
    the document; only document tokens are dropped (left-kept, i.e. the head of
    the paper is preserved exactly like LongBench truncation) and the question
    plus chat template are always preserved in full.
    """
    user = TEMPLATE.format(Q=question)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    if DOC_SENTINEL not in text:
        raise RuntimeError("chat template dropped the document placeholder")
    pre, post = text.split(DOC_SENTINEL, 1)
    pre_ids = tokenizer(pre, add_special_tokens=False)["input_ids"]
    post_ids = tokenizer(post, add_special_tokens=False)["input_ids"]
    doc_ids = tokenizer(document, add_special_tokens=False)["input_ids"] if document else []

    avail = int(max_tokens) - len(pre_ids) - len(post_ids)
    if avail < 0:  # pathological: template + question alone exceed the budget
        keep = max(0, int(max_tokens) - len(post_ids))
        pre_ids = pre_ids[len(pre_ids) - keep:] if keep else []
        avail = 0
    kept = doc_ids[:avail]
    input_ids = pre_ids + kept + post_ids
    meta = {
        "truncated": len(kept) < len(doc_ids),
        "doc_tokens_full": len(doc_ids),
        "doc_tokens_used": len(kept),
    }
    return input_ids, meta


def clean_answer(raw: str) -> str:
    text = raw.strip()
    for marker in ("\n\nQuestion:", "\nQuestion:", "\n\nQuestion "):
        if marker in text:
            text = text.split(marker)[0]
    if text.startswith("Question:"):
        text = text.split("\n", 1)[-1]
    return text.strip()


class Reader:
    """Resident CUDA model + tokenizer.  Real prefill/decode on every call."""

    def __init__(self, model_path, revision, max_tokens, max_new_tokens, device="cuda"):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        if not torch.cuda.is_available():
            raise PrereqError("CUDA is not available; this task requires a real CUDA device")
        torch.manual_seed(0)
        torch.cuda.manual_seed_all(0)
        self.torch = torch
        self.max_tokens = int(max_tokens)
        self.max_new_tokens = int(max_new_tokens)
        self.device = torch.device(device)

        started = time.perf_counter()
        self.tokenizer = AutoTokenizer.from_pretrained(str(model_path), revision=revision)
        try:
            self.model = AutoModelForCausalLM.from_pretrained(
                str(model_path), revision=revision, dtype=torch.bfloat16)
        except TypeError:  # older/newer signature uses torch_dtype
            self.model = AutoModelForCausalLM.from_pretrained(
                str(model_path), revision=revision, torch_dtype=torch.bfloat16)
        self.model.to(self.device)
        self.model.eval()
        self.load_seconds = time.perf_counter() - started

        self.pad_id = (self.tokenizer.pad_token_id
                       if self.tokenizer.pad_token_id is not None
                       else (self.tokenizer.eos_token_id or 0))
        self.eos_id = self.tokenizer.eos_token_id or self.pad_id
        self.dtype = str(next(self.model.parameters()).dtype).replace("torch.", "")
        self.device_name = torch.cuda.get_device_name(self.device)
        torch.cuda.reset_peak_memory_stats(self.device)

    def generate(self, document: str, question: str) -> dict:
        torch = self.torch
        input_ids, meta = build_input_ids(self.tokenizer, document, question, self.max_tokens)
        ids = torch.tensor([input_ids], dtype=torch.long, device=self.device)
        attn = torch.ones_like(ids)
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        torch.cuda.synchronize()
        wall0 = time.perf_counter()
        start.record()
        with torch.inference_mode():
            out = self.model.generate(
                input_ids=ids,
                attention_mask=attn,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
                num_beams=1,
                use_cache=True,
                pad_token_id=self.pad_id,
                eos_token_id=self.eos_id,
            )
        end.record()
        torch.cuda.synchronize()
        wall = time.perf_counter() - wall0
        new_ids = out[0, ids.shape[1]:].tolist()
        raw_text = self.tokenizer.decode(new_ids, skip_special_tokens=True)
        return {
            "input_tokens": len(input_ids),
            "truncated": bool(meta["truncated"]),
            "doc_tokens_full": meta["doc_tokens_full"],
            "doc_tokens_used": meta["doc_tokens_used"],
            "token_ids": new_ids,
            "raw_text": raw_text,
            "answer": clean_answer(raw_text),
            "new_tokens": len(new_ids),
            "gpu_ms": float(start.elapsed_time(end)),
            "wall_s": float(wall),
        }

    def env_info(self) -> dict:
        torch = self.torch
        import transformers
        return {
            "cuda_available": True,
            "device_count": torch.cuda.device_count(),
            "device_name": self.device_name,
            "device_capability": list(torch.cuda.get_device_capability(self.device)),
            "torch_version": torch.__version__,
            "transformers_version": transformers.__version__,
            "cuda_version": torch.version.cuda,
            "dtype": self.dtype,
        }

    def memory_info(self) -> dict:
        torch = self.torch
        gib = 1024 ** 3
        return {
            "peak_allocated_gib": torch.cuda.max_memory_allocated(self.device) / gib,
            "peak_reserved_gib": torch.cuda.max_memory_reserved(self.device) / gib,
        }


# --------------------------------------------------------------------------- run

def cmd_run(args) -> int:
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    in_dir = Path(args.input)
    req_path = in_dir / "requests.jsonl"
    if not req_path.is_file():
        raise PrereqError(f"missing input file: {req_path}")
    model_dir = Path(args.model)
    if not model_dir.is_dir():
        raise PrereqError(f"missing model directory: {model_dir}")

    requests = load_requests(req_path)
    if not requests:
        raise PrereqError(f"no requests parsed from {req_path}")
    print(json.dumps({"event": "loaded_requests", "count": len(requests)}), flush=True)

    started = time.time()
    reader = Reader(model_dir, args.revision, args.max_tokens, args.max_new_tokens)
    print(json.dumps({"event": "model_ready", "device": reader.device_name,
                      "dtype": reader.dtype, "load_s": reader.load_seconds}), flush=True)

    answers_path = out_dir / "answers.jsonl"
    items, documents = [], []
    total_new_tokens = 0
    gen_started = time.perf_counter()
    with open(answers_path, "w", encoding="utf-8") as fh:
        for index, req in enumerate(requests):
            res = reader.generate(req["document"], req["question"])
            record = {
                "id": req["id"],
                "answer": res["answer"],
                "raw_text": res["raw_text"],
                "token_ids": res["token_ids"],
                "input_tokens": res["input_tokens"],
                "truncated": res["truncated"],
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
            items.append({
                "id": req["id"],
                "order": index,
                "input_tokens": res["input_tokens"],
                "truncated": res["truncated"],
                "doc_tokens_full": res["doc_tokens_full"],
                "doc_tokens_used": res["doc_tokens_used"],
                "new_tokens": res["new_tokens"],
                "gpu_ms": res["gpu_ms"],
                "wall_s": res["wall_s"],
            })
            documents.append({
                "id": req["id"],
                "doc_sha256": req["doc_sha256"],
                "doc_tokens_full": res["doc_tokens_full"],
                "doc_tokens_used": res["doc_tokens_used"],
                "truncated": res["truncated"],
            })
            total_new_tokens += res["new_tokens"]
            print(json.dumps({"event": "answered", "id": req["id"],
                              "input_tokens": res["input_tokens"],
                              "new_tokens": res["new_tokens"],
                              "gpu_ms": round(res["gpu_ms"], 3)}), flush=True)
    gen_seconds = time.perf_counter() - gen_started
    session_seconds = time.time() - started

    answers_sha = sha256_file(answers_path)
    write_json(out_dir / "document_manifest.json", {
        "task_id": TASK_ID,
        "source": "input/requests.jsonl",
        "documents": documents,
    })
    write_json(out_dir / "reader_service_config.json", {
        "task_id": TASK_ID,
        "model_repo": MODEL_REPO,
        "model_revision": args.revision,
        "max_tokens": args.max_tokens,
        "max_new_tokens": args.max_new_tokens,
        "decoding": "greedy",
        "endpoints": {"GET /health": "liveness/readiness of the CUDA-resident model",
                      "POST /infer": "{id?, document, question} fresh QA request"},
        "serve_command": "python solution/main.py serve --port PORT --input input --output output",
    })
    write_json(out_dir / "reference_metric_inputs.json", {
        "task_id": TASK_ID,
        "metric": "LongBench qa_f1_score",
        "model_repo": MODEL_REPO,
        "model_revision": args.revision,
        "predictions": [{"id": it["id"], "pred": rec} for it, rec in
                        zip(items, [r["answer"] for r in _answers_from_file(answers_path)])],
        "note": "frozen input package contains no gold answers; the evaluator must score "
                "these predictions against its own labels.",
    })

    run_record = {
        "task_id": TASK_ID,
        "command": "run",
        "status": "completed",
        "scale": "debug_only",
        "formal_large_tested": False,
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
        "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": {"repo": MODEL_REPO, "revision": args.revision, "path": str(model_dir),
                  "dtype": reader.dtype, "device": "cuda",
                  "chat_template": bool(getattr(reader.tokenizer, "chat_template", None))},
        "decoding": {"strategy": "greedy", "do_sample": False, "num_beams": 1,
                     "max_new_tokens": args.max_new_tokens, "use_cache": True},
        "context": {"max_tokens": args.max_tokens,
                    "truncation": "document tokens only, head-kept; question and chat template preserved"},
        "environment": reader.env_info(),
        "inputs": {"requests.jsonl": {"path": str(req_path), "sha256": sha256_file(req_path),
                                       "count": len(requests),
                                       "expected_sha256": EXPECTED_REQUESTS_SHA256}},
        "outputs": {"answers.jsonl": {"path": str(answers_path), "sha256": answers_sha,
                                       "count": len(items)},
                    "document_manifest.json": str(out_dir / "document_manifest.json"),
                    "reader_service_config.json": str(out_dir / "reader_service_config.json"),
                    "reference_metric_inputs.json": str(out_dir / "reference_metric_inputs.json")},
        "items": items,
        "timings": {
            "model_load_s": reader.load_seconds,
            "generation_total_s": gen_seconds,
            "session_wall_s": session_seconds,
            "generated_tokens": total_new_tokens,
            "generated_tokens_per_s": (total_new_tokens / gen_seconds) if gen_seconds > 0 else None,
            "timing_source": "torch.cuda.Event around each generate() + torch.cuda.synchronize()",
        },
        "memory": reader.memory_info(),
        "reproducibility": {"torch_seed": 0, "cuda_seed": 0,
                            "note": "greedy decoding; no sampling RNG consumed"},
        "limitations": ["debug 0.5B model, eight native Qasper questions, 2048-token budget",
                        "gold answers are absent from the frozen input package, so accuracy is not "
                        "measured here; only coverage, recomputation and service behaviour are"],
    }
    write_json(out_dir / "run.json", run_record)
    print(json.dumps({"event": "run_complete", "answers": str(answers_path),
                      "count": len(items), "session_wall_s": round(session_seconds, 3)}), flush=True)
    return EXIT_OK


def _answers_from_file(path: Path):
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


# -------------------------------------------------------------------------- serve

def cmd_serve(args) -> int:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    model_dir = Path(args.model)
    if not model_dir.is_dir():
        raise PrereqError(f"missing model directory: {model_dir}")
    port = int(args.port if args.port else os.environ.get("PORT", 8080))

    reader = Reader(model_dir, args.revision, args.max_tokens, args.max_new_tokens)
    lock = threading.Lock()
    log_path = out_dir / "serve_log.jsonl"
    events_path = out_dir / "serve_events.jsonl"
    log_lock = threading.Lock()

    def append(path: Path, obj: dict) -> None:
        with log_lock:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
                fh.flush()
                os.fsync(fh.fileno())

    write_json(out_dir / "reader_service_config.json", {
        "task_id": TASK_ID,
        "model_repo": MODEL_REPO,
        "model_revision": args.revision,
        "port": port,
        "max_tokens": args.max_tokens,
        "max_new_tokens": args.max_new_tokens,
        "endpoints": {"GET /health": "readiness of the CUDA-resident model",
                      "POST /infer": "{id?, document, question}"},
    })

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "qasper-reader/1.0"

        def log_message(self, fmt, *a):  # keep stdout clean, log to stderr
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % a))

        def _send(self, code: int, obj: dict) -> None:
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path in ("/health", "/healthz"):
                self._send(200, {
                    "status": "ready",
                    "model_loaded": True,
                    "device": reader.device_name,
                    "cuda": True,
                    "dtype": reader.dtype,
                    "model_revision": args.revision,
                    "max_tokens": args.max_tokens,
                    "max_new_tokens": args.max_new_tokens,
                    "uptime_s": time.time() - started_at,
                })
            else:
                self._send(404, {"error": "not found", "path": path})

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            if path != "/infer":
                self._send(404, {"error": "not found", "path": path})
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
            except ValueError:
                self._send(400, {"error": "invalid Content-Length"})
                return
            raw = self.rfile.read(length) if length > 0 else b""
            try:
                payload = json.loads(raw.decode("utf-8")) if raw else {}
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._send(400, {"error": f"invalid JSON body: {exc}"})
                return
            if not isinstance(payload, dict):
                self._send(400, {"error": "body must be a JSON object"})
                return
            document = payload.get("document")
            question = payload.get("question")
            missing = [name for name, value in (("document", document), ("question", question))
                       if not isinstance(value, str) or not value.strip()]
            if missing:
                self._send(400, {"error": "missing or empty field(s): " + ", ".join(missing)})
                return
            rid = payload.get("id") or ("srv-" + os.urandom(6).hex())
            try:
                with lock:
                    res = reader.generate(_as_text(document), question)
            except Exception as exc:  # keep the service alive, report the failure
                self._send(500, {"error": f"{type(exc).__name__}: {exc}", "id": rid})
                return
            append(log_path, {
                "ts": time.time(), "id": rid, "request_sha256": hashlib.sha256(
                    (str(document) + "\x00" + question).encode("utf-8")).hexdigest(),
                "input_tokens": res["input_tokens"], "truncated": res["truncated"],
                "new_tokens": res["new_tokens"], "gpu_ms": res["gpu_ms"],
                "answer": res["answer"],
            })
            self._send(200, {
                "id": rid,
                "answer": res["answer"],
                "raw_text": res["raw_text"],
                "token_ids": res["token_ids"],
                "input_tokens": res["input_tokens"],
                "truncated": res["truncated"],
                "new_tokens": res["new_tokens"],
                "gpu_ms": res["gpu_ms"],
                "wall_s": res["wall_s"],
                "model_revision": args.revision,
                "fresh_request": True,
            })

    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    started_at = time.time()

    def on_signal(signum, _frame):
        append(events_path, {"event": "signal", "signum": int(signum), "ts": time.time()})
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    append(events_path, {"event": "ready", "port": port, "device": reader.device_name,
                         "model_revision": args.revision, "ts": started_at})
    print(json.dumps({"event": "ready", "port": port, "device": reader.device_name,
                      "dtype": reader.dtype, "model_revision": args.revision,
                      "load_s": reader.load_seconds}), flush=True)
    try:
        httpd.serve_forever(poll_interval=0.25)
    finally:
        httpd.server_close()
        append(events_path, {"event": "stopped", "ts": time.time(),
                             "uptime_s": time.time() - started_at})
    print(json.dumps({"event": "stopped"}), flush=True)
    return EXIT_OK


# ------------------------------------------------------------------------- doctor

def cmd_doctor(args) -> int:
    from importlib import util as importlib_util

    report = {"task_id": TASK_ID, "command": "doctor", "checks": [], "missing": [], "warnings": []}

    def rec(name, ok, detail="", required=True):
        report["checks"].append({"check": name, "ok": bool(ok), "required": bool(required),
                                "detail": str(detail)})
        if not ok:
            (report["missing"] if required else report["warnings"]).append(
                f"{name}: {detail}" if detail else name)
        return bool(ok)

    in_dir = Path(args.input)
    req_path = in_dir / "requests.jsonl"
    man_path = in_dir / "manifest.json"
    model_dir = Path(args.model)
    out_dir = Path(args.output)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        report["warnings"].append(f"output dir not writable: {exc}")

    rec("input.dir", in_dir.is_dir(), str(in_dir))
    rec("input.manifest.json", man_path.is_file(), str(man_path))
    if man_path.is_file():
        try:
            manifest = json.loads(man_path.read_text(encoding="utf-8"))
            rec("input.manifest.json.parse", True, f"task_id={manifest.get('task_id')}")
            report["manifest_task_id"] = manifest.get("task_id")
        except Exception as exc:
            rec("input.manifest.json.parse", False, f"{type(exc).__name__}: {exc}")

    requests = []
    if rec("input.requests.jsonl", req_path.is_file(), str(req_path)):
        digest = sha256_file(req_path)
        report["requests_sha256"] = digest
        rec("input.requests.jsonl.sha256", digest == EXPECTED_REQUESTS_SHA256,
            f"{digest} (expected {EXPECTED_REQUESTS_SHA256})", required=False)
        try:
            requests = load_requests(req_path)
            rec("input.requests.jsonl.parse", True, f"{len(requests)} requests")
        except Exception as exc:
            rec("input.requests.jsonl.parse", False, f"{type(exc).__name__}: {exc}")
        rec("input.requests.jsonl.count", len(requests) >= 1, f"{len(requests)}")
        rec("input.requests.jsonl.fields",
            all(r.get("id") and r.get("document") and r.get("question") for r in requests),
            "id/document/question present on every request")

    rec("model.dir", model_dir.is_dir(), str(model_dir))
    if model_dir.is_dir():
        names = {p.name for p in model_dir.iterdir()}
        rec("model.config.json", "config.json" in names, "config.json")
        rec("model.generation_config", "generation_config.json" in names, "generation_config.json",
            required=False)
        tokenizer_ok = ("tokenizer.json" in names or "tokenizer.model" in names
                        or ({"vocab.json", "merges.txt"} <= names))
        rec("model.tokenizer", tokenizer_ok, "tokenizer.json / tokenizer.model / vocab.json+merges.txt")
        rec("model.tokenizer_config", "tokenizer_config.json" in names, "tokenizer_config.json")
        weights = [n for n in names if n.endswith(".safetensors") or n.endswith(".bin")]
        rec("model.weights", bool(weights), ", ".join(sorted(weights)[:4]) or "no *.safetensors / *.bin")

    for mod in ("torch", "transformers", "numpy"):
        spec = importlib_util.find_spec(mod)
        version = ""
        if spec is not None:
            try:
                version = getattr(__import__(mod), "__version__", "")
            except Exception:
                version = ""
        rec(f"python.{mod}", spec is not None, version or (spec.origin if spec else "not found"))

    try:
        import torch
        rec("cuda.available", torch.cuda.is_available(),
            f"torch {torch.__version__}, cuda {torch.version.cuda}")
        if torch.cuda.is_available():
            rec("cuda.device0", torch.cuda.device_count() >= 1, torch.cuda.get_device_name(0))
            rec("cuda.bf16", torch.cuda.is_bf16_supported(),
                "device supports bfloat16", required=False)
    except Exception as exc:
        rec("cuda.available", False, f"{type(exc).__name__}: {exc}")

    report["status"] = "missing_prerequisites" if report["missing"] else "ok"
    report["exit_code"] = EXIT_MISSING if report["missing"] else EXIT_OK
    try:
        write_json(out_dir / "doctor_report.json", report)
    except OSError:
        pass
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report["exit_code"]


# --------------------------------------------------------------------------- main

def build_parser():
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="GPUv1-D01 debug: CUDA Qasper reader with Qwen2.5-0.5B-Instruct",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--input", default="input", type=Path,
                        help="read-only input directory (default: input)")
    common.add_argument("--output", default="output", type=Path,
                        help="writable output directory (default: output)")
    common.add_argument("--model", default=os.environ.get("MODEL_PATH", DEFAULT_MODEL),
                        type=Path, help="local model container path")
    common.add_argument("--revision", default=EXPECTED_REVISION, help="frozen model revision")
    common.add_argument("--max-tokens", type=int, default=2048, dest="max_tokens",
                        help="max prompt tokens including chat template (default 2048)")
    common.add_argument("--max-new-tokens", type=int, default=128, dest="max_new_tokens",
                        help="max generated tokens (default 128)")

    sub.add_parser("run", parents=[common], help="batch-answer input/requests.jsonl on CUDA")
    serve = sub.add_parser("serve", parents=[common], help="serve /health and /infer on the loaded model")
    serve.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8080)))
    sub.add_parser("doctor", parents=[common], help="static preflight; exit 78 if required items are missing")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "run":
            return cmd_run(args)
        if args.command == "serve":
            return cmd_serve(args)
        if args.command == "doctor":
            return cmd_doctor(args)
    except PrereqError as exc:
        print(json.dumps({"status": "missing_prerequisites", "error": str(exc)}), flush=True)
        return EXIT_MISSING
    except KeyboardInterrupt:
        return EXIT_OK
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print(json.dumps({"status": "failed", "error": f"{type(exc).__name__}: {exc}"}), flush=True)
        return EXIT_FAILED
    return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
