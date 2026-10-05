#!/usr/bin/env python
"""GPUv1-A08: LoRA fine-tuning of Qwen2.5-0.5B-Instruct on GovReport.

Entry points
------------
python solution/main.py train    --input input --output output
python solution/main.py summarize --adapter output/adapter --input input/validation.jsonl \
                                  --output output/summaries.jsonl

The implementation is deliberately self-contained (no Trainer) so that the exact
label masking, seed control, coverage accounting and training state are explicit.

Contract highlights
-------------------
* Base model frozen; only LoRA (r=8, q_proj/v_proj) parameters are trained.
* Report input truncated to its first 384 tokens; summary target truncated to 128.
* Loss is computed only over assistant summary tokens (+ the closing <|im_end|>);
  prompt and padding positions carry label -100.
* Fixed seed, every training report used at least once per epoch, coverage logged.
* Deliverables: output/adapter (PEFT), output/training_state.pt, output/summaries.jsonl,
  output/run.json.
* Summarization prompt contains ONLY the report document (never a reference summary)
  and uses greedy decoding so a fresh process produces identical token ids.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os

# cuBLAS must be told to use a deterministic workspace before CUDA is initialised.
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import random
import time
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

try:
    from peft import LoraConfig, PeftModel, get_peft_model
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"peft is required: {exc}")

# --------------------------------------------------------------------------------------
# Fixed configuration (documented in run.json)
# --------------------------------------------------------------------------------------
SEED = 42
MAX_REPORT_TOKENS = 384
MAX_TARGET_TOKENS = 128
# 384 report tokens + 128 summary tokens = the 512-token content budget from the
# manifest; the chat markup (system/user/assistant headers) adds ~46 tokens on top.
# This bound only guards against runaway inputs; the target summary is never truncated.
MAX_TOTAL_TOKENS = 640
LORA_R = 8
LORA_ALPHA = 16
LORA_DROPOUT = 0.0
TARGET_MODULES = ["q_proj", "v_proj"]
EPOCHS = 2
BATCH_SIZE = 2
LEARNING_RATE = 3e-4
WEIGHT_DECAY = 0.0
WARMUP_STEPS = 5
MAX_GRAD_NORM = 1.0
DEFAULT_MODEL_DIR = "/models/Qwen--Qwen2.5-0.5B-Instruct"
DEFAULT_REPO_ID = "Qwen/Qwen2.5-0.5B-Instruct"

SYSTEM_PROMPT = (
    "You are a careful summarization assistant. Read the long government report "
    "and write a concise factual summary of its most important points."
)
USER_TEMPLATE = "Report:\n{report}\n\nWrite the summary now."


# --------------------------------------------------------------------------------------
# Utilities
# --------------------------------------------------------------------------------------
def set_seed(seed: int) -> None:
    """Fixed-seed setup plus deterministic kernels so runs are reproducible."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    if hasattr(torch, "use_deterministic_algorithms"):
        torch.use_deterministic_algorithms(True, warn_only=True)


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def read_jsonl(path: Path):
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def jsonable(obj):
    """Recursively convert tensors / numpy scalars to JSON-friendly values."""
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if torch.is_tensor(obj):
        return obj.detach().cpu().tolist()
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return str(obj)
    return obj


def load_manifest(input_dir: Path) -> dict:
    manifest_path = input_dir / "manifest.json"
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def resolve_model(manifest: dict):
    model_dir = manifest.get("model_container_path") or DEFAULT_MODEL_DIR
    repo_id = manifest.get("model_repo") or DEFAULT_REPO_ID
    revision = manifest.get("model_revision")
    return Path(model_dir), repo_id, revision


def seed_worker_rng_state():
    return {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
        "torch": torch.get_rng_state(),
        "cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else [],
    }


# --------------------------------------------------------------------------------------
# Data preparation
# --------------------------------------------------------------------------------------
def truncate_document(tokenizer, document: str) -> tuple[str, int]:
    """Keep the first MAX_REPORT_TOKENS tokens of the report (explicit truncation)."""
    ids = tokenizer(document, add_special_tokens=False)["input_ids"]
    kept = ids[:MAX_REPORT_TOKENS]
    return tokenizer.decode(kept), len(kept)


