#!/usr/bin/env python3
"""GPUv1-D03: HumanEval function-body completion with Qwen2.5-Coder-0.5B-Instruct.

Three entry points:

    python solution/main.py run    --input input --output output
    python solution/main.py serve  --port 8123
    python solution/main.py doctor --input input

* ``run`` reads every request from ``input/requests.jsonl``, performs a *fresh
  greedy CUDA generation* with the fixed prompt template defined in this file,
  normalizes the raw model output into a body completion that can be appended
  directly to the original prompt, and writes

    output/completions.jsonl   id / prompt / raw_generation / token_ids /
                               completion / normalization (+ small checks)
    output/run.json            full provenance: model revision, template,
                               greedy parameters, normalization rules, counts.

* ``serve`` exposes the exact same generation path over HTTP:

    GET  /health   -> {"status": "ok", ...}   (also aliased at /healthz)
    POST /complete -> {"id","prompt","raw_generation","token_ids",
                       "completion","normalization",...}

* ``doctor`` inspects the exact input files, the local model directory and the
  required Python modules **without loading the model or running inference**,
  lists every missing item, and exits 78 if anything is missing, 0 otherwise.

Hard contract: CUDA is mandatory.  If ``torch.cuda.is_available()`` is False
``ModelRunner`` raises immediately; there is no CPU fallback of any kind and no
mock weights.  Every ``completion`` in this project is produced by the language
model at inference time; no answer is ever hard-coded.
"""

from __future__ import annotations

import argparse
import ast
import datetime as _dt
import hashlib
import importlib
import json
import os
import re
import signal
import sys
import textwrap
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------
# Fixed configuration (recorded verbatim in run.json)
# --------------------------------------------------------------------------

DEFAULT_MODEL_PATH = "/models/Qwen--Qwen2.5-Coder-0.5B-Instruct"
DEFAULT_MODEL_REPO = "Qwen/Qwen2.5-Coder-0.5B-Instruct"
DEFAULT_MODEL_REVISION = "ea3f2471cf1b1f0db85067f1ef93848e38e88c25"
DEFAULT_MAX_NEW_TOKENS = 256

PROMPT_TEMPLATE_PROFILE = "qwen25coder-instruct-codecompletion-v1"
SYSTEM_PROMPT = (
    "You are a code completion engine. Given a Python function prefix, output "
    "only the missing function body. Do not restate the signature or docstring, "
    "do not add explanations, and do not use Markdown code fences."
)
USER_TEMPLATE = (
    "Complete the Python function below by writing only the body code that "
    "should be appended after the prefix (keep the 4-space indentation).\n\n"
    "{prompt}"
)

NORMALIZATION_PROFILE = "v1"
FENCE_LINE_RE = re.compile(r"^\s*```[A-Za-z0-9_+.\-]*\s*$")
STOP_PREFIXES = (
    "if __name__",
    "print(",
    "class ",
    "assert ",
    "# Test",
    "# test",
    "# Example",
    "# Check",
    "# check",
    "pytest",
    "unittest",
    "def main(",
)
DEF_RE_TMPL = r"^(\s*)def\s+{name}\s*\("

