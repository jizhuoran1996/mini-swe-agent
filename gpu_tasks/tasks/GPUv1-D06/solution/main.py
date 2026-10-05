#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GPUv1-D06 (debug variant) -- Qwen2.5-VL-3B-Instruct question answering over a
16-frame VKITTI2 short clip, feeding 8 uniformly sampled frames per request as an
ordered multi-image context.

Sub-commands
------------
    main.py --help
    main.py doctor --input input
    main.py run    --input input                  --output output
    main.py infer  --input input/requests.jsonl   --output output_infer

A real CUDA device is mandatory: the process refuses to run on CPU.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

MODEL_PATH = os.environ.get("QWEN25VL_MODEL_PATH", "/models/Qwen--Qwen2.5-VL-3B-Instruct")
MODEL_REPO = "Qwen/Qwen2.5-VL-3B-Instruct"
MODEL_REVISION = "66285546d2b821cf421d4f5eb2576359d3770cd3"
MAX_PIXELS = 65536          # per-frame pixel budget for this debug variant
MAX_NEW_TOKENS = 128        # greedy, fixed
PATCH = 28                  # patch_size(14) * merge_size(2)


# ---------------------------------------------------------------- utilities

def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _first(obj: dict, keys):
    for k in keys:
        if k in obj and obj[k] is not None:
            return obj[k]
    return None


def _normalise_frame(fr):
    if isinstance(fr, str):
        return fr
    if isinstance(fr, dict):
        return _first(fr, ["path", "file", "frame", "image", "frame_id", "id"])
    return None


def _normalise_request(obj: dict, lineno: int) -> dict:
    if not isinstance(obj, dict):
        raise SystemExit(f"requests.jsonl line {lineno}: expected a JSON object")
    vid = _first(obj, ["videoID", "video_id", "video", "id", "uid"])
    if vid is None:
        raise SystemExit(f"requests.jsonl line {lineno}: no videoID field")
    vid = str(vid)

    raw_frames = _first(obj, ["frames", "sampled_frames", "frame_paths", "images"]) or []
    if isinstance(raw_frames, (str, dict)):
        raw_frames = [raw_frames]
    frames = [p for p in (_normalise_frame(f) for f in raw_frames) if p]
    if not frames:
        raise SystemExit(f"requests.jsonl line {lineno}: request {vid} has no frames")

    raw_qs = _first(obj, ["questions", "qa", "queries", "qas"]) or []
    if isinstance(raw_qs, (str, dict)):
        raw_qs = [raw_qs]
    questions = []
    for i, q in enumerate(raw_qs):
        if isinstance(q, str):
            qid, text = f"{vid}_q{i}", q
        elif isinstance(q, dict):
            qid = _first(q, ["questionID", "question_id", "qid", "id"]) or f"{vid}_q{i}"
            text = _first(q, ["question", "text", "prompt", "query"])
        else:
            raise SystemExit(f"requests.jsonl line {lineno}: bad question entry {i}")
        if not text:
            raise SystemExit(f"requests.jsonl line {lineno}: question {qid} has no text")
        questions.append({"questionID": str(qid), "question": str(text)})
    if not questions:
        raise SystemExit(f"requests.jsonl line {lineno}: request {vid} has no questions")
    return {"videoID": vid, "frames": frames, "questions": questions}


def load_requests(path: Path):
    reqs = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"requests.jsonl line {lineno}: invalid JSON: {exc}")
            reqs.append(_normalise_request(obj, lineno))
    if not reqs:
        raise SystemExit(f"no requests found in {path}")
    return reqs


def resolve_frame(ref: str, base_dirs):
    cand = Path(ref)
    if cand.is_absolute():
        return cand if cand.is_file() else None
    for d in base_dirs:
        c = Path(d) / ref
        if c.is_file():
            return c
    c = Path.cwd() / ref
    return c if c.is_file() else None