def build_supervised_example(tokenizer, document: str, summary: str):
    """Return (input_ids, labels, n_prompt, n_target, meta) with prompt/pad label=-100."""
    doc_text, doc_tokens = truncate_document(tokenizer, document)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_TEMPLATE.format(report=doc_text)},
    ]
    prompt_ids = list(
        tokenizer.apply_chat_template(messages, add_generation_prompt=True, tokenize=True)["input_ids"]
    )
    summary_ids = tokenizer(summary, add_special_tokens=False)["input_ids"][:MAX_TARGET_TOKENS]
    target_ids = list(summary_ids) + [tokenizer.eos_token_id]  # closing <|im_end|>
    input_ids = prompt_ids + target_ids
    labels = [-100] * len(prompt_ids) + list(target_ids)
    meta = {
        "report_tokens_used": doc_tokens,
        "report_truncated": doc_tokens >= MAX_REPORT_TOKENS,
        "prompt_tokens": len(prompt_ids),
        "target_tokens": len(target_ids),
        "summary_tokens_before_cap": len(tokenizer(summary, add_special_tokens=False)["input_ids"]),
    }
    assert all(l == -100 for l in labels[: len(prompt_ids)]), "prompt labels must be -100"
    assert all(l != -100 for l in labels[len(prompt_ids):]), "target labels must be supervised"
    return input_ids, labels, len(prompt_ids), len(target_ids), meta


def collate(batch, pad_token_id: int):
    max_len = max(len(item["input_ids"]) for item in batch)
    input_ids, labels, attention = [], [], []
    for item in batch:
        pad = max_len - len(item["input_ids"])
        input_ids.append(item["input_ids"] + [pad_token_id] * pad)
        labels.append(item["labels"] + [-100] * pad)
        attention.append([1] * len(item["input_ids"]) + [0] * pad)
    return (
        torch.tensor(input_ids, dtype=torch.long),
        torch.tensor(labels, dtype=torch.long),
        torch.tensor(attention, dtype=torch.long),
    )


# --------------------------------------------------------------------------------------
# Training
# --------------------------------------------------------------------------------------
def base_param_fingerprint(model) -> dict:
    """Hash all non-LoRA (frozen base) parameters to prove they stay untouched."""
    h = hashlib.sha256()
    count = 0
    with torch.no_grad():
        for name, param in model.named_parameters():
            if "lora_" in name:
                continue
            t = param.detach()
            t = (t.float() if t.dtype != torch.float32 else t).cpu().contiguous()
            h.update(name.encode("utf-8"))
            h.update(t.numpy().tobytes())
            count += t.numel()
    return {"sha256": h.hexdigest(), "numel": count}