NORMALIZATION_RULES = [
    "1. Normalize newlines (\\r\\n, \\r -> \\n); keep raw_generation untouched.",
    "2. Remove a uniform Markdown code-fence wrapper: drop every line before the "
    "first fence line (```/```python/...) and everything from the closing fence on.",
    "3. Strip leading/trailing blank lines from the candidate body text.",
    "4. Preferred extraction: try, in order, (a) the fence-stripped text alone "
    "(after dedent), (b) prompt + text, (c) prompt + body-indented text. Each is "
    "parsed with ast; the last definition of the prompt's function (`def <name>` "
    "derived from the prompt) is located and its statements after the docstring are "
    "kept. This removes a restated signature/docstring/imports and any trailing "
    "test/demo code that follows the function, and also fixes prefixes whose "
    "function body is still empty.",
    "5. If the full candidate does not parse, retry while dropping trailing lines "
    "one at a time (longest parsing prefix wins); this removes trailing prose.",
    "6. Fallback: if `def <name>(` is present but ast extraction fails, keep the "
    "lines after the last docstring terminator of that definition.",
    "7. Final fallback: use the fence-stripped text as the body (flagged in "
    "normalization.applied.fallback=true) - the completion then still carries the "
    "raw decoded text so nothing is hidden.",
    "8. Re-indent the extracted statements: textwrap.dedent followed by a uniform "
    "indent equal to the indentation of the prompt's `def` line plus 4 spaces "
    "(4 spaces for the module-level HumanEval functions), and exactly one trailing "
    "newline.",
    "9. The returned `completion` is meant to be concatenated as prompt + completion.",
]

REQUIRED_MODULES = ("torch", "transformers", "numpy", "fastapi", "uvicorn")


# --------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------


def strip_markdown_fences(raw: str) -> Tuple[str, bool]:
    """Uniformly remove a Markdown code-fence wrapper from a model reply."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    first_fence = next((i for i, ln in enumerate(lines) if FENCE_LINE_RE.match(ln)), None)
    if first_fence is None:
        return text, False
    lines = lines[first_fence + 1 :]
    close = next((i for i, ln in enumerate(lines) if FENCE_LINE_RE.match(ln)), None)
    if close is not None:
        lines = lines[:close]
    return "\n".join(lines), True


def _trim_blank_edges(text: str) -> str:
    lines = text.split("\n")
    while lines and lines[0].strip() == "":
        lines.pop(0)
    while lines and lines[-1].strip() == "":
        lines.pop()
    return "\n".join(lines)


def _function_name_from_prompt(prompt: str) -> Optional[str]:
    matches = re.findall(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(", prompt, flags=re.M)
    return matches[-1] if matches else None


def _last_module_level_def(tree: ast.AST, name: Optional[str]) -> Optional[ast.AST]:
    found = None
    for node in getattr(tree, "body", []):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if name is None or node.name == name:
                found = node
    return found


def _body_block_from_def(src_lines: List[str], node: ast.AST) -> Optional[str]:
    body = list(node.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(getattr(body[0], "value", None), ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    if not body:
        return None
    start = body[0].lineno
    end = getattr(node, "end_lineno", None) or start
    block = "\n".join(src_lines[start - 1 : end])
    return block if block.strip() else None


def _extract_body_from_source(source: str, name: Optional[str]) -> Optional[str]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, MemoryError):
        return None
    node = _last_module_level_def(tree, name)
    if node is None:
        return None
    return _body_block_from_def(source.split("\n"), node)


def _prompt_body_indent(prompt: str) -> str:
    """Indent used for the first body statement (def indent + 4 spaces)."""
    for line in reversed(prompt.split("\n")):
        match = re.match(r"^([ \t]*)(?:async\s+)?def\s+", line)
        if match:
            return match.group(1) + "    "
    return "    "


def _indent_body(block: str, indent: str = "    ") -> str:
    block = textwrap.dedent(block).strip("\n")
    if not block.strip():
        return ""
    return textwrap.indent(block, indent).rstrip("\n") + "\n"


def _line_truncation_candidate(body_text: str, name: Optional[str]) -> Optional[str]:
    lines = body_text.split("\n")
    for cut in range(len(lines), 0, -1):
        trimmed = "\n".join(lines[:cut])
        block = _extract_body_from_source(trimmed, name)
        if block is not None:
            return block
    return None


def _docstring_fallback(body_text: str, name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    lines = body_text.split("\n")
    start = None
    for idx, ln in enumerate(lines):
        if re.match(DEF_RE_TMPL.format(name=re.escape(name)), ln.strip("\t ")) or re.match(
            r"^\s*(?:async\s+)?def\s+" + re.escape(name) + r"\s*\(", ln
        ):
            start = idx
    if start is None:
        return None
    tail = lines[start + 1 :]
    for j, ln in enumerate(tail):
        stripped = ln.strip()
        if stripped.endswith('"""') or stripped.endswith("'''"):
            tail = tail[j + 1 :]
            break
    else:
        if tail and tail[0].strip().startswith(('"""', "'''", "r'''", 'r"""')):
            tail = tail[1:]
    block = "\n".join(tail)
    return block if block.strip() else None


