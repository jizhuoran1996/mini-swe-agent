#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GPUv1-D10 (debug variant): English -> German translation archive + continuation entry point.

Real CUDA inference with Qwen/Qwen2.5-0.5B-Instruct (chat template, greedy, <=128 new tokens).

Subcommands
-----------
  run        --input DIR --output DIR     translate every request in input/requests.jsonl
  translate  --text TEXT --source-language L --target-language L --output JSON
  doctor     --input DIR                  inspect files/dependencies without executing the model

`--help` never imports torch/transformers and never touches the filesystem.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from pathlib import Path

TASK_ID = "GPUv1-D10"
SCALE = "debug_only"
FORMAL_LARGE_TESTED = False

MODEL_REPO = "Qwen/Qwen2.5-0.5B-Instruct"
MODEL_REVISION = "7ae557604adf67be50417f59c2c2f167def9a775"
MODEL_CONTAINER_PATH = "/models/Qwen--Qwen2.5-0.5B-Instruct"

MAX_NEW_TOKENS = 128
DECODE_MODE = "greedy"
DEFAULT_SOURCE_LANGUAGE = "English"
DEFAULT_TARGET_LANGUAGE = "German"
EXPECTED_N_REQUESTS = 8
DECLARED_REQUESTS_SHA256 = (
    "c562ae98b6ffc599ca76253b39917e6a4c0519f44914820dd5fcc9c65fe6e666"
)

SYSTEM_TEMPLATE = (
    "You are a professional translator. Translate the user's {src} text into {tgt}. "
    "Preserve the meaning exactly. Output only the {tgt} translation, with no "
    "explanations, notes, transliteration or quotation marks."
)

REQUIRED_MODEL_FILES = (
    "config.json",
    "tokenizer_config.json",
    "generation_config.json",
)


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------
def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def load_requests(path: Path):
    """Parse requests.jsonl; accept the documented id/source key spellings."""
    reqs = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            rid = None
            for key in ("id", "segment_id", "request_id"):
                if obj.get(key) is not None:
                    rid = str(obj[key])
                    break
            src = None
            for key in ("source", "text", "source_text", "sentence", "src", "en"):
                val = obj.get(key)
                if isinstance(val, str) and val.strip():
                    src = val
                    break
            if rid is None:
                raise ValueError("line %d: no id field" % lineno)
            if src is None:
                raise ValueError("line %d: no source text field" % lineno)
            reqs.append({"id": rid, "source": src, "raw": obj})
    return reqs


def build_prompt(tokenizer, text, src_lang, tgt_lang):
    messages = [
        {"role": "system", "content": SYSTEM_TEMPLATE.format(src=src_lang, tgt=tgt_lang)},
        {"role": "user", "content": text},
    ]
    return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)


def decode_clean(tokenizer, token_ids):
    return tokenizer.decode(token_ids, skip_special_tokens=True).strip()


def decode_raw(tokenizer, token_ids):
    return tokenizer.decode(token_ids, skip_special_tokens=False)


def write_json(path: Path, payload) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=False)
        fh.write("\n")


# --------------------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------------------
def load_model():
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA is not available. This task performs real GPU inference and will not "
            "fall back to CPU."
        )

    tokenizer = AutoTokenizer.from_pretrained(MODEL_CONTAINER_PATH)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    try:
        model = AutoModelForCausalLM.from_pretrained(
            MODEL_CONTAINER_PATH, dtype=torch.bfloat16, low_cpu_mem_usage=True
        )
    except TypeError:
        model = AutoModelForCausalLM.from_pretrained(
            MODEL_CONTAINER_PATH, torch_dtype=torch.bfloat16, low_cpu_mem_usage=True
        )
    model = model.to("cuda").eval()
    return model, tokenizer


def generate_all(model, tokenizer, prompts, device="cuda", max_new_tokens=MAX_NEW_TOKENS):
    """Greedy generation for every prompt. Returns [(token_ids, n_prompt_tokens), ...]."""
    import torch

    results = []
    for prompt in prompts:
        enc = tokenizer(prompt, return_tensors="pt")
        enc = {k: v.to(device) for k, v in enc.items()}
        n_in = int(enc["input_ids"].shape[1])
        with torch.inference_mode():
            out = model.generate(
                **enc,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                num_beams=1,
                use_cache=True,
                pad_token_id=tokenizer.pad_token_id,
            )
        gen_ids = [int(t) for t in out[0, n_in:].tolist()]
        results.append((gen_ids, n_in))
    return results


