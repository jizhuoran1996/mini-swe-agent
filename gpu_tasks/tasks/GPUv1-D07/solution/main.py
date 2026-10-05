#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GPUv1-D07 (debug variant) - parse OmniDocBench pages into reusable Markdown.

Real Qwen2.5-VL-3B-Instruct image+text inference on CUDA in bfloat16, greedy
decoding, max_new_tokens=512, max_pixels=262144.  No mock weights, no random
substitute, no CPU fallback, no copied/placeholder page text.

Commands
  python solution/main.py --help
  python solution/main.py doctor --input input
  python solution/main.py run    --input input --output output
  python solution/main.py infer  --image page.png --prompt "..." --output page.json
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time

DEFAULT_MODEL_DIR = "/models/Qwen--Qwen2.5-VL-3B-Instruct"
MODEL_REPO = "Qwen/Qwen2.5-VL-3B-Instruct"
MODEL_REVISION = "66285546d2b821cf421d4f5eb2576359d3770cd3"
DATASET_REPO = "opendatalab/OmniDocBench"
DATASET_REVISION = "aa1ee96d106dbe53d0ae59474d75c6e6d9b53fec"
TASK_ID = "GPUv1-D07"
SCALE = "debug_only"
MAX_NEW_TOKENS = 512
MAX_PIXELS = 262144
INVALID_EXIT = 78

PAGE_PROMPT = (
    "You are a document parsing engine. Convert the document page image into "
    "GitHub-flavored Markdown.\n"
    "Rules:\n"
    "1. Preserve the natural reading order of the page.\n"
    "2. Reproduce every table as an HTML <table> block that keeps all rows and "
    "columns; never replace a table with an image or a plain-text dump.\n"
    "3. Reproduce every mathematical formula as LaTeX: inline $...$ and display $$...$$.\n"
    "4. Preserve headings, lists, captions and paragraph breaks.\n"
    "5. Do not add commentary, do not describe the page, do not wrap the answer "
    "in code fences.\n"
    "Output only the Markdown of the page."
)

TABLE_RE = re.compile(r"<table\b.*?</table>", re.IGNORECASE | re.DOTALL)


class InputError(Exception):
    """Raised when a required input, model file or dependency is absent."""


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_name(value):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(value)) or "page"


def extract_formulas(text):
    """Return [(kind, latex), ...] for display and inline formulas in `text`."""
    found = []
    for match in re.finditer(r"\$\$(.+?)\$\$", text, re.DOTALL):
        body = match.group(1).strip()
        if body:
            found.append(("display", body))
    without_display = re.sub(r"\$\$.+?\$\$", " ", text, flags=re.DOTALL)
    for match in re.finditer(r"(?<!\$)\$([^$\n]+?)\$(?!\$)", without_display):
        body = match.group(1).strip()
        if body:
            found.append(("inline", body))
    return found


def load_requests(input_dir):
    """Read requests.jsonl and resolve every page image path."""
    path = os.path.join(input_dir, "requests.jsonl")
    if not os.path.isfile(path):
        raise InputError("input file %s" % path)
    requests, seen = [], set()
    with open(path, "r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise InputError("requests.jsonl line %d is not JSON: %s" % (lineno, exc))
            if not isinstance(record, dict):
                raise InputError("requests.jsonl line %d is not a JSON object" % lineno)
            page_id = record.get("id", record.get("page_id", record.get("doc_id")))
            if page_id is None:
                raise InputError("requests.jsonl line %d has no id" % lineno)
            page_id = str(page_id)
            if page_id in seen:
                raise InputError("requests.jsonl contains duplicate id %s" % page_id)
            seen.add(page_id)
            image = record.get("image") or record.get("image_path") or record.get("image_file")
            if not image:
                image = os.path.join("images", page_id + ".png")
            if not os.path.isabs(image):
                image = os.path.join(input_dir, image)
            requests.append({"id": page_id, "image": os.path.normpath(image)})
    if not requests:
        raise InputError("requests.jsonl contains no page request")
    return requests


def probe_cuda(torch):
    """Report the CUDA device or raise SystemExit; inference never runs on CPU."""
    if torch is None or not torch.cuda.is_available():
        raise SystemExit(
            "[fatal] CUDA is required for GPUv1-D07; there is no CPU fallback for this task"
        )
    if torch.cuda.device_count() < 1:
        raise SystemExit("[fatal] no CUDA device reported by torch.cuda.device_count()")
    return torch.device("cuda:0")


def load_model(model_dir, torch):
    """Load the real Qwen2.5-VL processor and weights in bfloat16 on CUDA."""
    from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

    if not os.path.isdir(model_dir):
        raise InputError("model directory %s" % model_dir)
    processor = AutoProcessor.from_pretrained(model_dir, max_pixels=MAX_PIXELS)
    try:
        model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            model_dir, dtype=torch.bfloat16
        )
    except TypeError:
        model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            model_dir, torch_dtype=torch.bfloat16
        )
    model.to(torch.device("cuda:0"))
    model.eval()
    return processor, model