def normalize_completion(raw: str, prompt: str) -> Tuple[str, Dict[str, Any]]:
    """Turn a raw model reply into a function-body completion for `prompt`."""
    name = _function_name_from_prompt(prompt)
    indent = _prompt_body_indent(prompt)
    applied: Dict[str, Any] = {
        "profile": NORMALIZATION_PROFILE,
        "fence_stripped": False,
        "method": None,
        "stop_marker": None,
        "fallback": False,
        "dropped_trailing_lines": 0,
    }

    body_text, fence = strip_markdown_fences(raw)
    applied["fence_stripped"] = fence
    body_text = _trim_blank_edges(body_text)

    lines = body_text.split("\n")
    for idx, ln in enumerate(lines):
        if ln[:1] not in ("", " ", "\t") and any(ln.startswith(p) for p in STOP_PREFIXES):
            applied["stop_marker"] = ln[:40]
            body_text = "\n".join(lines[:idx])
            break
    body_text = _trim_blank_edges(body_text)

    if not body_text.strip():
        applied["method"] = "empty_output"
        return "", applied

    first = next((ln for ln in body_text.split("\n") if ln.strip()), "")
    candidates: List[Tuple[str, str]] = [
        ("standalone", textwrap.dedent(body_text)),
        ("prompt+text", prompt + body_text),
    ]
    if first[:1] not in (" ", "\t"):
        candidates.append(("prompt+indented_text", prompt + _indent_body(body_text, indent)))

    for label, source in candidates:
        block = _extract_body_from_source(source, name)
        if block is not None:
            applied["method"] = f"ast_def_body[{label}]"
            return _indent_body(block, indent), applied

    for label, source in candidates:
        lines_src = source.split("\n")
        for cut in range(len(lines_src), 0, -1):
            trimmed = "\n".join(lines_src[:cut])
            block = _extract_body_from_source(trimmed, name)
            if block is not None:
                applied["method"] = f"ast_def_body_line_truncated[{label}]"
                applied["dropped_trailing_lines"] = len(lines_src) - cut
                return _indent_body(block, indent), applied

    block = _docstring_fallback(body_text, name)
    if block is not None:
        applied["method"] = "docstring_tail_fallback"
        applied["fallback"] = True
        return _indent_body(block, indent), applied

    applied["method"] = "raw_text_fallback"
    applied["fallback"] = True
    return _indent_body(body_text, indent), applied


# --------------------------------------------------------------------------
# Local checks (syntax in isolation + docstring examples from the prompt)
# --------------------------------------------------------------------------


def syntax_ok(prompt: str, completion: str) -> bool:
    try:
        compile(prompt + completion, "<candidate>", "exec")
        return True
    except (SyntaxError, ValueError):
        return False


def local_docstring_check(prompt: str, completion: str) -> Dict[str, Any]:
    """Run the >>> examples that are part of the prompt docstring (systematic doctest).

    These are *not* the hidden HumanEval unit tests; they are a self-check only.
    """
    import doctest

    source = prompt + completion
    ns: Dict[str, Any] = {}
    try:
        exec(compile(source, "<candidate>", "exec"), ns)
    except Exception as exc:  # noqa: BLE001
        return {"exec_ok": False, "error": f"{type(exc).__name__}: {exc}"[:200], "ran": 0, "failures": 0}
    name = _function_name_from_prompt(prompt)
    func = ns.get(name) if name else None
    if func is None:
        return {"exec_ok": False, "error": "function not found", "ran": 0, "failures": 0}
    runner = doctest.DocTestRunner(verbose=False)
    try:
        tests = doctest.DocTestFinder().find(func, name=name, globs=dict(ns))
    except Exception as exc:  # noqa: BLE001
        return {"exec_ok": True, "error": f"doctest find: {exc}"[:200], "ran": 0, "failures": 0}
    for test in tests:
        runner.run(test, out=lambda _s: None)
    return {
        "exec_ok": True,
        "ran": runner.tries,
        "failures": runner.failures,
        "passed": runner.tries > 0 and runner.failures == 0,
    }