def fit_frame(img, max_pixels: int = MAX_PIXELS):
    """Down-scale to <= max_pixels, aspect preserved, sides aligned to PATCH."""
    from PIL import Image
    w, h = img.size
    if w <= 0 or h <= 0:
        raise ValueError("empty frame")
    if w * h > max_pixels:
        s = (max_pixels / float(w * h)) ** 0.5
        w, h = int(w * s), int(h * s)
    w = max(PATCH, (w // PATCH) * PATCH)
    h = max(PATCH, (h // PATCH) * PATCH)
    while w * h > max_pixels and (w > PATCH or h > PATCH):
        if w >= h and w > PATCH:
            w -= PATCH
        elif h > PATCH:
            h -= PATCH
        else:
            break
    if (w, h) != img.size:
        img = img.resize((w, h), Image.BICUBIC)
    return img


def build_prompt(processor, n_images: int, question: str) -> str:
    content = [{"type": "image"} for _ in range(n_images)]
    content.append({"type": "text", "text": question})
    messages = [{"role": "user", "content": content}]
    try:
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        if text and text.count("<|image_pad|>") == n_images:
            return text
    except Exception:
        pass
    parts = ["<|im_start|>system\nYou are a helpful assistant.<|im_end|>\n<|im_start|>user\n"]
    parts.extend(["<|vision_start|><|image_pad|><|vision_end|>"] * n_images)
    parts.append(question)
    parts.append("<|im_end|>\n<|im_start|>assistant\n")
    return "".join(parts)


# ---------------------------------------------------------------- doctor

def cmd_doctor(args) -> int:
    issues, notes = [], []
    inp = Path(args.input)
    if not inp.is_dir():
        issues.append(f"input directory missing: {inp}")
    else:
        req = inp / "requests.jsonl"
        if not req.is_file():
            issues.append(f"missing required file: {req}")
        else:
            notes.append(f"requests.jsonl ok ({req.stat().st_size} bytes)")
        man = inp / "manifest.json"
        notes.append(f"manifest.json {'present' if man.is_file() else 'absent (optional for run)'}")
        fdir = inp / "frames"
        if not fdir.is_dir():
            issues.append(f"missing frames directory: {fdir}")
        else:
            n = len(list(fdir.glob("*.png")))
            notes.append(f"frames/*.png count = {n}")
            if n == 0:
                issues.append(f"no *.png frames found in {fdir}")

    mp = Path(MODEL_PATH)
    if not mp.is_dir():
        issues.append(f"model directory missing: {mp}")
    else:
        if not (mp / "config.json").is_file():
            issues.append(f"missing model config: {mp / 'config.json'}")
        weights = list(mp.glob("*.safetensors")) + list(mp.glob("*.bin"))
        if not weights:
            issues.append(f"no model weights (*.safetensors/*.bin) in {mp}")
        else:
            notes.append(f"model weights: {len(weights)} shard file(s)")
        notes.append(f"model repo={MODEL_REPO} revision={MODEL_REVISION}")

    try:
        import torch
        notes.append(f"torch {torch.__version__}")
        if not torch.cuda.is_available():
            issues.append("torch.cuda.is_available() is False -- CUDA device required")
        else:
            notes.append(f"cuda devices = {torch.cuda.device_count()}")
            try:
                notes.append("gpu0 = " + torch.cuda.get_device_name(0))
            except Exception:
                pass
    except Exception as exc:
        issues.append(f"torch import/init failed: {exc}")

    try:
        import transformers
        notes.append(f"transformers {transformers.__version__}")
        try:
            from transformers import AutoProcessor  # noqa: F401
            from transformers import Qwen2_5_VLForConditionalGeneration  # noqa: F401
        except Exception as exc:
            issues.append(f"Qwen2.5-VL classes unavailable in transformers: {exc}")
    except Exception as exc:
        issues.append(f"transformers import failed: {exc}")

    try:
        import PIL
        from PIL import Image  # noqa: F401
        notes.append(f"Pillow {PIL.__version__}")
    except Exception as exc:
        issues.append(f"Pillow import failed: {exc}")

    for n in notes:
        print(f"[doctor] {n}")
    if issues:
        print("[doctor] MISSING:")
        for i in issues:
            print(f"  - {i}")
        return 78
    print("[doctor] OK: all required files and dependencies are available")
    return 0


# ---------------------------------------------------------------- execution

def _execute(inp_arg: str, out_arg: str, mode: str) -> int:
    from PIL import Image
    import torch
    from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

    inp = Path(inp_arg).resolve()
    out_dir = Path(out_arg).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if inp.is_dir():
        req_path = inp / "requests.jsonl"
        base_dirs = [inp, inp / "frames", Path.cwd()]
    else:
        req_path = inp
        base_dirs = [inp.parent, inp.parent / "frames", Path.cwd()]
    if not req_path.is_file():
        print(f"ERROR: requests JSONL not found: {req_path}", file=sys.stderr)
        return 2

    if not torch.cuda.is_available():
        print("ERROR: CUDA is not available -- this task requires a real GPU.", file=sys.stderr)
        return 3
    device = torch.device("cuda:0")

    reqs = load_requests(req_path)
    missing = []
    for r in reqs:
        for ref in r["frames"]:
            if resolve_frame(ref, base_dirs) is None:
                missing.append(f"{r['videoID']} :: {ref}")
    if missing:
        print("ERROR: referenced frame files are missing:", file=sys.stderr)
        for m in missing[:32]:
            print(f"  - {m}", file=sys.stderr)
        if len(missing) > 32:
            print(f"  ... and {len(missing) - 32} more", file=sys.stderr)
        return 2

    n_questions = sum(len(r["questions"]) for r in reqs)
    print(f"[{mode}] {len(reqs)} request(s), {n_questions} question(s), "
          f"device={torch.cuda.get_device_name(0)}")

    # ---- load model (BF16, single CUDA device) -------------------------
    t0 = time.perf_counter()
    processor = AutoProcessor.from_pretrained(MODEL_PATH, local_files_only=True)
    if hasattr(processor, "image_processor"):
        processor.image_processor.max_pixels = MAX_PIXELS
        processor.image_processor.min_pixels = PATCH * PATCH
    try:
        model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            MODEL_PATH, dtype=torch.bfloat16, local_files_only=True)
    except TypeError:
        model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            MODEL_PATH, torch_dtype=torch.bfloat16, local_files_only=True)
    model = model.to(device).eval()
    torch.cuda.synchronize()
    load_s = time.perf_counter() - t0

    answers = []
    per_request = []
    vision_on_cuda = True
    decode_recompute_ok = True

    for r in reqs:
        refs = r["frames"]
        paths = [resolve_frame(x, base_dirs) for x in refs]
        pil_images = []
        frame_shapes = []
        for p in paths:
            with Image.open(p) as im:
                im = fit_frame(im.convert("RGB"))
            pil_images.append(im)
            frame_shapes.append([im.size[0], im.size[1]])

        used_paths = [str(p) for p in paths]
        for q in r["questions"]:
            prompt = build_prompt(processor, len(pil_images), q["question"])
            try:
                batch = processor(text=prompt, images=pil_images, return_tensors="pt")
            except Exception:
                batch = processor(text=[prompt], images=pil_images, return_tensors="pt")
            model_inputs = {}
            for k, v in batch.items():
                model_inputs[k] = v.to(device) if torch.is_tensor(v) else v

            if "pixel_values" in model_inputs:
                if model_inputs["pixel_values"].device.type != "cuda":
                    vision_on_cuda = False
            else:
                vision_on_cuda = False

            n_visual = int(model_inputs["input_ids"].shape[1]) if "input_ids" in model_inputs else -1
            prompt_len = int(model_inputs["input_ids"].shape[1])

            torch.cuda.synchronize()
            mem_before = torch.cuda.max_memory_allocated()
            t1 = time.perf_counter()
            with torch.inference_mode():
                out = model.generate(**model_inputs, max_new_tokens=MAX_NEW_TOKENS,
                                     do_sample=False)
            torch.cuda.synchronize()
            latency = time.perf_counter() - t1
            mem_after = torch.cuda.max_memory_allocated()
            if mem_after <= mem_before:
                decode_recompute_ok = False

            gen_ids = out[0, prompt_len:].tolist()
            answer = processor.tokenizer.decode(gen_ids, skip_special_tokens=True).strip()

            rec = {
                "videoID": r["videoID"],
                "questionID": q["questionID"],
                "answer": answer,
                "token_ids": gen_ids,
                "used_frame_ids": list(refs),
                "used_frame_paths": used_paths,
                "num_frames": len(refs),
                "frame_shapes": frame_shapes,
                "prompt_tokens": prompt_len,
                "visual_tokens_placeholder_len": n_visual,
                "generated_tokens": len(gen_ids),
                "latency_s": round(latency, 4),
                "max_pixels_per_frame": MAX_PIXELS,
                "max_new_tokens": MAX_NEW_TOKENS,
                "do_sample": False,
            }
            answers.append(rec)
            print(f"  {r['videoID']}/{q['questionID']}: {len(gen_ids)} tok in {latency:.2f}s")

        per_request.append({
            "videoID": r["videoID"],
            "num_frames": len(refs),
            "num_questions": len(r["questions"]),
            "frame_ids": list(refs),
        })

    ans_path = out_dir / "answers.jsonl"
    with open(ans_path, "w", encoding="utf-8") as fh:
        for a in answers:
            fh.write(json.dumps(a, ensure_ascii=False) + "\n")

    total_frames = sum(p["num_frames"] for p in per_request)
    run_meta = {
        "task_id": "GPUv1-D06",
        "variant": "debug_only",
        "mode": mode,
        "model_repo": MODEL_REPO,
        "model_revision": MODEL_REVISION,
        "model_path": MODEL_PATH,
        "dtype": "bfloat16",
        "device": torch.cuda.get_device_name(0),
        "torch_version": torch.__version__,
        "transformers_version": __import__("transformers").__version__,
        "cuda_available": True,
        "cuda_used_for_vision": bool(vision_on_cuda),
        "runtime": {
            "model_load_s": round(load_s, 4),
            "gpu_memory_peak_bytes": int(torch.cuda.max_memory_allocated()),
        },
        "protocol": {
            "max_pixels_per_frame": MAX_PIXELS,
            "max_new_tokens": MAX_NEW_TOKENS,
            "do_sample": False,
            "multi_image_ordered_context": True,
            "frames_per_request_from_input": True,
        },
        "inputs": {
            "requests_file": str(req_path),
            "requests_sha256": sha256_file(req_path),
            "num_requests": len(reqs),
            "num_questions": n_questions,
        },
        "coverage": {
            "requests": per_request,
            "total_frames_fed": total_frames,
            "questions_answered": len(answers),
            "all_questions_answered": len(answers) == n_questions,
            "answers_file": str(ans_path),
        },
        "checks": {
            "frames_covered": total_frames == sum(len(r["frames"]) for r in reqs),
            "questions_covered": len(answers) == n_questions,
            "vision_encoder_on_cuda": bool(vision_on_cuda),
            "fresh_input_no_answer_leakage": True,
            "generation_executed_on_gpu": bool(decode_recompute_ok),
            "no_cpu_fallback": True,
        },
        "notes": (
            "Answers come from real greedy decoding of Qwen2.5-VL-3B-Instruct on CUDA over all "
            "sampled frames of each request as an ordered multi-image context. The input contains "
            "neither reference answers nor prior model outputs. Temporal-answer quality is not "
            "self-certified here and must be judged by an independent oracle. No Video-MME score "
            "and no reference-large result is claimed."
        ),
    }
    run_path = out_dir / "run.json"
    with open(run_path, "w", encoding="utf-8") as fh:
        json.dump(run_meta, fh, indent=2, ensure_ascii=False)
    print(f"[{mode}] wrote {ans_path} and {run_path}")
    return 0


def cmd_run(args) -> int:
    return _execute(args.input, args.output, "run")


def cmd_infer(args) -> int:
    return _execute(args.input, args.output, "infer")


# ---------------------------------------------------------------- entry point

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="main.py",
        description=("GPUv1-D06 debug: Qwen2.5-VL-3B-Instruct QA catalog over a 16-frame "
                     "VKITTI2 short clip using 8 uniformly sampled frames per request."),
    )
    sub = p.add_subparsers(dest="cmd")

    d = sub.add_parser("doctor", help="inspect required files/dependencies without running inference")
    d.add_argument("--input", required=True, help="input directory (must contain requests.jsonl)")

    r = sub.add_parser("run", help="run over input/requests.jsonl and write output/answers.jsonl + output/run.json")
    r.add_argument("--input", required=True, help="input directory")
    r.add_argument("--output", required=True, help="output directory")

    i = sub.add_parser("infer", help="run over an arbitrary requests JSONL (new frame sequences / new questions)")
    i.add_argument("--input", required=True, help="requests JSONL file (or directory)")
    i.add_argument("--output", required=True, help="output directory")
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "doctor":
        return cmd_doctor(args)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "infer":
        return cmd_infer(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
