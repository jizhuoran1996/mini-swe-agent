#!/usr/bin/env python3
"""GPUv1-D05 (debug variant) - DocVQA document-image questions answered with a real
Qwen2.5-VL-3B-Instruct forward/generate pass on CUDA.

Subcommands
-----------
  doctor --input DIR                                 static readiness check, no model load
  run    --input DIR --output DIR                    full ledger run over requests.jsonl
  infer  --image PATH --question TEXT --output JSON  one extra, previously unseen document

The model actually receives the decoded page image and the question; answers are
produced by greedy decoding (<= 64 new tokens) and the generated token ids are
returned alongside the decoded text.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

MODEL_PATH = os.environ.get("DOCVQA_MODEL_PATH", "/models/Qwen--Qwen2.5-VL-3B-Instruct")
MODEL_REPO = "Qwen/Qwen2.5-VL-3B-Instruct"
MODEL_REVISION = "66285546d2b821cf421d4f5eb2576359d3770cd3"
MAX_PIXELS = 262144
MIN_PIXELS = 3136
MAX_NEW_TOKENS = 64
IMAGE_FACTOR = 28
SEED = 0
INSTRUCTION = (
    "Answer the question with a short phrase taken from the document. "
    "If the answer is not present in the image, reply 'unanswerable'."
)


# ----------------------------------------------------------------------------- helpers
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def smart_resize(height: int, width: int, factor: int = IMAGE_FACTOR,
                 min_pixels: int = MIN_PIXELS, max_pixels: int = MAX_PIXELS):
    """Same rounding scheme as the official Qwen2.5-VL image processor."""
    if height < factor or width < factor:
        raise ValueError(f"image too small for patch factor: {height}x{width}")
    h_bar = max(factor, int(round(height / factor)) * factor)
    w_bar = max(factor, int(round(width / factor)) * factor)
    if h_bar * w_bar > max_pixels:
        beta = math.sqrt((height * width) / max_pixels)
        h_bar = max(factor, math.floor(height / beta / factor) * factor)
        w_bar = max(factor, math.floor(width / beta / factor) * factor)
    elif h_bar * w_bar < min_pixels:
        beta = math.sqrt(min_pixels / (height * width))
        h_bar = math.ceil(height * beta / factor) * factor
        w_bar = math.ceil(width * beta / factor) * factor
    return h_bar, w_bar


def load_requests(input_dir: Path):
    req_path = input_dir / "requests.jsonl"
    if not req_path.is_file():
        raise FileNotFoundError(f"missing requests file: {req_path}")
    out = []
    with req_path.open("r", encoding="utf-8") as fh:
        for idx, line in enumerate(fh):
            line = line.strip()
            if line:
                out.append((idx, json.loads(line)))
    if not out:
        raise ValueError(f"no requests in {req_path}")
    return req_path, out


def normalize_request(obj: dict, idx: int) -> dict:
    rid = obj.get("id", obj.get("question_id", obj.get("qid", idx)))
    img = (obj.get("image") or obj.get("image_path") or obj.get("image_file")
           or obj.get("page_image") or obj.get("image_name"))
    if img is None:
        raise ValueError(f"request {rid} has no image field")
    question = obj.get("question") or obj.get("query") or obj.get("text")
    if question is None:
        raise ValueError(f"request {rid} has no question field")
    gold = obj.get("answers", obj.get("gold_answers"))
    if gold is None:
        gold = obj.get("answer")
    if isinstance(gold, str):
        gold = [gold]
    elif isinstance(gold, list):
        gold = [str(g) for g in gold]
    elif gold is not None:
        gold = [str(gold)]
    page_id = str(obj.get("page_id", Path(str(img)).stem))
    return {"id": str(rid), "page_id": page_id, "image": str(img),
            "question": str(question), "gold": gold}


def _lev(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def anls_score(pred: str, golds, thr: float = 0.5):
    """ANLS with the standard 0.5 distance threshold. Returns None without gold."""
    if not golds:
        return None
    p = str(pred).strip().lower()
    best = 0.0
    for g in golds:
        gg = str(g).strip().lower()
        m = max(len(p), len(gg))
        s = 1.0 if m == 0 else 1.0 - _lev(p, gg) / m
        if s >= thr:
            best = max(best, s)
    return best


# ----------------------------------------------------------------------------- model IO
def load_model():
    import torch
    from transformers import AutoProcessor

    try:
        from transformers import Qwen2_5_VLForConditionalGeneration as ModelCls
    except ImportError:  # newer transformers exposes the generic image-text class
        from transformers import AutoModelForImageTextToText as ModelCls

    try:
        processor = AutoProcessor.from_pretrained(
            MODEL_PATH, min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS)
    except TypeError:
        processor = AutoProcessor.from_pretrained(MODEL_PATH)
        try:
            ip = processor.image_processor
            ip.min_pixels, ip.max_pixels = MIN_PIXELS, MAX_PIXELS
        except Exception:
            pass

    kwargs = {"dtype": torch.bfloat16}
    try:
        model = ModelCls.from_pretrained(MODEL_PATH, **kwargs)
    except TypeError:
        model = ModelCls.from_pretrained(MODEL_PATH, torch_dtype=torch.bfloat16)
    model = model.to("cuda").eval()
    for p in model.parameters():
        p.requires_grad_(False)
    return processor, model, torch


def build_prompt(processor, question: str) -> str:
    messages = [{"role": "user", "content": [
        {"type": "image"},
        {"type": "text", "text": f"{question}\n{INSTRUCTION}"},
    ]}]
    return processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)


def answer_image(processor, model, torch, image_path: Path, question: str) -> dict:
    """Decode one page, run real vision encoding + greedy generation, return tokens/text."""
    from PIL import Image

    t_start = time.perf_counter()
    with Image.open(image_path) as im:
        pil = im.convert("RGB")
    t_decoded = time.perf_counter()
    w0, h0 = pil.size
    th, tw = smart_resize(h0, w0)
    if (th, tw) != (h0, w0):
        pil = pil.resize((tw, th), Image.BICUBIC)
    t_resized = time.perf_counter()

    prompt = build_prompt(processor, question)
    inputs = processor(text=[prompt], images=[pil], return_tensors="pt")
    if "pixel_values" in inputs:
        inputs["pixel_values"] = inputs["pixel_values"].to(torch.bfloat16)
    inputs = inputs.to("cuda")
    torch.cuda.synchronize()
    t_prep = time.perf_counter()
    h2d_bytes = int(inputs["pixel_values"].numel() * inputs["pixel_values"].element_size())

    start_ev = torch.cuda.Event(enable_timing=True)
    end_ev = torch.cuda.Event(enable_timing=True)
    start_ev.record()
    with torch.inference_mode():
        gen = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            return_dict_in_generate=True,
        )
    end_ev.record()
    torch.cuda.synchronize()
    t_end = time.perf_counter()
    gpu_ms = start_ev.elapsed_time(end_ev)

    seq = gen.sequences
    in_len = inputs["input_ids"].shape[1]
    token_ids = [int(t) for t in seq[0, in_len:].tolist()]
    answer = processor.tokenizer.decode(token_ids, skip_special_tokens=True).strip()
    re_ids = processor.tokenizer.encode(answer, add_special_tokens=False)

    return {
        "answer": answer,
        "token_ids": token_ids,
        "retokenized_ids": [int(t) for t in re_ids],
        "retokenized_equal": [int(t) for t in re_ids] == token_ids,
        "num_tokens": len(token_ids),
        "image_original_wh": [w0, h0],
        "image_resized_wh": [tw, th],
        "pixels_after_resize": tw * th,
        "pixel_values_shape": list(inputs["pixel_values"].shape),
        "h2d_bytes": h2d_bytes,
        "prompt_tokens": int(in_len),
        "timings_s": {
            "image_decode": t_decoded - t_start,
            "resize": t_resized - t_decoded,
            "preprocess_h2d": t_prep - t_resized,
            "generate_wall": t_end - t_prep,
            "total": t_end - t_start,
        },
        "generate_gpu_ms": gpu_ms,
    }


# ----------------------------------------------------------------------------- doctor
def cmd_doctor(args) -> int:
    report = {"command": "doctor", "missing": [], "warnings": [], "checks": {}}

    def miss(msg):
        report["missing"].append(msg)

    # python deps
    for mod in ("torch", "transformers", "PIL", "numpy"):
        try:
            __import__(mod)
            report["checks"][f"import:{mod}"] = "ok"
        except Exception as exc:  # pragma: no cover
            report["checks"][f"import:{mod}"] = f"missing ({exc})"
            miss(f"python package not importable: {mod}")

    # CUDA
    try:
        import torch
        if torch.cuda.is_available():
            report["checks"]["cuda"] = {
                "available": True,
                "device_count": torch.cuda.device_count(),
                "device_name": torch.cuda.get_device_name(0),
                "torch": torch.__version__,
            }
        else:
            report["checks"]["cuda"] = {"available": False}
            miss("CUDA is not available (torch.cuda.is_available() == False)")
    except Exception as exc:
        report["checks"]["cuda"] = f"error: {exc}"
        miss("torch/CUDA probe failed")

    try:
        import transformers
        report["checks"]["transformers"] = transformers.__version__
    except Exception:
        pass

    # model assets (no weight loading)
    mp = Path(MODEL_PATH)
    if not mp.is_dir():
        miss(f"model directory missing: {MODEL_PATH}")
    else:
        needed = ["config.json"]
        present = {p.name for p in mp.iterdir()}
        for name in needed:
            if name not in present:
                miss(f"model file missing: {mp / name}")
        weights = [n for n in present if n.endswith((".safetensors", ".bin"))]
        if not weights:
            miss(f"no weight shards found in {mp}")
        else:
            report["checks"]["model_weight_files"] = sorted(weights)
        if not any(n.startswith("tokenizer") for n in present):
            miss(f"no tokenizer files found in {mp}")

    # inputs
    inp = Path(args.input)
    if not inp.is_dir():
        miss(f"input directory missing: {inp}")
    else:
        try:
            req_path, reqs = load_requests(inp)
            report["checks"]["requests_file"] = str(req_path)
            report["checks"]["requests_sha256"] = sha256_file(req_path)
            report["checks"]["num_requests"] = len(reqs)
            man = inp / "manifest.json"
            if man.is_file():
                try:
                    mdoc = json.loads(man.read_text())
                    declared = (mdoc.get("files") or {}).get("requests.jsonl")
                    if declared and declared != report["checks"]["requests_sha256"]:
                        miss("requests.jsonl sha256 does not match manifest.json")
                    else:
                        report["checks"]["manifest_hash_match"] = True
                except Exception as exc:
                    report["warnings"].append(f"manifest.json unreadable: {exc}")
            else:
                report["warnings"].append("manifest.json not present")
            for idx, obj in reqs:
                try:
                    req = normalize_request(obj, idx)
                except Exception as exc:
                    miss(f"request line {idx}: {exc}")
                    continue
                ipath = Path(req["image"])
                if not ipath.is_absolute():
                    ipath = inp / ipath
                if not ipath.is_file():
                    miss(f"image missing for id={req['id']}: {ipath}")
                else:
                    try:
                        from PIL import Image
                        with Image.open(ipath) as im:
                            im.verify()
                    except Exception as exc:
                        miss(f"image unreadable for id={req['id']}: {ipath} ({exc})")
        except Exception as exc:
            miss(f"cannot parse input: {exc}")

    report["ok"] = not report["missing"]
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 78


# ----------------------------------------------------------------------------- run
def cmd_run(args) -> int:
    import torch

    if not torch.cuda.is_available():
        print(json.dumps({"error": "CUDA required but not available"}))
        return 1
    torch.manual_seed(SEED)
    rng_before = torch.random.get_rng_state().clone()

    inp = Path(args.input)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    req_path, raw = load_requests(inp)
    requests = []
    for idx, obj in raw:
        req = normalize_request(obj, idx)
        ipath = Path(req["image"])
        if not ipath.is_absolute():
            ipath = inp / ipath
        if not ipath.is_file():
            print(json.dumps({"error": f"missing image for id={req['id']}: {ipath}"}))
            return 1
        req["image_abs"] = str(ipath)
        requests.append(req)
    if args.limit and args.limit > 0:
        requests = requests[: args.limit]

    wall0 = time.perf_counter()
    processor, model, torch = load_model()
    torch.cuda.synchronize()
    load_s = time.perf_counter() - wall0
    if torch.cuda.max_memory_allocated() > 0 and "max_memory_allocated" not in dir(torch.cuda):
        pass
    torch.cuda.reset_peak_memory_stats()

    answers_lines = []
    samples = []
    anls_scores = []
    for req in requests:
        res = answer_image(processor, model, torch, Path(req["image_abs"]), req["question"])
        line = {
            "id": req["id"],
            "answer": res["answer"],
            "token_ids": res["token_ids"],
            "page_id": req["page_id"],
            "question": req["question"],
            "image": req["image"],
            "num_tokens": res["num_tokens"],
        }
        answers_lines.append(line)
        score = anls_score(res["answer"], req["gold"])
        if score is not None:
            anls_scores.append(score)
        samples.append({**{k: req[k] for k in ("id", "page_id", "question", "image")},
                        **res, "anls": score})
        print(f"[{req['id']}] {req['question'][:60]!r} -> {res['answer'][:80]!r} "
              f"({res['num_tokens']} tok, {res['generate_gpu_ms']:.1f} ms gpu)", flush=True)

    total_s = time.perf_counter() - wall0
    peak_gib = torch.cuda.max_memory_allocated() / (1024 ** 3)

    answers_path = out / "answers.jsonl"
    with answers_path.open("w", encoding="utf-8") as fh:
        for line in answers_lines:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")

    pages = {}
    for s in samples:
        pages.setdefault(s["page_id"], {"image": s["image"], "question_ids": []})
        pages[s["page_id"]]["question_ids"].append(s["id"])
    page_manifest = {
        "num_pages": len(pages),
        "num_questions": len(samples),
        "pages": pages,
    }
    (out / "page_manifest.json").write_text(
        json.dumps(page_manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    try:
        ip_cfg = processor.image_processor.to_dict()
    except Exception:
        ip_cfg = {k: v for k, v in vars(processor.image_processor).items()
                  if isinstance(v, (int, float, str, bool, list, dict, type(None)))}
    (out / "processor_config.json").write_text(json.dumps({
        "processor_class": type(processor).__name__,
        "tokenizer_class": type(processor.tokenizer).__name__,
        "image_processor": ip_cfg,
        "min_pixels": MIN_PIXELS,
        "max_pixels": MAX_PIXELS,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = {
        "task_id": "GPUv1-D05",
        "variant": "debug_only",
        "reference_large_claimed": False,
        "dataset": "nielsr/docvqa_1200_examples",
        "status": "ok",
        "model": {
            "repo": MODEL_REPO,
            "revision": MODEL_REVISION,
            "container_path": MODEL_PATH,
            "dtype": "bfloat16",
            "device": "cuda:0",
            "attn_implementation": getattr(model.config, "_attn_implementation", None),
            "num_parameters": int(sum(p.numel() for p in model.parameters())),
        },
        "hardware": {
            "gpu_name": torch.cuda.get_device_name(0),
            "gpu_count": torch.cuda.device_count(),
            "capability": list(torch.cuda.get_device_capability(0)),
            "cuda_version": torch.version.cuda,
            "torch": torch.__version__,
            "torch_cuda_available": True,
        },
        "config": {
            "max_pixels": MAX_PIXELS,
            "min_pixels": MIN_PIXELS,
            "image_factor": IMAGE_FACTOR,
            "max_new_tokens": MAX_NEW_TOKENS,
            "do_sample": False,
            "seed": SEED,
            "instruction": INSTRUCTION,
        },
        "inputs": {
            "requests": str(req_path),
            "requests_sha256": sha256_file(req_path),
            "num_requests": len(samples),
            "requests_manifest_sha256_declared": (
                (json.loads((inp / "manifest.json").read_text()).get("files", {})
                 .get("requests.jsonl")) if (inp / "manifest.json").is_file() else None),
        },
        "outputs": {
            "answers_jsonl_sha256": sha256_file(answers_path),
            "answers_jsonl": str(answers_path),
            "num_answers": len(answers_lines),
        },
        "timings_s": {
            "model_load": load_s,
            "total_wall": total_s,
            "generation_gpu_ms_sum": sum(s["generate_gpu_ms"] for s in samples),
            "per_sample_total": [s["timings_s"]["total"] for s in samples],
        },
        "memory": {
            "cuda_peak_allocated_gib": peak_gib,
            "cuda_peak_reserved_gib": torch.cuda.max_memory_reserved() / (1024 ** 3),
            "h2d_bytes_total": sum(s["h2d_bytes"] for s in samples),
        },
        "rng": {
            "seed": SEED,
            "torch_rng_state_sha256_after_load": hashlib.sha256(
                bytes(rng_before.cpu().numpy().tobytes())).hexdigest(),
        },
        "scoring": {
            "metric": "ANLS",
            "threshold": 0.5,
            "num_scored": len(anls_scores),
            "mean_anls": (sum(anls_scores) / len(anls_scores)) if anls_scores else None,
            "note": ("computed from independent gold answers carried in requests.jsonl; "
                     "the model never sees them") if anls_scores else
                    "no gold answers present in this debug input; ANLS not computable",
        },
        "samples": samples,
        "cuda_work": {
            "vision_encoder_ran_on_cuda": True,
            "generation_ran_on_cuda": True,
            "cpu_fallback_used": False,
        },
    }
    (out / "run.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                                  encoding="utf-8")
    print(json.dumps({"status": "ok", "answers": str(answers_path),
                      "num_answers": len(answers_lines),
                      "mean_anls": summary["scoring"]["mean_anls"],
                      "total_wall_s": total_s}, ensure_ascii=False))
    return 0


# ----------------------------------------------------------------------------- infer
def cmd_infer(args) -> int:
    import torch

    if not torch.cuda.is_available():
        print(json.dumps({"error": "CUDA required but not available"}))
        return 1
    image_path = Path(args.image)
    if not image_path.is_file():
        print(json.dumps({"error": f"image not found: {image_path}"}))
        return 1
    torch.manual_seed(SEED)
    processor, model, torch = load_model()
    res = answer_image(processor, model, torch, image_path, args.question)
    payload = {
        "task_id": "GPUv1-D05",
        "mode": "infer",
        "image": str(image_path),
        "question": args.question,
        "answer": res["answer"],
        "token_ids": res["token_ids"],
        "num_tokens": res["num_tokens"],
        "model": {"repo": MODEL_REPO, "revision": MODEL_REVISION,
                  "container_path": MODEL_PATH, "dtype": "bfloat16"},
        "config": {"max_pixels": MAX_PIXELS, "min_pixels": MIN_PIXELS,
                   "max_new_tokens": MAX_NEW_TOKENS, "do_sample": False},
        "image_original_wh": res["image_original_wh"],
        "image_resized_wh": res["image_resized_wh"],
        "timings_s": res["timings_s"],
        "generate_gpu_ms": res["generate_gpu_ms"],
    }
    out_path = Path(args.output)
    if out_path.parent and str(out_path.parent) not in ("", "."):
        out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status": "ok", "answer": res["answer"], "output": str(out_path)},
                     ensure_ascii=False))
    return 0


# ----------------------------------------------------------------------------- cli
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="main.py",
        description="GPUv1-D05 debug variant: DocVQA image+question -> answer ledger "
                    "with Qwen2.5-VL-3B-Instruct on CUDA.")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="check inputs/model/CUDA without loading weights")
    d.add_argument("--input", required=True, help="input directory with requests.jsonl")

    r = sub.add_parser("run", help="answer every request in input/requests.jsonl")
    r.add_argument("--input", required=True)
    r.add_argument("--output", required=True)
    r.add_argument("--limit", type=int, default=0, help="debug helper: cap number of requests")

    i = sub.add_parser("infer", help="answer one extra, unseen document image")
    i.add_argument("--image", required=True)
    i.add_argument("--question", required=True)
    i.add_argument("--output", required=True)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "doctor":
        return cmd_doctor(args)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "infer":
        return cmd_infer(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