# --------------------------------------------------------------------------
# Model runner: the only place where text is produced (CUDA hard requirement)
# --------------------------------------------------------------------------


def _require_cuda(torch_module) -> None:
    if not torch_module.cuda.is_available():
        raise RuntimeError(
            "CUDA is required for GPUv1-D03 but torch.cuda.is_available() is False. "
            "CPU execution is forbidden by the frozen contract; refusing to run."
        )


class ModelRunner:
    def __init__(
        self,
        model_path: str = DEFAULT_MODEL_PATH,
        max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
        device: Optional[str] = None,
    ) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        # Hard CUDA gate: no CPU fallback is permitted.
        _require_cuda(torch)
        if device is None:
            device = "cuda"
        if not isinstance(device, str) or not device.startswith("cuda"):
            raise RuntimeError(
                f"Only CUDA devices are permitted; got device={device!r}. No CPU fallback is allowed."
            )
        self.device = device

        self.repo_path = model_path
        self.repo_id = DEFAULT_MODEL_REPO
        self.revision = DEFAULT_MODEL_REVISION
        lock = Path(model_path) / "asset_lock.json"
        if lock.exists():
            try:
                meta = json.loads(lock.read_text())
                self.repo_id = meta.get("repo_id", self.repo_id)
                self.revision = meta.get("revision", self.revision)
            except Exception:  # noqa: BLE001
                pass

        self.dtype = torch.bfloat16
        self.max_new_tokens = int(max_new_tokens)

        t0 = time.time()
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=False)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path, dtype=self.dtype, trust_remote_code=False
        )
        self.model.to(self.device)
        self.model.eval()
        self.load_seconds = time.time() - t0

        self.bos_token_id = self.tokenizer.bos_token_id
        self.eos_token_id = 151645  # <|im_end|> of Qwen2.5
        gen_cfg = getattr(self.model, "generation_config", None)
        if gen_cfg is not None and getattr(gen_cfg, "eos_token_id", None) is not None:
            eos = gen_cfg.eos_token_id
            if isinstance(eos, (list, tuple)) and eos:
                self.eos_token_id = int(eos[0])
            elif isinstance(eos, int):
                self.eos_token_id = int(eos)
        self.pad_token_id = self.tokenizer.pad_token_id or self.bos_token_id

    # -- prompt rendering -------------------------------------------------
    def render_prompt(self, prompt: str) -> str:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_TEMPLATE.format(prompt=prompt)},
        ]
        return self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

    # -- generation -------------------------------------------------------
    def complete(self, prompt: str, sample_id: Optional[str] = None) -> Dict[str, Any]:
        import torch

        model_input = self.render_prompt(prompt)
        encoded = self.tokenizer(model_input, return_tensors="pt")
        input_ids = encoded["input_ids"].to(self.device)
        attention_mask = encoded["attention_mask"].to(self.device)

        t0 = time.time()
        with torch.inference_mode():
            out = self.model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,          # greedy
                num_beams=1,              # greedy
                repetition_penalty=1.0,   # no penalty => pure argmax
                pad_token_id=self.pad_token_id,
                eos_token_id=self.eos_token_id,
            )
        seconds = time.time() - t0

        new_ids = out[0, input_ids.shape[1] :].tolist()
        raw_generation = self.tokenizer.decode(new_ids, skip_special_tokens=True)
        completion, norm = normalize_completion(raw_generation, prompt)
        finished = "eos" if (new_ids and new_ids[-1] == self.eos_token_id) else "length"

        return {
            "id": sample_id,
            "prompt": prompt,
            "model_input": model_input,
            "raw_generation": raw_generation,
            "token_ids": new_ids,
            "completion": completion,
            "normalization": {
                "profile": NORMALIZATION_PROFILE,
                "rules": NORMALIZATION_RULES,
                "applied": norm,
            },
            "generation": {
                "strategy": "greedy",
                "do_sample": False,
                "num_beams": 1,
                "repetition_penalty": 1.0,
                "max_new_tokens": self.max_new_tokens,
                "prompt_tokens": int(input_ids.shape[1]),
                "new_tokens": len(new_ids),
                "finished": finished,
                "seconds": round(seconds, 4),
                "device": self.device,
            },
            "checks": {
                "syntax_ok": syntax_ok(prompt, completion),
                "local_docstring": local_docstring_check(prompt, completion),
            },
        }


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_requests(input_path: Path) -> Tuple[List[Dict[str, str]], Path]:
    if input_path.is_dir():
        src = input_path / "requests.jsonl"
    else:
        src = input_path
    if not src.exists():
        raise FileNotFoundError(f"requests file not found: {src}")
    reqs: List[Dict[str, str]] = []
    with src.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if "id" not in rec or "prompt" not in rec:
                raise ValueError(f"{src}:{line_no}: record must contain id and prompt")
            reqs.append({"id": str(rec["id"]), "prompt": str(rec["prompt"])})
    ids = [r["id"] for r in reqs]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate ids in requests file")
    return reqs, src