def run_single(processor, model, torch, image, prompt):
    """One greedy multimodal generation for one page image."""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": prompt},
            ],
        }
    ]
    chat = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[chat], images=[image], return_tensors="pt", padding=True)
    device = next(model.parameters()).device
    inputs = inputs.to(device)

    pixel_cuda = None
    pixel_shape = None
    if "pixel_values" in inputs:
        pixel_cuda = bool(inputs["pixel_values"].is_cuda)
        pixel_shape = list(inputs["pixel_values"].shape)
        if not pixel_cuda:
            raise RuntimeError("vision tensors are not on CUDA; refusing CPU prefill")
    if "image_grid_thw" in inputs and not bool(inputs["image_grid_thw"].is_cuda):
        raise RuntimeError("image_grid_thw is not on CUDA")

    prompt_tokens = int(inputs["input_ids"].shape[1])
    start_event = torch.cuda.Event(enable_timing=True)
    end_event = torch.cuda.Event(enable_timing=True)
    torch.cuda.synchronize()
    wall0 = time.perf_counter()
    start_event.record()
    with torch.inference_mode():
        output = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            num_beams=1,
            use_cache=True,
        )
    end_event.record()
    torch.cuda.synchronize()
    wall1 = time.perf_counter()

    generated = output[:, prompt_tokens:]
    token_ids = [int(t) for t in generated[0].tolist()]
    text = processor.batch_decode(
        generated, skip_special_tokens=True, clean_up_tokenization_spaces=False
    )[0]
    return {
        "text": text,
        "token_ids": token_ids,
        "prompt_tokens": prompt_tokens,
        "wall_s": wall1 - wall0,
        "gpu_event_s": start_event.elapsed_time(end_event) / 1000.0,
        "pixel_values_is_cuda": pixel_cuda,
        "pixel_values_shape": pixel_shape,
        "device": str(device),
    }


def cmd_doctor(args):
    ok, missing = [], []
    model_dir = args.model_dir
    if not os.path.isdir(model_dir):
        missing.append("model directory %s" % model_dir)
    else:
        ok.append("model directory %s" % model_dir)
        for rel in ("config.json", "tokenizer_config.json"):
            path = os.path.join(model_dir, rel)
            (ok if os.path.isfile(path) else missing).append("model file %s" % path)
        processor_cfg = [
            os.path.join(model_dir, name)
            for name in ("preprocessor_config.json", "processor_config.json")
        ]
        if any(os.path.isfile(p) for p in processor_cfg):
            ok.append("model processor config")
        else:
            missing.append(
                "model processor config (preprocessor_config.json / processor_config.json) in %s"
                % model_dir
            )
        shards = [
            name
            for name in sorted(os.listdir(model_dir))
            if name.endswith(".safetensors") or name.endswith(".bin")
        ]
        if shards:
            ok.append("model weights: %d shard file(s), first=%s" % (len(shards), shards[0]))
        else:
            missing.append("model weights (*.safetensors or *.bin) in %s" % model_dir)

    torch = None
    try:
        import torch as _torch

        torch = _torch
        ok.append("python module torch %s" % torch.__version__)
    except Exception as exc:  # pragma: no cover - environment dependent
        missing.append("python module torch (%s)" % exc)
    try:
        import transformers as _transformers

        ok.append("python module transformers %s" % _transformers.__version__)
        try:
            from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration  # noqa: F401

            ok.append("transformers exposes Qwen2_5_VLForConditionalGeneration and AutoProcessor")
        except Exception as exc:  # pragma: no cover
            missing.append("transformers Qwen2.5-VL classes (%s)" % exc)
    except Exception as exc:  # pragma: no cover
        missing.append("python module transformers (%s)" % exc)
    try:
        import PIL as _pil

        ok.append("python module PIL %s" % getattr(_pil, "__version__", "?"))
    except Exception as exc:  # pragma: no cover
        missing.append("python module PIL (%s)" % exc)
    try:
        import numpy as _numpy

        ok.append("python module numpy %s" % _numpy.__version__)
    except Exception as exc:  # pragma: no cover
        missing.append("python module numpy (%s)" % exc)

    if torch is not None:
        try:
            if torch.cuda.is_available():
                ok.append(
                    "CUDA available: %s (torch %s, cuda runtime %s, devices=%d)"
                    % (
                        torch.cuda.get_device_name(0),
                        torch.__version__,
                        torch.version.cuda,
                        torch.cuda.device_count(),
                    )
                )
            else:
                missing.append("CUDA device (torch.cuda.is_available() is False)")
        except Exception as exc:  # pragma: no cover
            missing.append("CUDA probe (%s)" % exc)

    try:
        requests = load_requests(args.input)
    except InputError as exc:
        missing.append(str(exc))
        requests = []
    for request in requests:
        if os.path.isfile(request["image"]):
            ok.append("page %s image %s" % (request["id"], request["image"]))
        else:
            missing.append("page %s image %s" % (request["id"], request["image"]))

    print("GPUv1-D07 doctor | input=%s | model=%s" % (args.input, args.model_dir))
    for item in ok:
        print("  [ok]   %s" % item)
    for item in missing:
        print("  [MISS] %s" % item)
    if missing:
        print("RESULT: %d missing item(s); do not run." % len(missing))
        return INVALID_EXIT
    print("RESULT: all required files and dependencies are available.")
    return 0