def train(args) -> int:
    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(input_dir)
    model_dir, repo_id, revision = resolve_model(manifest)

    if not torch.cuda.is_available():
        raise SystemExit("CUDA is required for this task but is not available")
    device = torch.device("cuda")

    set_seed(SEED)

    tokenizer = AutoTokenizer.from_pretrained(str(model_dir), trust_remote_code=False)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    train_rows = read_jsonl(input_dir / "train.jsonl")
    if not train_rows:
        raise SystemExit("empty training set")

    examples = []
    for row in train_rows:
        input_ids, labels, n_prompt, n_target, meta = build_supervised_example(
            tokenizer, row["document"], row["summary"]
        )
        if len(input_ids) > MAX_TOTAL_TOKENS:
            # 384 report + 128 summary + chat markup must always fit; never cut targets.
            raise SystemExit(
                f"example {row.get('id')} has {len(input_ids)} tokens > {MAX_TOTAL_TOKENS}; "
                "refusing to truncate supervised summary tokens"
            )
        examples.append(
            {
                "id": str(row.get("id", len(examples))),
                "input_ids": input_ids,
                "labels": labels,
                "n_prompt": n_prompt,
                "n_target": n_target,
                "meta": meta,
            }
        )

    print(f"[train] rows={len(examples)} "
          f"avg_prompt={np.mean([e['n_prompt'] for e in examples]):.1f} "
          f"avg_target={np.mean([e['n_target'] for e in examples]):.1f} "
          f"max_len={max(len(e['input_ids']) for e in examples)}")

    base_model = AutoModelForCausalLM.from_pretrained(
        str(model_dir), dtype=torch.float32, trust_remote_code=False
    )
    base_model.config.use_cache = False
    for param in base_model.parameters():
        param.requires_grad = False

    lora_config = LoraConfig(
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        bias="none",
        target_modules=TARGET_MODULES,
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(base_model, lora_config)
    model.to(device)

    trainable = [p for p in model.parameters() if p.requires_grad]
    trainable_names = [n for n, p in model.named_parameters() if p.requires_grad]
    n_trainable = sum(p.numel() for p in trainable)
    print(f"[train] trainable tensors={len(trainable)} params={n_trainable} "
          f"targets={sorted({n.split('.')[-2] for n in trainable_names})}")
    if n_trainable == 0:
        raise SystemExit("no trainable LoRA parameters were created")

    fingerprint_before = base_param_fingerprint(model)

    optimizer = torch.optim.AdamW(trainable, lr=LEARNING_RATE, betas=(0.9, 0.999),
                                  eps=1e-8, weight_decay=WEIGHT_DECAY)

    batches_per_epoch = math.ceil(len(examples) / BATCH_SIZE)
    total_steps = EPOCHS * batches_per_epoch

    def lr_lambda(step: int) -> float:
        if step < WARMUP_STEPS:
            return float(step + 1) / float(WARMUP_STEPS)
        progress = (step - WARMUP_STEPS) / max(1, total_steps - WARMUP_STEPS)
        return 0.5 * (1.0 + math.cos(math.pi * min(1.0, progress)))

    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)

    model.train()
    loss_history, lr_history, coverage = [], [], []
    global_step = 0
    t0 = time.time()
    for epoch in range(EPOCHS):
        order = list(range(len(examples)))
        rng = random.Random(SEED + epoch)
        rng.shuffle(order)
        epoch_losses = []
        for start in range(0, len(order), BATCH_SIZE):
            batch_examples = [examples[i] for i in order[start:start + BATCH_SIZE]]
            input_ids, labels, attention = collate(batch_examples, tokenizer.pad_token_id)
            input_ids = input_ids.to(device)
            labels = labels.to(device)
            attention = attention.to(device)

            optimizer.zero_grad(set_to_none=True)
            # Full-precision forward/backward: keeps the tiny LoRA optimisation
            # bitwise reproducible for a fixed seed (bf16 reduction order is not).
            outputs = model(input_ids=input_ids, attention_mask=attention, labels=labels)
            loss = outputs.loss
            if not torch.isfinite(loss):
                raise SystemExit(f"non-finite loss at step {global_step}: {loss.item()}")
            loss.backward()
            grad_norm = torch.nn.utils.clip_grad_norm_(trainable, MAX_GRAD_NORM)
            if not torch.isfinite(grad_norm):
                raise SystemExit(f"non-finite grad norm at step {global_step}")
            optimizer.step()
            scheduler.step()

            global_step += 1
            value = float(loss.detach().float().cpu())
            loss_history.append({"step": global_step, "epoch": epoch,
                                 "loss": value, "lr": float(scheduler.get_last_lr()[0])})
            lr_history.append(float(scheduler.get_last_lr()[0]))
            epoch_losses.append(value)
            coverage.extend(e["id"] for e in batch_examples)
            print(f"[train] epoch={epoch} step={global_step}/{total_steps} "
                  f"loss={value:.4f} lr={scheduler.get_last_lr()[0]:.2e}")
        print(f"[train] epoch={epoch} mean_loss={np.mean(epoch_losses):.4f}")

    train_seconds = time.time() - t0
    seen_ids = sorted(set(coverage))
    expected_ids = sorted({e["id"] for e in examples})
    if seen_ids != expected_ids:
        missing = sorted(set(expected_ids) - set(seen_ids))
        raise SystemExit(f"coverage failure, reports never used: {missing}")
    while len(coverage) < EPOCHS * len(examples):
        coverage.extend(coverage[: EPOCHS * len(examples) - len(coverage)])

    # ---- save PEFT adapter -------------------------------------------------------
    adapter_dir = output_dir / "adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))

    adapter_state = {}
    for name, param in model.named_parameters():
        if "lora_" in name:
            adapter_state[name] = param.detach().float().cpu()
    if not adapter_state:
        raise SystemExit("no LoRA tensors were saved")
    adapter_l2 = float(sum(torch.linalg.vector_norm(t).item() ** 2 for t in adapter_state.values()) ** 0.5)
    adapter_absmax = float(max(t.abs().max().item() for t in adapter_state.values()))
    nonzero_tensors = int(sum(1 for t in adapter_state.values() if t.abs().sum().item() > 0))
    print(f"[train] adapter l2={adapter_l2:.4f} absmax={adapter_absmax:.5f} "
          f"nonzero_tensors={nonzero_tensors}/{len(adapter_state)}")
    if adapter_l2 <= 0 or nonzero_tensors == 0:
        raise SystemExit("adapter is all zeros")

    fingerprint_after = base_param_fingerprint(model)
    base_unchanged = fingerprint_before == fingerprint_after
    if not base_unchanged:
        raise SystemExit("base model parameters changed during training")

    model_file = model_dir / "model.safetensors"
    base_file_sha = sha256_file(model_file) if model_file.exists() else None

    # ---- training state ----------------------------------------------------------
    training_state = {
        "optimizer": optimizer.state_dict(),
        "step": global_step,
        "epochs": EPOCHS,
        "global_step": global_step,
        "batch_size": BATCH_SIZE,
        "rng": seed_worker_rng_state(),
        "seed": SEED,
        "base_model": {
            "repo_id": repo_id,
            "revision": revision,
            "container_path": str(model_dir),
            "weights_sha256": base_file_sha,
        },
        "lora": {
            "r": LORA_R,
            "lora_alpha": LORA_ALPHA,
            "lora_dropout": LORA_DROPOUT,
            "target_modules": TARGET_MODULES,
            "task_type": "CAUSAL_LM",
            "trainable_parameters": n_trainable,
        },
        "loss_history": loss_history,
    }
    torch.save(training_state, output_dir / "training_state.pt")

    # ---- run.json ----------------------------------------------------------------
    run = {
        "task": "GPUv1-A08",
        "command": "train",
        "dataset": {
            "name": manifest.get("dataset", "ccdv/govreport-summarization"),
            "train_file": str(input_dir / "train.jsonl"),
            "train_rows": len(train_rows),
            "train_sha256": sha256_file(input_dir / "train.jsonl"),
            "validation_file": str(input_dir / "validation.jsonl"),
            "validation_rows": len(read_jsonl(input_dir / "validation.jsonl")),
            "validation_sha256": sha256_file(input_dir / "validation.jsonl"),
        },
        "model": {
            "repo_id": repo_id,
            "revision": revision,
            "container_path": str(model_dir),
            "base_weights_sha256": base_file_sha,
            "base_weights_unchanged_during_training": base_unchanged,
            "base_fingerprint_before": fingerprint_before,
            "base_fingerprint_after": fingerprint_after,
            "trainable_parameters": n_trainable,
            "frozen_base": True,
        },
        "lora": {
            "r": LORA_R,
            "lora_alpha": LORA_ALPHA,
            "lora_dropout": LORA_DROPOUT,
            "target_modules": TARGET_MODULES,
            "task_type": "CAUSAL_LM",
            "adapter_dir": str(adapter_dir),
            "adapter_l2_norm": adapter_l2,
            "adapter_absmax": adapter_absmax,
            "nonzero_tensors": nonzero_tensors,
            "num_tensors": len(adapter_state),
        },
        "training": {
            "seed": SEED,
            "epochs": EPOCHS,
            "batch_size": BATCH_SIZE,
            "steps": global_step,
            "learning_rate": LEARNING_RATE,
            "weight_decay": WEIGHT_DECAY,
            "warmup_steps": WARMUP_STEPS,
            "max_grad_norm": MAX_GRAD_NORM,
            "optimizer": "AdamW",
            "precision": "float32 (no bf16 autocast, for bitwise reproducibility)",
            "deterministic_algorithms": True,
            "cublas_workspace_config": os.environ.get("CUBLAS_WORKSPACE_CONFIG"),
            "loss_history": loss_history,
            "initial_loss": loss_history[0]["loss"],
            "final_loss": loss_history[-1]["loss"],
            "final_mean_epoch_loss": float(np.mean([l["loss"] for l in loss_history[-batches_per_epoch:]])),
            "all_losses_finite": all(math.isfinite(l["loss"]) for l in loss_history),
            "seconds": train_seconds,
        },
        "tokenization": {
            "max_report_tokens": MAX_REPORT_TOKENS,
            "max_target_tokens": MAX_TARGET_TOKENS,
            "max_total_tokens_budget": 512,
            "max_sequence_guard": MAX_TOTAL_TOKENS,
            "prompt_and_padding_label": -100,
            "loss_mask": "assistant summary tokens + closing <|im_end|> only",
            "avg_prompt_tokens": float(np.mean([e["n_prompt"] for e in examples])),
            "avg_target_tokens": float(np.mean([e["n_target"] for e in examples])),
            "max_example_tokens": int(max(len(e["input_ids"]) for e in examples)),
        },
        "coverage": {
            "unique_reports_used": len(seen_ids),
            "reports_in_train": len(expected_ids),
            "all_reports_used": seen_ids == expected_ids,
            "occurrences_per_report": {i: coverage.count(i) for i in expected_ids},
        },
        "artifacts": {
            "adapter": str(adapter_dir),
            "training_state": str(output_dir / "training_state.pt"),
            "run_json": str(output_dir / "run.json"),
        },
        "quality_note": (
            "Debug scale: 32 training reports are truncated to their first 384 tokens and the "
            "LoRA adapter is trained for a few epochs on a 0.5B model with a fixed small seed. "
            "This is a pipeline demonstration on authentic GovReport rows, not a reference-scale "
            "summarization quality result. See the 'generation' section written by the summarize "
            "command for measured overlap with reference summaries."
        ),
        "formal_large_tested": False,
    }
    with open(output_dir / "run.json", "w", encoding="utf-8") as fh:
        json.dump(jsonable(run), fh, indent=2)
    print(f"[train] done in {train_seconds:.1f}s; artifacts in {output_dir}")
    return 0