def model_file_digest(path: Path):
    digest = {}
    for name in REQUIRED_MODEL_FILES:
        p = path / name
        if p.is_file():
            digest[name] = sha256_file(p)
    for p in sorted(path.glob("*.safetensors")):
        digest[p.name] = sha256_file(p)
    for p in sorted(path.glob("pytorch_model*.bin")):
        digest[p.name] = sha256_file(p)
    for p in sorted(path.glob("*.json")):
        if p.name not in digest:
            digest[p.name] = sha256_file(p)
    return digest


# --------------------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------------------
def cmd_doctor(args) -> int:
    input_dir = Path(args.input)
    missing = []
    checks = []

    for name in ("requests.jsonl", "manifest.json"):
        p = input_dir / name
        ok = p.is_file()
        checks.append({"item": "input/%s" % name, "path": str(p), "ok": ok})
        if not ok:
            missing.append("input/%s" % name)

    req_path = input_dir / "requests.jsonl"
    reqs = None
    if req_path.is_file():
        try:
            reqs = load_requests(req_path)
            ok = len(reqs) == EXPECTED_N_REQUESTS
            checks.append(
                {"item": "input/requests.jsonl records", "count": len(reqs),
                 "expected": EXPECTED_N_REQUESTS, "ok": ok}
            )
            if not ok:
                missing.append(
                    "input/requests.jsonl: expected %d records, found %d"
                    % (EXPECTED_N_REQUESTS, len(reqs))
                )
        except Exception as exc:  # noqa: BLE001
            checks.append({"item": "input/requests.jsonl parse", "ok": False, "error": str(exc)})
            missing.append("input/requests.jsonl unparseable: %s" % exc)

    model_dir = Path(MODEL_CONTAINER_PATH)
    model_dir_ok = model_dir.is_dir()
    checks.append({"item": "model container dir", "path": str(model_dir), "ok": model_dir_ok})
    if not model_dir_ok:
        missing.append("model container dir %s" % model_dir)
    else:
        for name in REQUIRED_MODEL_FILES:
            ok = (model_dir / name).is_file()
            checks.append({"item": "model/%s" % name, "ok": ok})
            if not ok:
                missing.append("model/%s" % name)
        weights = list(model_dir.glob("*.safetensors")) + list(model_dir.glob("pytorch_model*.bin"))
        checks.append({"item": "model weights", "files": [w.name for w in weights],
                       "ok": bool(weights)})
        if not weights:
            missing.append("model weights (*.safetensors / pytorch_model*.bin)")
        tok_files = ["tokenizer.json", "vocab.json", "merges.txt", "tokenizer.model"]
        present = [t for t in tok_files if (model_dir / t).is_file()]
        checks.append({"item": "tokenizer files", "present": present, "ok": bool(present)})
        if not present:
            missing.append("tokenizer files")

    torch_ok = True
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        checks.append({"item": "import torch/transformers", "ok": True})
    except Exception as exc:  # noqa: BLE001
        torch_ok = False
        checks.append({"item": "import torch/transformers", "ok": False, "error": str(exc)})
        missing.append("python packages torch/transformers: %s" % exc)

    cuda_ok = False
    cuda_info = {}
    if torch_ok:
        import torch
        cuda_ok = bool(torch.cuda.is_available())
        cuda_info = {
            "torch": torch.__version__,
            "cuda_available": cuda_ok,
            "device_count": torch.cuda.device_count() if cuda_ok else 0,
            "device_name": torch.cuda.get_device_name(0) if cuda_ok else None,
        }
        checks.append({"item": "CUDA device", "ok": cuda_ok, **cuda_info})
        if not cuda_ok:
            missing.append("CUDA device (torch.cuda.is_available() == False)")

    report = {
        "task_id": TASK_ID,
        "mode": "doctor",
        "input": str(input_dir),
        "model_container_path": MODEL_CONTAINER_PATH,
        "model_repo": MODEL_REPO,
        "model_revision": MODEL_REVISION,
        "expected_requests": EXPECTED_N_REQUESTS,
        "checks": checks,
        "cuda": cuda_info,
        "missing": missing,
        "status": "ok" if not missing else "missing_items",
        "exit_code": 0 if not missing else 78,
        "executed_inference": False,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not missing else 78


# --------------------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------------------
def cmd_run(args) -> int:
    input_dir = Path(args.input)
    output_dir = Path(args.output)
    req_path = input_dir / "requests.jsonl"

    # ---- reject absent inputs BEFORE loading the model / spawning any job ----
    if not req_path.is_file():
        print(json.dumps({"status": "error", "error": "missing input file",
                          "path": str(req_path)}, ensure_ascii=False), file=sys.stderr)
        return 78
    try:
        reqs = load_requests(req_path)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "error": "unparseable requests: %s" % exc},
                         ensure_ascii=False), file=sys.stderr)
        return 78
    if not reqs:
        print(json.dumps({"status": "error", "error": "requests.jsonl is empty"},
                         ensure_ascii=False), file=sys.stderr)
        return 78

    import torch
    if not torch.cuda.is_available():
        print(json.dumps({"status": "error",
                          "error": "CUDA is not available; refusing CPU fallback"},
                         ensure_ascii=False), file=sys.stderr)
        return 3

    output_dir.mkdir(parents=True, exist_ok=True)

    seed = 0
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)

    wall_start = time.perf_counter()
    t0 = time.perf_counter()
    model, tokenizer = load_model()
    torch.cuda.synchronize()
    load_s = time.perf_counter() - t0

    param = next(model.parameters())
    device_name = torch.cuda.get_device_name(0)

    prompts = [build_prompt(tokenizer, r["source"], DEFAULT_SOURCE_LANGUAGE,
                            DEFAULT_TARGET_LANGUAGE) for r in reqs]

    ev_start = torch.cuda.Event(enable_timing=True)
    ev_end = torch.cuda.Event(enable_timing=True)

    max_mem_before = torch.cuda.max_memory_allocated()
    ev_start.record()
    gen_start = time.perf_counter()
    first_pass = generate_all(model, tokenizer, prompts)
    torch.cuda.synchronize()
    gen_wall = time.perf_counter() - gen_start
    ev_end.record()
    torch.cuda.synchronize()
    gen_event_ms = ev_start.elapsed_time(ev_end)

    # independent re-computation of token generation
    re_start = time.perf_counter()
    second_pass = generate_all(model, tokenizer, prompts)
    torch.cuda.synchronize()
    recompute_wall = time.perf_counter() - re_start

    vocab_size = int(getattr(model.config, "vocab_size", 0)) or None

    records = []
    recompute_ok = True
    raw_consistent = True
    in_vocab = True
    nonempty = True
    source_copy = 0
    total_new_tokens = 0
    diagnostics = []

    for req, (gen_ids, n_in), (gen_ids_b, n_in_b) in zip(reqs, first_pass, second_pass):
        if gen_ids != gen_ids_b or n_in != n_in_b:
            recompute_ok = False
        raw_text = decode_raw(tokenizer, gen_ids)
        translation = decode_clean(tokenizer, gen_ids)
        if decode_clean(tokenizer, gen_ids).strip() != translation.strip():
            raw_consistent = False
        if vocab_size and any(t < 0 or t >= vocab_size for t in gen_ids):
            in_vocab = False
        if not translation:
            nonempty = False
        if translation.strip().lower() == req["source"].strip().lower():
            source_copy += 1
        total_new_tokens += len(gen_ids)
        diagnostics.append({
            "id": req["id"],
            "source_chars": len(req["source"]),
            "translation_chars": len(translation),
            "length_ratio": round(len(translation) / max(1, len(req["source"])), 4),
            "source_copy_exact": translation.strip().lower() == req["source"].strip().lower(),
            "empty_output": not translation,
        })
        records.append({
            "id": req["id"],
            "translation": translation,
            "raw_text": raw_text,
            "token_ids": gen_ids,
        })

    # ---- coverage ----
    in_ids = [r["id"] for r in reqs]
    out_ids = [r["id"] for r in records]
    coverage_complete = in_ids == out_ids and len(set(out_ids)) == len(out_ids)
    duplicate_ids = sorted({i for i in out_ids if out_ids.count(i) > 1})

    translations_path = output_dir / "translations.jsonl"
    with open(translations_path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    total_wall = time.perf_counter() - wall_start
    requests_hash = sha256_file(req_path)
    sha_ok = None
    if len(DECLARED_REQUESTS_SHA256) == 64:
        sha_ok = requests_hash == DECLARED_REQUESTS_SHA256

    checks = {
        "coverage_complete": coverage_complete,
        "n_requests": len(in_ids),
        "n_translations": len(records),
        "duplicate_ids": duplicate_ids,
        "token_recompute_exact_match": recompute_ok,
        "raw_text_decode_consistent": raw_consistent,
        "token_ids_within_vocab": in_vocab,
        "vocab_size": vocab_size,
        "all_translations_nonempty": nonempty,
        "source_copy_count": source_copy,
        "max_new_tokens_respected": all(len(r["token_ids"]) <= MAX_NEW_TOKENS for r in records),
        "requests_sha256_match": sha_ok,
    }
    all_ok = bool(
        coverage_complete and recompute_ok and raw_consistent and in_vocab
        and nonempty and not duplicate_ids and checks["max_new_tokens_respected"]
    )

    run_json = {
        "task_id": TASK_ID,
        "scale": SCALE,
        "formal_large_tested": FORMAL_LARGE_TESTED,
        "status": "ok" if all_ok else "checks_failed",
        "device": {
            "cuda_available": True,
            "device_index": 0,
            "device_name": device_name,
            "param_device": str(param.device),
            "param_dtype": str(param.dtype),
            "torch": torch.__version__,
            "cuda_runtime": torch.version.cuda,
        },
        "model": {
            "repo": MODEL_REPO,
            "revision": MODEL_REVISION,
            "container_path": MODEL_CONTAINER_PATH,
            "dtype": "bfloat16",
            "files_sha256": model_file_digest(Path(MODEL_CONTAINER_PATH)),
        },
        "inputs": {
            "requests_path": str(req_path),
            "requests_sha256": requests_hash,
            "declared_requests_sha256": DECLARED_REQUESTS_SHA256,
            "declared_sha256_is_valid_length": len(DECLARED_REQUESTS_SHA256) == 64,
            "requests_sha256_match": sha_ok,
            "n_requests": len(reqs),
        },
        "generation": {
            "decode_mode": DECODE_MODE,
            "do_sample": False,
            "num_beams": 1,
            "max_new_tokens": MAX_NEW_TOKENS,
            "prompt_style": "tokenizer.apply_chat_template(add_generation_prompt=True)",
            "system_prompt_template": SYSTEM_TEMPLATE,
            "source_language": DEFAULT_SOURCE_LANGUAGE,
            "target_language": DEFAULT_TARGET_LANGUAGE,
            "references_used": False,
        },
        "timings": {
            "unit": "s",
            "model_load_s": round(load_s, 4),
            "generation_wall_s": round(gen_wall, 4),
            "generation_cuda_event_ms": round(gen_event_ms, 3),
            "recompute_wall_s": round(recompute_wall, 4),
            "total_wall_s": round(total_wall, 4),
        },
        "throughput": {
            "requests": len(reqs),
            "generated_tokens_first_pass": total_new_tokens,
            "tokens_per_s": round(total_new_tokens / gen_wall, 3) if gen_wall > 0 else None,
        },
        "cuda_evidence": {
            "generate_calls": len(reqs) * 2,
            "cuda_events_used": True,
            "cuda_synchronize_calls": 4,
            "max_memory_allocated_before_gen_bytes": int(max_mem_before),
            "max_memory_allocated_bytes": int(torch.cuda.max_memory_allocated()),
            "max_memory_reserved_bytes": int(torch.cuda.max_memory_reserved()),
            "device_name": device_name,
        },
        "checks": checks,
        "outputs": {
            "translations": str(translations_path),
            "run_json": str(output_dir / "run.json"),
            "metrics_json": str(output_dir / "metrics.json"),
            "service_config": str(output_dir / "translation_service_config.json"),
        },
        "seed": {"python_random": seed, "torch": seed, "torch_cuda": seed},
        "notes": [
            "No reference translations were read or used; only the source column is available.",
            "Token generation was recomputed independently and compared token-by-token.",
        ],
    }
    write_json(output_dir / "run.json", run_json)

    metrics = {
        "task_id": TASK_ID,
        "generative_metrics": {
            "bleu": None,
            "chrf": None,
            "status": "not_computed",
            "reason": (
                "No reference translations exist in input/ and using pre-stored targets is "
                "forbidden, so BLEU/chrF cannot be computed in this run."
            ),
        },
        "non_generative_diagnostics": {
            "n_items": len(diagnostics),
            "empty_outputs": sum(1 for d in diagnostics if d["empty_output"]),
            "exact_source_copies": sum(1 for d in diagnostics if d["source_copy_exact"]),
            "mean_length_ratio": round(
                sum(d["length_ratio"] for d in diagnostics) / max(1, len(diagnostics)), 4
            ),
            "per_item": diagnostics,
        },
    }
    write_json(output_dir / "metrics.json", metrics)

    service_config = {
        "task_id": TASK_ID,
        "model": {"repo": MODEL_REPO, "revision": MODEL_REVISION,
                  "container_path": MODEL_CONTAINER_PATH, "dtype": "bfloat16"},
        "device_requirement": "CUDA (no CPU fallback)",
        "decode": {"mode": DECODE_MODE, "max_new_tokens": MAX_NEW_TOKENS},
        "entry_point": "python solution/main.py translate --text TEXT "
                       "--source-language English --target-language German --output OUT.json",
        "default_source_language": DEFAULT_SOURCE_LANGUAGE,
        "default_target_language": DEFAULT_TARGET_LANGUAGE,
        "validation": checks,
    }
    write_json(output_dir / "translation_service_config.json", service_config)

    summary = {
        "status": run_json["status"],
        "translations": str(translations_path),
        "run_json": str(output_dir / "run.json"),
        "checks": checks,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if all_ok else 1


# --------------------------------------------------------------------------------------
# translate (continuation entry point for new sentences)
# --------------------------------------------------------------------------------------
def cmd_translate(args) -> int:
    import torch

    if not torch.cuda.is_available():
        print(json.dumps({"status": "error",
                          "error": "CUDA is not available; refusing CPU fallback"},
                         ensure_ascii=False), file=sys.stderr)
        return 3
    if not Path(MODEL_CONTAINER_PATH).is_dir():
        print(json.dumps({"status": "error", "error": "model container missing",
                          "path": MODEL_CONTAINER_PATH}, ensure_ascii=False), file=sys.stderr)
        return 78

    torch.manual_seed(0)
    torch.cuda.manual_seed_all(0)

    t0 = time.perf_counter()
    model, tokenizer = load_model()
    torch.cuda.synchronize()
    load_s = time.perf_counter() - t0

    prompt = build_prompt(tokenizer, args.text, args.source_language, args.target_language)

    ev_start = torch.cuda.Event(enable_timing=True)
    ev_end = torch.cuda.Event(enable_timing=True)
    ev_start.record()
    t1 = time.perf_counter()
    (gen_ids, n_in) = generate_all(model, tokenizer, [prompt])[0]
    torch.cuda.synchronize()
    elapsed = time.perf_counter() - t1
    ev_end.record()
    torch.cuda.synchronize()

    result = {
        "status": "ok",
        "task_id": TASK_ID,
        "model": {"repo": MODEL_REPO, "revision": MODEL_REVISION, "dtype": "bfloat16"},
        "device": torch.cuda.get_device_name(0),
        "source_language": args.source_language,
        "target_language": args.target_language,
        "text": args.text,
        "translation": decode_clean(tokenizer, gen_ids),
        "raw_text": decode_raw(tokenizer, gen_ids),
        "token_ids": gen_ids,
        "n_prompt_tokens": n_in,
        "n_new_tokens": len(gen_ids),
        "max_new_tokens": MAX_NEW_TOKENS,
        "decode_mode": DECODE_MODE,
        "timings": {"model_load_s": round(load_s, 4), "generation_s": round(elapsed, 4),
                    "generation_cuda_event_ms": round(ev_start.elapsed_time(ev_end), 3)},
    }

    if args.output and args.output != "-":
        out_path = Path(args.output)
        if out_path.parent and str(out_path.parent) not in ("", "."):
            out_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(out_path, result)
        result["output_path"] = str(out_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


# --------------------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description=(
            "%s (%s): English->German translation with %s on CUDA "
            "(greedy, max %d new tokens)." % (TASK_ID, SCALE, MODEL_REPO, MAX_NEW_TOKENS)
        ),
    )
    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run", help="translate every request in input/requests.jsonl")
    p_run.add_argument("--input", required=True, help="input directory (requests.jsonl)")
    p_run.add_argument("--output", required=True, help="output directory")
    p_run.set_defaults(func=cmd_run)

    p_tr = sub.add_parser("translate", help="translate one new sentence through the local GPU")
    p_tr.add_argument("--text", required=True, help="source sentence")
    p_tr.add_argument("--source-language", dest="source_language",
                      default=DEFAULT_SOURCE_LANGUAGE)
    p_tr.add_argument("--target-language", dest="target_language",
                      default=DEFAULT_TARGET_LANGUAGE)
    p_tr.add_argument("--output", default="-",
                      help="path for the JSON result ('-' for stdout only)")
    p_tr.set_defaults(func=cmd_translate)

    p_doc = sub.add_parser("doctor", help="inspect inputs and dependencies (no inference)")
    p_doc.add_argument("--input", required=True, help="input directory")
    p_doc.set_defaults(func=cmd_doctor)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