def cmd_run(args):
    import torch
    import transformers
    from PIL import Image

    device = probe_cuda(torch)
    requests = load_requests(args.input)
    for request in requests:
        if not os.path.isfile(request["image"]):
            raise InputError("page %s image %s" % (request["id"], request["image"]))

    output_dir = args.output
    pages_dir = os.path.join(output_dir, "pages")
    tables_dir = os.path.join(output_dir, "tables")
    for directory in (output_dir, pages_dir, tables_dir):
        os.makedirs(directory, exist_ok=True)

    torch.cuda.reset_peak_memory_stats(device)
    load_start = time.perf_counter()
    processor, model = load_model(args.model_dir, torch)
    torch.cuda.synchronize()
    load_s = time.perf_counter() - load_start
    visual_device = None
    visual = getattr(model, "visual", None)
    if visual is not None:
        try:
            visual_device = str(next(visual.parameters()).device)
        except StopIteration:
            visual_device = None

    run_start = time.perf_counter()
    documents, page_entries, page_status, formula_manifest = [], [], [], []
    written_ids = []
    for request in requests:
        page_id = request["id"]
        entry = {"id": page_id, "image": request["image"]}
        status_row = {"id": page_id, "status": "ok", "error": None}
        try:
            image_hash = sha256_file(request["image"])
            image = Image.open(request["image"])
            image = image.convert("RGB")
            entry["image_sha256"] = image_hash
            entry["image_size"] = list(image.size)
            result = run_single(processor, model, torch, image, PAGE_PROMPT)
            text = result["text"]

            markdown_path = os.path.join(pages_dir, safe_name(page_id) + ".md")
            with open(markdown_path, "w", encoding="utf-8") as handle:
                handle.write(text if text.endswith("\n") else text + "\n")

            tables = TABLE_RE.findall(text)
            for index, table_html in enumerate(tables):
                table_path = os.path.join(
                    tables_dir, "%s_%d.html" % (safe_name(page_id), index)
                )
                with open(table_path, "w", encoding="utf-8") as handle:
                    handle.write(table_html)
            formulas = extract_formulas(text)
            for index, (kind, latex) in enumerate(formulas):
                formula_manifest.append(
                    {
                        "id": page_id,
                        "index": index,
                        "kind": kind,
                        "latex": latex,
                        "markdown": os.path.relpath(markdown_path, output_dir),
                    }
                )

            documents.append(
                {
                    "id": page_id,
                    "text": text,
                    "token_ids": result["token_ids"],
                    "image_sha256": image_hash,
                    "image_path": request["image"],
                    "image_size": list(image.size),
                    "prompt_tokens": result["prompt_tokens"],
                    "tokens_generated": len(result["token_ids"]),
                    "pixel_values_is_cuda": result["pixel_values_is_cuda"],
                    "markdown_path": os.path.relpath(markdown_path, output_dir),
                }
            )
            entry.update(
                {
                    "status": "ok",
                    "prompt_tokens": result["prompt_tokens"],
                    "tokens_generated": len(result["token_ids"]),
                    "text_chars": len(text),
                    "tables": len(tables),
                    "formulas": len(formulas),
                    "wall_s": result["wall_s"],
                    "gpu_event_s": result["gpu_event_s"],
                    "pixel_values_is_cuda": result["pixel_values_is_cuda"],
                    "pixel_values_shape": result["pixel_values_shape"],
                    "markdown_path": os.path.relpath(markdown_path, output_dir),
                }
            )
            status_row.update(
                {
                    "markdown": os.path.relpath(markdown_path, output_dir),
                    "tables": len(tables),
                    "formulas": len(formulas),
                    "tokens_generated": len(result["token_ids"]),
                }
            )
            written_ids.append(page_id)
        except Exception as exc:  # keep the failure list, never fake a page
            entry.update(
                {"status": "failed", "error": "%s: %s" % (type(exc).__name__, exc)}
            )
            status_row.update({"status": "failed", "error": entry["error"]})
        page_entries.append(entry)
        page_status.append(status_row)

    torch.cuda.synchronize()
    total_s = time.perf_counter() - run_start

    with open(os.path.join(output_dir, "documents.jsonl"), "w", encoding="utf-8") as handle:
        for document in documents:
            handle.write(json.dumps(document, ensure_ascii=False) + "\n")
    with open(os.path.join(output_dir, "formula_manifest.jsonl"), "w", encoding="utf-8") as handle:
        for formula in formula_manifest:
            handle.write(json.dumps(formula, ensure_ascii=False) + "\n")
    with open(os.path.join(output_dir, "page_status.jsonl"), "w", encoding="utf-8") as handle:
        for row in page_status:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    config = {
        "task_id": TASK_ID,
        "scale": SCALE,
        "formal_large_tested": False,
        "deviation_note": "debug variant: four native OmniDocBench pages with the 3B VL model instead of 72B / 1651 pages",
        "model": MODEL_REPO,
        "model_revision": MODEL_REVISION,
        "model_dir": args.model_dir,
        "dataset": DATASET_REPO,
        "dataset_revision": DATASET_REVISION,
        "dtype": "bfloat16",
        "device": str(device),
        "max_new_tokens": MAX_NEW_TOKENS,
        "max_pixels": MAX_PIXELS,
        "decoding": {"strategy": "greedy", "do_sample": False, "num_beams": 1},
        "prompt": PAGE_PROMPT,
    }
    with open(os.path.join(output_dir, "config.json"), "w", encoding="utf-8") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=2)

    requested_ids = [request["id"] for request in requests]
    failed = [row["id"] for row in page_status if row["status"] != "ok"]
    report = {
        "task_id": TASK_ID,
        "scale": SCALE,
        "formal_large_tested": False,
        "run_kind": "omnidocbench_page_parsing_debug",
        "model": {
            "repo": MODEL_REPO,
            "revision": MODEL_REVISION,
            "local_dir": args.model_dir,
            "dtype": "bfloat16",
            "visual_device": visual_device,
        },
        "dataset": {"repo": DATASET_REPO, "revision": DATASET_REVISION},
        "environment": {
            "python": sys.version.split()[0],
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "cuda_runtime": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(0),
            "gpu_count": torch.cuda.device_count(),
        },
        "decoding": {"strategy": "greedy", "do_sample": False, "num_beams": 1,
                     "max_new_tokens": MAX_NEW_TOKENS},
        "image_processing": {"max_pixels": MAX_PIXELS},
        "prompt": PAGE_PROMPT,
        "timings": {
            "model_load_s": load_s,
            "generation_total_wall_s": total_s,
            "sum_page_wall_s": sum(e.get("wall_s", 0.0) for e in page_entries),
            "sum_page_gpu_event_s": sum(e.get("gpu_event_s", 0.0) for e in page_entries),
            "synchronized": True,
        },
        "memory": {
            "peak_allocated_gib": torch.cuda.max_memory_allocated(device) / (1024 ** 3),
            "peak_reserved_gib": torch.cuda.max_memory_reserved(device) / (1024 ** 3),
        },
        "pages": page_entries,
        "coverage": {
            "requested_ids": requested_ids,
            "written_ids": written_ids,
            "failed_ids": failed,
            "complete": len(written_ids) == len(requested_ids) and not failed,
        },
        "outputs": {
            "pages_dir": "pages",
            "documents": "documents.jsonl",
            "tables_dir": "tables",
            "formula_manifest": "formula_manifest.jsonl",
            "page_status": "page_status.jsonl",
            "config": "config.json",
        },
    }
    with open(os.path.join(output_dir, "run.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)

    print(
        "pages ok=%d failed=%d | generation wall=%.2fs | peak alloc=%.2f GiB"
        % (
            len(written_ids),
            len(failed),
            total_s,
            report["memory"]["peak_allocated_gib"],
        )
    )
    print("wrote %s" % os.path.join(output_dir, "run.json"))
    return 1 if failed else 0


def cmd_infer(args):
    import torch

    from PIL import Image

    device = probe_cuda(torch)
    if not os.path.isfile(args.image):
        raise InputError("image %s" % args.image)
    with open(args.image, "rb"):
        pass
    if not args.prompt or not args.prompt.strip():
        raise InputError("prompt must not be empty")

    started = time.perf_counter()
    processor, model = load_model(args.model_dir, torch)
    image = Image.open(args.image).convert("RGB")
    result = run_single(processor, model, torch, image, args.prompt)
    torch.cuda.synchronize()

    payload = {
        "task_id": TASK_ID,
        "kind": "fresh_page_inference",
        "model": MODEL_REPO,
        "model_revision": MODEL_REVISION,
        "model_dir": args.model_dir,
        "device": str(device),
        "dtype": "bfloat16",
        "decoding": {"strategy": "greedy", "do_sample": False, "num_beams": 1,
                     "max_new_tokens": MAX_NEW_TOKENS},
        "max_pixels": MAX_PIXELS,
        "image": os.path.abspath(args.image),
        "image_sha256": sha256_file(args.image),
        "image_size": list(image.size),
        "prompt": args.prompt,
        "text": result["text"],
        "token_ids": result["token_ids"],
        "prompt_tokens": result["prompt_tokens"],
        "tokens_generated": len(result["token_ids"]),
        "pixel_values_is_cuda": result["pixel_values_is_cuda"],
        "pixel_values_shape": result["pixel_values_shape"],
        "timings": {
            "wall_s": result["wall_s"],
            "gpu_event_s": result["gpu_event_s"],
            "total_s": time.perf_counter() - started,
            "synchronized": True,
        },
    }
    out_dir = os.path.dirname(os.path.abspath(args.output))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    print(
        "infer ok: %d tokens in %.2fs -> %s"
        % (payload["tokens_generated"], result["wall_s"], args.output)
    )
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="GPUv1-D07 debug: parse real OmniDocBench pages into Markdown with Qwen2.5-VL-3B-Instruct on CUDA.",
    )
    subparsers = parser.add_subparsers(dest="command")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--model-dir", default=DEFAULT_MODEL_DIR, help="local Qwen2.5-VL model directory"
    )

    doctor = subparsers.add_parser(
        "doctor",
        parents=[common],
        help="inspect the requested files and dependencies without loading models or running inference",
    )
    doctor.add_argument("--input", default="input", help="input directory with requests.jsonl and images/")
    doctor.set_defaults(func=cmd_doctor)

    run = subparsers.add_parser(
        "run", parents=[common], help="parse every requested page into output/pages/*.md"
    )
    run.add_argument("--input", default="input", help="input directory")
    run.add_argument("--output", default="output", help="output directory")
    run.set_defaults(func=cmd_run)

    infer = subparsers.add_parser(
        "infer", parents=[common], help="parse one fresh page image supplied on the command line"
    )
    infer.add_argument("--image", required=True, help="path to a new page image")
    infer.add_argument("--prompt", default=PAGE_PROMPT, help="parsing instruction sent with the image")
    infer.add_argument("--output", required=True, help="JSON file receiving text/token_ids/timings")
    infer.set_defaults(func=cmd_infer)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "func", None) is None:
        parser.print_help(sys.stderr)
        return 2
    try:
        return args.func(args) or 0
    except InputError as exc:
        print("[missing] %s" % exc, file=sys.stderr)
        return INVALID_EXIT


if __name__ == "__main__":
    sys.exit(main())