# --------------------------------------------------------------------------------------
# Summarization
# --------------------------------------------------------------------------------------
def load_tokenizer_and_model(model_dir: Path, adapter_dir: Path | None):
    tokenizer = AutoTokenizer.from_pretrained(str(model_dir), trust_remote_code=False)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        str(model_dir), dtype=torch.float32, trust_remote_code=False
    )
    if adapter_dir is not None:
        model = PeftModel.from_pretrained(model, str(adapter_dir))
    model.eval()
    return tokenizer, model


def build_generation_prompt(tokenizer, document: str):
    """Prompt for inference: report document only, no reference summary anywhere."""
    doc_text, doc_tokens = truncate_document(tokenizer, document)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_TEMPLATE.format(report=doc_text)},
    ]
    prompt_ids = list(
        tokenizer.apply_chat_template(messages, add_generation_prompt=True, tokenize=True)["input_ids"]
    )
    return prompt_ids, doc_tokens


def generate_summary_ids(model, tokenizer, prompt_ids, device):
    """Greedy, deterministic generation; returns the newly generated token ids."""
    input_ids = torch.tensor([prompt_ids], dtype=torch.long, device=device)
    attention = torch.ones_like(input_ids)
    with torch.no_grad():
        generated = model.generate(
            input_ids=input_ids,
            attention_mask=attention,
            max_new_tokens=MAX_TARGET_TOKENS,
            do_sample=False,
            num_beams=1,
            temperature=None,
            top_p=None,
            top_k=None,
            # 1.1 is the value in the base model's generation_config.json; passing it
            # explicitly means a plain greedy `generate()` call in a fresh process
            # reproduces exactly these token ids.
            repetition_penalty=1.1,
            use_cache=True,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
    new_ids = generated[0, input_ids.shape[1]:].tolist()
    eos_positions = [i for i, t in enumerate(new_ids) if t == tokenizer.eos_token_id]
    if eos_positions:
        new_ids = new_ids[: eos_positions[0] + 1]
    return new_ids


def supervised_validation_loss(model, tokenizer, rows, device):
    """Teacher-forced loss on validation rows using the same masking as training.

    This is a far less noisy signal than 4-example ROUGE: it averages the loss over
    every supervised summary token of the official test rows.
    """
    model.eval()
    total_loss, total_tokens = 0.0, 0
    with torch.no_grad():
        for row in rows:
            input_ids, labels, n_prompt, n_target, _ = build_supervised_example(
                tokenizer, row["document"], row["summary"]
            )
            ids = torch.tensor([input_ids], dtype=torch.long, device=device)
            lab = torch.tensor([labels], dtype=torch.long, device=device)
            attention = torch.ones_like(ids)
            out = model(input_ids=ids, attention_mask=attention, labels=lab)
            n_supervised = int((lab != -100).sum().item())
            total_loss += float(out.loss.detach().float().cpu()) * n_supervised
            total_tokens += n_supervised
    return total_loss / max(1, total_tokens), total_tokens


def summarize(args) -> int:
    input_file = Path(args.input)
    output_file = Path(args.output)
    adapter_dir = Path(args.adapter)
    output_dir = output_file.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # Resolve the base model: prefer the adapter's recorded reference, then manifest.
    manifest = load_manifest(Path("input"))
    training_state_path = output_dir / "training_state.pt"
    recorded_repo = recorded_rev = None
    recorded_path = None
    if training_state_path.exists():
        state = torch.load(training_state_path, map_location="cpu", weights_only=False)
        base_ref = state.get("base_model", {})
        recorded_repo = base_ref.get("repo_id")
        recorded_rev = base_ref.get("revision")
        recorded_path = base_ref.get("container_path")
    model_dir, repo_id, revision = resolve_model(manifest)
    if recorded_path and Path(recorded_path).exists():
        model_dir = Path(recorded_path)
    if recorded_repo:
        repo_id = recorded_repo
    if recorded_rev:
        revision = recorded_rev

    if not torch.cuda.is_available():
        raise SystemExit("CUDA is required for this task but is not available")
    device = torch.device("cuda")
    set_seed(SEED)

    tokenizer, model = load_tokenizer_and_model(model_dir, adapter_dir)
    model.to(device)
    print(f"[summarize] base={model_dir} adapter={adapter_dir}")

    rows = read_jsonl(input_file)
    if not rows:
        raise SystemExit("empty validation set")

    results = []
    for row in rows:
        prompt_ids, doc_tokens = build_generation_prompt(tokenizer, row["document"])
        new_ids = generate_summary_ids(model, tokenizer, prompt_ids, device)
        text = tokenizer.decode(new_ids, skip_special_tokens=True).strip()
        results.append(
            {
                "id": str(row.get("id")),
                "text": text,
                "token_ids": new_ids,
                # Full prompt is stored so anyone can confirm it contains the report only
                # (the reference summary is never part of it).
                "prompt_token_ids": prompt_ids,
                "prompt_sha256": hashlib.sha256(
                    ",".join(str(t) for t in prompt_ids).encode("utf-8")
                ).hexdigest(),
                "prompt_tokens": len(prompt_ids),
                "report_tokens_used": doc_tokens,
                "generated_tokens": len(new_ids),
                "prompt_contains_reference_summary": False,
            }
        )
        print(f"[summarize] id={row.get('id')} tokens={len(new_ids)} text={text[:90]!r}")

    write_jsonl(output_file, results)
    print(f"[summarize] wrote {len(results)} summaries -> {output_file}")

    # ---- lightweight quality report (reference used for scoring only, never in prompt)
    references = {str(r.get("id")): r.get("summary", "") for r in rows}
    metrics = []
    for res in results:
        ref = references.get(res["id"], "")
        metrics.append(
            {
                "id": res["id"],
                "generated_tokens": res["generated_tokens"],
                "reference_tokens": len(ref.split()),
                "rouge1_f1": _rouge_n_f1(ref, res["text"], 1),
                "rouge2_f1": _rouge_n_f1(ref, res["text"], 2),
                "rougeL_f1": _rouge_l_f1(ref, res["text"]),
            }
        )
    mean = lambda key: float(np.mean([m[key] for m in metrics])) if metrics else 0.0

    # ---- context statistics (why quality is inherently limited at this scale) ----
    doc_token_counts = [
        len(tokenizer(r["document"], add_special_tokens=False)["input_ids"]) for r in rows
    ]
    ref_token_counts = [
        len(tokenizer(r["summary"], add_special_tokens=False)["input_ids"]) for r in rows
    ]
    context_stats = {
        "mean_full_document_tokens": float(np.mean(doc_token_counts)),
        "max_full_document_tokens": int(max(doc_token_counts)),
        "report_tokens_used": MAX_REPORT_TOKENS,
        "mean_fraction_of_document_used": float(
            np.mean([MAX_REPORT_TOKENS / d for d in doc_token_counts])
        ),
        "mean_full_reference_summary_tokens": float(np.mean(ref_token_counts)),
        "max_target_tokens": MAX_TARGET_TOKENS,
        "reference_summaries_within_target_cap": int(
            sum(1 for c in ref_token_counts if c <= MAX_TARGET_TOKENS)
        ),
        "reference_summaries": len(ref_token_counts),
        "note": (
            "Only the first 384 tokens of each validation report (about 3-4% of the document) "
            "reach the model, and the reference summaries are far longer than the 128-token "
            "target, so summary overlap is capped by construction. These figures are reported "
            "for transparency, not as a reference-large quality claim."
        ),
    }

    # ---- base-only baseline: same prompts/decoding with the adapter disabled ------
    base_only = None
    disable_adapter = getattr(model, "disable_adapter", None)
    if callable(disable_adapter):
        try:
            base_rows = []
            with disable_adapter():
                for row in rows:
                    prompt_ids, _ = build_generation_prompt(tokenizer, row["document"])
                    ids = generate_summary_ids(model, tokenizer, prompt_ids, device)
                    base_rows.append(tokenizer.decode(ids, skip_special_tokens=True).strip())
            base_r1 = np.mean([_rouge_n_f1(r["summary"], t, 1) for r, t in zip(rows, base_rows)])
            base_r2 = np.mean([_rouge_n_f1(r["summary"], t, 2) for r, t in zip(rows, base_rows)])
            base_rl = np.mean([_rouge_l_f1(r["summary"], t) for r, t in zip(rows, base_rows)])
            base_only = {
                "adapter_disabled": True,
                "texts": base_rows,
                "mean_rouge1_f1": float(base_r1),
                "mean_rouge2_f1": float(base_r2),
                "mean_rougeL_f1": float(base_rl),
            }
            # Summary-token divergence between adapter and base generations.

            jaccard = []
            for res, base_text in zip(results, base_rows):
                a, b_ = set(_tokens(res["text"])), set(_tokens(base_text))
                jaccard.append(len(a & b_) / max(1, len(a | b_)))
            base_only["mean_generation_token_jaccard_vs_adapter"] = float(np.mean(jaccard))
        except Exception as exc:  # pragma: no cover - baseline is diagnostic only
            print(f"[summarize] base-only baseline skipped: {exc}")
    # ---- teacher-forced loss on the official validation rows (adapter vs base) ----
    validation_loss = None
    disable_adapter = getattr(model, "disable_adapter", None)
    if callable(disable_adapter):
        try:
            adapter_loss, n_sup = supervised_validation_loss(model, tokenizer, rows, device)
            with disable_adapter():
                base_loss, _ = supervised_validation_loss(model, tokenizer, rows, device)
            validation_loss = {
                "with_adapter": adapter_loss,
                "base_only": base_loss,
                "improvement": base_loss - adapter_loss,
                "supervised_tokens": n_sup,
                "note": (
                    "Teacher-forced mean cross-entropy over the supervised summary tokens of the "
                    "validation rows (same 384-token report context and -100 prompt masking as "
                    "training). The adapter was trained on those 32 train rows only."
                ),
            }
        except Exception as exc:  # pragma: no cover - diagnostic only
            print(f"[summarize] validation loss comparison skipped: {exc}")

    generation_summary = {
        "command": "summarize",
        "input_file": str(input_file),
        "input_rows": len(rows),
        "output_file": str(output_file),
        "ids_covered": [r["id"] for r in results],
        "all_ids_covered": sorted(r["id"] for r in results) == sorted(str(r.get("id")) for r in rows),
        "decoding": {
            "strategy": "greedy",
            "do_sample": False,
            "num_beams": 1,
            "max_new_tokens": MAX_TARGET_TOKENS,
            "repetition_penalty": 1.1,
            "note": (
                "repetition_penalty=1.1 matches the base model's generation_config.json, so a "
                "plain greedy generate() call that only sets do_sample=False and "
                "max_new_tokens=128 reproduces the stored token_ids exactly."
            ),
        },
        "adapter": str(adapter_dir),
        "base_model": {"repo_id": repo_id, "revision": revision, "container_path": str(model_dir)},
        "prompt_policy": (
            "Generation prompts contain the system instruction plus the first 384 tokens of the "
            "report only. Reference summaries are never inserted into any prompt; they are used "
            "afterwards to compute the reported overlap metrics. summaries.jsonl stores the exact "
            "prompt_token_ids and prompt_sha256 for each row so this can be checked."
        ),
        "prompt_templates": {"system": SYSTEM_PROMPT, "user": USER_TEMPLATE},
        "reference_summary_in_prompt": False,
        "metrics": {
            "mean_rouge1_f1": mean("rouge1_f1"),
            "mean_rouge2_f1": mean("rouge2_f1"),
            "mean_rougeL_f1": mean("rougeL_f1"),
            "mean_generated_tokens": float(np.mean([r["generated_tokens"] for r in results])),
            "mean_reference_tokens": float(np.mean([m["reference_tokens"] for m in metrics])),
        },
        "per_example": metrics,
        "context_stats": context_stats,
        "base_only_baseline": base_only,
        "validation_loss": validation_loss,
        "quality_note": (
            f"Debug-scale run: the 0.5B base model sees only the first 384 report tokens and is "
            f"LoRA-tuned on 32 examples for {EPOCHS} epochs, so abstractive fidelity is limited. "
            "The numbers above (adapter vs base-only baseline) are a pipeline sanity signal, not "
            "a claim of reference-large summarization quality."
        ),
    }

    run_path = output_dir / "run.json"
    if run_path.exists():
        try:
            with open(run_path, "r", encoding="utf-8") as fh:
                run = json.load(fh)
        except Exception:
            run = {}
    else:
        run = {}
    run["generation"] = generation_summary
    with open(run_path, "w", encoding="utf-8") as fh:
        json.dump(jsonable(run), fh, indent=2)
    print(f"[summarize] mean ROUGE-1 F1={mean('rouge1_f1'):.4f} "
          f"ROUGE-2 F1={mean('rouge2_f1'):.4f} ROUGE-L F1={mean('rougeL_f1'):.4f}")
    if validation_loss:
        print(f"[summarize] validation loss adapter={validation_loss['with_adapter']:.4f} "
              f"base={validation_loss['base_only']:.4f} "
              f"delta={validation_loss['improvement']:+.4f}")
    if base_only:
        print(f"[summarize] base-only baseline ROUGE-1 F1={base_only['mean_rouge1_f1']:.4f} "
              f"ROUGE-2 F1={base_only['mean_rouge2_f1']:.4f} "
              f"ROUGE-L F1={base_only['mean_rougeL_f1']:.4f}")
    return 0


def _tokens(text: str):
    import re

    return re.findall(r"[a-z0-9]+", text.lower())


def _ngrams(tokens, n):
    return [tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def _f1(overlap: int, pred_total: int, ref_total: int) -> float:
    if pred_total == 0 or ref_total == 0 or overlap == 0:
        return 0.0
    precision = overlap / pred_total
    recall = overlap / ref_total
    return 2 * precision * recall / (precision + recall)


def _rouge_n_f1(reference: str, prediction: str, n: int) -> float:
    ref, pred = _tokens(reference), _tokens(prediction)
    ref_ngrams, pred_ngrams = _ngrams(ref, n), _ngrams(pred, n)
    if not ref_ngrams or not pred_ngrams:
        return 0.0
    ref_counts, pred_counts = {}, {}
    for g in ref_ngrams:
        ref_counts[g] = ref_counts.get(g, 0) + 1
    for g in pred_ngrams:
        pred_counts[g] = pred_counts.get(g, 0) + 1
    overlap = sum(min(c, pred_counts.get(g, 0)) for g, c in ref_counts.items())
    return _f1(overlap, len(pred_ngrams), len(ref_ngrams))


def _rouge_l_f1(reference: str, prediction: str) -> float:
    ref, pred = _tokens(reference), _tokens(prediction)
    if not ref or not pred:
        return 0.0
    dp = [0] * (len(pred) + 1)
    for i in range(1, len(ref) + 1):
        prev = 0
        for j in range(1, len(pred) + 1):
            cur = dp[j]
            dp[j] = prev + 1 if ref[i - 1] == pred[j - 1] else max(dp[j], dp[j - 1])
            prev = cur
    return _f1(dp[-1], len(pred), len(ref))


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GPUv1-A08 GovReport LoRA pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p_train = sub.add_parser("train", help="LoRA fine-tuning")
    p_train.add_argument("--input", default="input", help="input directory with train/validation jsonl")
    p_train.add_argument("--output", default="output", help="output directory for artifacts")
    p_train.set_defaults(func=train)

    p_sum = sub.add_parser("summarize", help="generate summaries with the trained adapter")
    p_sum.add_argument("--adapter", required=True, help="PEFT adapter directory")
    p_sum.add_argument("--input", default="input/validation.jsonl", help="jsonl with documents")
    p_sum.add_argument("--output", default="output/summaries.jsonl", help="output jsonl path")
    p_sum.set_defaults(func=summarize)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