# --------------------------------------------------------------------------
# CLI: run
# --------------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> int:
    input_path = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    reqs, src = read_requests(input_path)
    if args.limit is not None:
        reqs = reqs[: args.limit]
    if not reqs:
        raise SystemExit("no requests to process")

    runner = ModelRunner(
        model_path=args.model,
        max_new_tokens=args.max_new_tokens,
        device=args.device,
    )

    t_start = time.time()
    records: List[Dict[str, Any]] = []
    for i, req in enumerate(reqs, 1):
        rec = runner.complete(req["prompt"], sample_id=req["id"])
        records.append(rec)
        print(
            f"[{i}/{len(reqs)}] {rec['id']}: {rec['generation']['new_tokens']} tokens, "
            f"{rec['generation']['finished']}, syntax_ok={rec['checks']['syntax_ok']}",
            flush=True,
        )
    elapsed = time.time() - t_start

    completions_path = output_dir / "completions.jsonl"
    with completions_path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    n_syntax = sum(1 for r in records if r["checks"]["syntax_ok"])
    n_doc_ran = sum(1 for r in records if r["checks"]["local_docstring"].get("ran", 0) > 0)
    n_doc_pass = sum(1 for r in records if r["checks"]["local_docstring"].get("passed"))

    import numpy
    import torch
    import transformers

    run_meta: Dict[str, Any] = {
        "task_id": "GPUv1-D03",
        "mode": "run",
        "created_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "input": {
            "path": str(src),
            "sha256": _sha256_file(src),
            "problems": len(records),
            "ids": [r["id"] for r in records],
        },
        "output": {
            "dir": str(output_dir),
            "completions_file": str(completions_path),
            "completions_sha256": _sha256_file(completions_path),
        },
        "model": {
            "repo_id": runner.repo_id,
            "revision": runner.revision,
            "container_path": runner.repo_path,
            "dtype": str(runner.dtype),
            "device": str(runner.device),
            "device_name": torch.cuda.get_device_name(0),
            "load_seconds": round(runner.load_seconds, 3),
        },
        "generation": {
            "strategy": "greedy",
            "do_sample": False,
            "num_beams": 1,
            "repetition_penalty": 1.0,
            "max_new_tokens": runner.max_new_tokens,
            "sampling_parameters": None,
            "seeding": "not required: do_sample=False is deterministic argmax decoding",
            "eos_token_id": runner.eos_token_id,
            "pad_token_id": runner.pad_token_id,
            "batch_size": 1,
            "cuda_required": True,
            "cpu_fallback": False,
        },
        "prompt_template": {
            "profile": PROMPT_TEMPLATE_PROFILE,
            "chat_template_applied": True,
            "add_generation_prompt": True,
            "system": SYSTEM_PROMPT,
            "user_template": USER_TEMPLATE,
            "user_template_placeholder": "{prompt}",
            "note": "The rendered prompt (model_input) is stored per record in completions.jsonl.",
        },
        "normalization": {
            "profile": NORMALIZATION_PROFILE,
            "fence_line_regex": FENCE_LINE_RE.pattern,
            "stop_prefixes": list(STOP_PREFIXES),
            "rules": NORMALIZATION_RULES,
            "raw_preserved": True,
            "token_ids_preserved": True,
        },
        "counts": {
            "problems": len(records),
            "generated": len(records),
            "syntax_ok": n_syntax,
            "syntax_ok_rate": round(n_syntax / len(records), 4),
            "local_docstring_examples_ran": n_doc_ran,
            "local_docstring_examples_passed": n_doc_pass,
        },
        "pass_at_1": None,
        "pass_at_1_note": (
            "pass@1 is measured separately by the independent evaluator against the hidden "
            "HumanEval unit tests, which are not present in this container. This run reports "
            "only the local docstring-example self-check above; it must not be read as the "
            "hidden-test pass@1."
        ),
        "problems": [
            {
                "id": r["id"],
                "new_tokens": r["generation"]["new_tokens"],
                "finished": r["generation"]["finished"],
                "seconds": r["generation"]["seconds"],
                "syntax_ok": r["checks"]["syntax_ok"],
                "local_docstring": r["checks"]["local_docstring"],
                "normalization_method": r["normalization"]["applied"]["method"],
            }
            for r in records
        ],
        "timing": {"generation_seconds": round(elapsed, 3)},
        "environment": {
            "python": sys.version.split()[0],
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "numpy": numpy.__version__,
            "cuda_available": torch.cuda.is_available(),
        },
        "scale_note": "debug variant: 0.5B model, 8 native HumanEval prompts; reference-large not claimed.",
    }
    run_path = output_dir / "run.json"
    run_path.write_text(json.dumps(run_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {completions_path}")
    print(f"wrote {run_path}")
    print(
        f"summary: syntax {n_syntax}/{len(records)}, local docstring examples "
        f"{n_doc_pass}/{n_doc_ran} passed"
    )
    return 0


# --------------------------------------------------------------------------
# CLI: serve
# --------------------------------------------------------------------------


def cmd_serve(args: argparse.Namespace) -> int:
    import threading as _threading

    from fastapi import Body, FastAPI, HTTPException
    import uvicorn

    # Model load happens first: the HTTP endpoint is only reachable after the
    # model is on CUDA.  If CUDA is unavailable ModelRunner raises here and the
    # process exits non-zero (no service, no CPU fallback).
    runner = ModelRunner(
        model_path=args.model,
        max_new_tokens=args.max_new_tokens,
        device=args.device,
    )

    app = FastAPI(title="GPUv1-D03 HumanEval completion service", version="1.0")

    @app.get("/health")
    @app.get("/healthz")
    def health() -> Dict[str, Any]:
        import torch
        return {
            "status": "ok",
            "model_loaded": True,
            "cuda_available": torch.cuda.is_available(),
            "device": runner.device,
            "device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "repo_id": runner.repo_id,
            "revision": runner.revision,
            "container_path": runner.repo_path,
            "dtype": str(runner.dtype),
            "prompt_template_profile": PROMPT_TEMPLATE_PROFILE,
            "normalization_profile": NORMALIZATION_PROFILE,
            "generation": {
                "strategy": "greedy",
                "do_sample": False,
                "num_beams": 1,
                "max_new_tokens": runner.max_new_tokens,
            },
        }

    @app.post("/complete")
    def complete(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="body must be a JSON object")
        prompt = payload.get("prompt")
        if not isinstance(prompt, str) or prompt.strip() == "":
            raise HTTPException(status_code=400, detail="field 'prompt' must be a non-empty string")
        sample_id = payload.get("id")
        if sample_id is not None and not isinstance(sample_id, str):
            sample_id = str(sample_id)
        rec = runner.complete(prompt, sample_id=sample_id)
        rec.pop("model_input", None)
        return rec

    @app.get("/")
    def root() -> Dict[str, str]:
        return {"service": "GPUv1-D03", "endpoints": "/health, /healthz, /complete"}

    # Explicit SIGTERM/SIGINT handling: uvicorn installs its own handlers on
    # Server.run(), and those set should_exit=True, giving a graceful shutdown.
    # We wrap in try/finally so that CUDA memory is explicitly released.
    stop = _threading.Event()

    def _on_signal(signum, frame):  # pragma: no cover - signal path
        print(f"signal {signum} received, shutting down", file=sys.stderr, flush=True)
        stop.set()

    try:
        signal.signal(signal.SIGTERM, _on_signal)
        signal.signal(signal.SIGINT, _on_signal)
    except ValueError:
        pass

    print(f"serving on http://{args.host}:{args.port}", flush=True)
    config = uvicorn.Config(
        app,
        host=args.host,
        port=int(args.port),
        log_level="info",
        timeout_graceful_shutdown=10,
    )
    server = uvicorn.Server(config)
    try:
        server.run()
    finally:
        try:
            import torch
            del runner
            torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001
            pass
    return 0


# --------------------------------------------------------------------------
# CLI: doctor (no model load, no inference)
# --------------------------------------------------------------------------


def cmd_doctor(args: argparse.Namespace) -> int:
    problems: List[str] = []
    input_path = Path(args.input).resolve()

    # ---- input files ----------------------------------------------------
    reqs_file: Optional[Path] = None
    if not input_path.exists():
        problems.append(f"input path does not exist: {input_path}")
    else:
        reqs_file = input_path / "requests.jsonl" if input_path.is_dir() else input_path
        if not reqs_file.exists():
            problems.append(f"requests file missing: {reqs_file}")
        else:
            try:
                reqs, _ = read_requests(input_path)
                print(f"input OK: {len(reqs)} requests at {reqs_file}")
                print(f"  ids: {[r['id'] for r in reqs]}")
            except Exception as exc:  # noqa: BLE001
                problems.append(f"requests file unreadable: {exc}")

    # ---- manifest + declared hashes -------------------------------------
    manifest_path = None
    if input_path.is_dir():
        manifest_path = input_path / "manifest.json"
    elif reqs_file is not None:
        manifest_path = reqs_file.parent / "manifest.json"
    if manifest_path is not None and manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
            declared: Dict[str, str] = manifest.get("files", {}) or {}
            for fname, expected in declared.items():
                fpath = manifest_path.parent / fname
                if not fpath.exists():
                    problems.append(f"manifest-declared file missing: {fpath}")
                    continue
                actual = _sha256_file(fpath)
                if actual != expected:
                    problems.append(
                        f"sha256 mismatch for {fname}: expected {expected[:12]}..., got {actual[:12]}..."
                    )
                else:
                    print(f"manifest file OK: {fname} sha256={actual[:12]}...")
        except Exception as exc:  # noqa: BLE001
            problems.append(f"manifest unreadable: {exc}")
    elif manifest_path is not None:
        print(f"note: no manifest.json at {manifest_path}; skipping hash verification")

    # ---- model directory ------------------------------------------------
    model_path = Path(args.model)
    if not model_path.exists():
        problems.append(f"model directory missing: {model_path}")
    else:
        config_json = model_path / "config.json"
        if not config_json.exists():
            problems.append(f"model config missing: {config_json}")
        else:
            try:
                cfg = json.loads(config_json.read_text())
                print(f"model config OK: model_type={cfg.get('model_type')}, architectures={cfg.get('architectures')}")
            except Exception as exc:  # noqa: BLE001
                problems.append(f"model config unreadable: {exc}")

        weights_ok = (
            (model_path / "model.safetensors").exists()
            or (model_path / "model.safetensors.index.json").exists()
            or bool(list(model_path.glob("*.safetensors")))
            or bool(list(model_path.glob("*.bin")))
        )
        if not weights_ok:
            problems.append(f"no model weights (*.safetensors or *.bin) found in {model_path}")
        else:
            names = [p.name for p in model_path.glob("*.safetensors")] or [p.name for p in model_path.glob("*.bin")]
            print(f"model weights OK: {names[:4]}{' ...' if len(names) > 4 else ''}")

        tok_ok = (model_path / "tokenizer.json").exists() or (model_path / "tokenizer_config.json").exists()
        if not tok_ok:
            problems.append(f"no tokenizer files (tokenizer.json / tokenizer_config.json) in {model_path}")
        else:
            print("tokenizer files OK")

    # ---- python modules -------------------------------------------------
    for mod in REQUIRED_MODULES:
        try:
            m = importlib.import_module(mod)
            print(f"module OK: {mod} {getattr(m, '__version__', '?')}")
        except Exception as exc:  # noqa: BLE001
            problems.append(f"module missing or unimportable: {mod} ({exc})")

    # ---- CUDA -----------------------------------------------------------
    try:
        import torch
        if torch.cuda.is_available():
            print(f"CUDA OK: {torch.cuda.get_device_name(0)} (torch {torch.__version__}, cuda {torch.version.cuda})")
        else:
            problems.append(
                "CUDA is not available: torch.cuda.is_available() reported False "
                "(GPUv1-D03 forbids CPU execution)"
            )
    except Exception as exc:  # noqa: BLE001
        problems.append(f"CUDA check failed: {exc}")

    # ---- verdict --------------------------------------------------------
    if problems:
        print("", file=sys.stderr)
        for p in problems:
            print(f"MISSING: {p}", file=sys.stderr)
        print(f"doctor: {len(problems)} problem(s) found", file=sys.stderr)
        return 78
    print("doctor: all checks passed")
    return 0


# --------------------------------------------------------------------------
# argparse
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="main.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--model", default=DEFAULT_MODEL_PATH, help="local model directory")
        p.add_argument("--max-new-tokens", type=int, default=DEFAULT_MAX_NEW_TOKENS)
        p.add_argument("--device", default=None, help="CUDA device (default cuda; CPU is rejected)")

    p_run = sub.add_parser("run", help="generate completions for every request")
    p_run.add_argument("--input", default="input", help="input directory or requests.jsonl")
    p_run.add_argument("--output", default="output", help="output directory")
    p_run.add_argument("--limit", type=int, default=None, help="optional debug limit")
    add_common(p_run)
    p_run.set_defaults(func=cmd_run)

    p_serve = sub.add_parser("serve", help="HTTP service: GET /health, POST /complete")
    p_serve.add_argument("--port", type=int, required=True)
    p_serve.add_argument("--host", default="127.0.0.1")
    add_common(p_serve)
    p_serve.set_defaults(func=cmd_serve)

    p_doc = sub.add_parser(
        "doctor",
        help="inspect input files, local model directory and required modules without loading the model",
    )
    p_doc.add_argument("--input", default="input", help="input directory or requests.jsonl")
    p_doc.add_argument("--model", default=DEFAULT_MODEL_PATH, help="local model directory")
    p_doc.set_defaults(func=cmd_doctor)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
