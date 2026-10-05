#!/usr/bin/env python
"""GPUv1-A01: adapt SmolLM2-135M-Instruct to UltraChat SFT and serve a reloadable checkpoint.

Entry points:
  python solution/main.py train --input input --output output [--resume output/training_state.pt --steps N]
  python solution/main.py infer --checkpoint output/checkpoint --input input/validation.jsonl --output output/responses.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import time
from typing import Dict, List, Optional

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    get_cosine_schedule_with_warmup,
)

DEFAULT_MODEL = "/models/HuggingFaceTB--SmolLM2-135M-Instruct"
MODEL_REVISION = "12fd25f77366fa6b3b4b768ec3050bf629380bac"


# ----------------------------------------------------------------------------- utils
def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_jsonl(path: str) -> List[Dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: str, rows: List[Dict]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def rng_state() -> Dict:
    st = {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
        "torch": torch.get_rng_state(),
    }
    if torch.cuda.is_available():
        st["cuda"] = torch.cuda.get_rng_state_all()
    return st


def load_rng_state(st: Dict) -> None:
    if "python" in st:
        random.setstate(st["python"])
    if "numpy" in st:
        np.random.set_state(st["numpy"])
    if "torch" in st:
        torch.set_rng_state(st["torch"])
    if "cuda" in st and torch.cuda.is_available():
        torch.cuda.set_rng_state_all(st["cuda"])


def prompt_prefix(messages: List[Dict]) -> List[Dict]:
    """Messages strictly before the first assistant turn (the user prompt)."""
    out = []
    for m in messages:
        if m.get("role") == "assistant":
            break
        out.append(m)
    if not out:
        out = messages[:1]
    return out


def render_ids(tokenizer, messages: List[Dict], add_generation_prompt: bool, max_tokens: int) -> List[int]:
    ids = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=add_generation_prompt,
    )
    if hasattr(ids, "keys") and "input_ids" in ids:  # BatchEncoding in newer transformers
        ids = ids["input_ids"]
    ids = list(ids)[:max_tokens]
    return ids


# ----------------------------------------------------------------------------- data
class ChatSFTDataset(Dataset):
    def __init__(self, rows: List[Dict], tokenizer, max_tokens: int):
        self.samples = []
        for r in rows:
            ids = render_ids(tokenizer, r["messages"], add_generation_prompt=False, max_tokens=max_tokens)
            if len(ids) < 2:
                continue
            self.samples.append({"id": r["id"], "input_ids": ids})

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, i: int) -> Dict:
        return self.samples[i]


class Collator:
    def __init__(self, pad_token_id: int):
        self.pad_token_id = pad_token_id

    def __call__(self, batch: List[Dict]) -> Dict[str, torch.Tensor]:
        maxlen = max(len(b["input_ids"]) for b in batch)
        input_ids, attn, labels = [], [], []
        for b in batch:
            ids = list(b["input_ids"])
            pad = maxlen - len(ids)
            input_ids.append(ids + [self.pad_token_id] * pad)
            attn.append([1] * len(ids) + [0] * pad)
            labels.append(ids + [-100] * pad)
        return {
            "input_ids": torch.tensor(input_ids, dtype=torch.long),
            "attention_mask": torch.tensor(attn, dtype=torch.long),
            "labels": torch.tensor(labels, dtype=torch.long),
        }


# ----------------------------------------------------------------------------- eval
@torch.no_grad()
def teacher_forced_loss(model, tokenizer, rows: List[Dict], max_tokens: int, device: torch.device,
                        batch_size: int = 8) -> float:
    model.eval()
    ds = ChatSFTDataset(rows, tokenizer, max_tokens)
    collator = Collator(tokenizer.pad_token_id)
    total_loss, total_tok = 0.0, 0
    for i in range(0, len(ds), batch_size):
        batch = collator([ds[j] for j in range(i, min(i + batch_size, len(ds)))])
        batch = {k: v.to(device) for k, v in batch.items()}
        out = model(**batch)
        ntok = int((batch["labels"] != -100).sum().item())
        total_loss += float(out.loss.item()) * ntok
        total_tok += ntok
    model.train()
    return total_loss / max(total_tok, 1)


def param_fingerprint(model) -> Dict[str, float]:
    total_sq = 0.0
    checksum = 0.0
    max_abs = 0.0
    for p in model.parameters():
        d = p.detach().float()
        total_sq += float((d * d).sum().item())
        checksum += float(d.sum().item())
        max_abs = max(max_abs, float(d.abs().max().item()))
    return {"l2": math.sqrt(total_sq), "sum": checksum, "max_abs": max_abs}


# ----------------------------------------------------------------------------- train
def parse_sync(args) -> argparse.Namespace:
    return args


def train(args) -> Dict:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("CUDA is required for training but is not available")

    os.makedirs(args.output, exist_ok=True)
    ckpt_dir = os.path.abspath(args.checkpoint if args.checkpoint else os.path.join(args.output, "checkpoint"))
    state_path = os.path.abspath(args.state if args.state else os.path.join(args.output, "training_state.pt"))
    train_path = os.path.join(args.input, "train.jsonl")
    val_path = os.path.join(args.input, "validation.jsonl")
    train_rows = read_jsonl(train_path)
    val_rows = read_jsonl(val_path) if os.path.exists(val_path) else []

    set_seed(args.seed)

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    model_source = args.model
    resume_state: Optional[Dict] = None
    if args.resume:
        if not os.path.exists(args.resume):
            raise FileNotFoundError(f"resume state not found: {args.resume}")
        resume_state = torch.load(args.resume, map_location="cpu", weights_only=False)
        state_ckpt = resume_state.get("checkpoint_dir")
        if state_ckpt and os.path.isdir(state_ckpt):
            model_source = state_ckpt
        elif os.path.isdir(ckpt_dir):
            model_source = ckpt_dir
        print(f"[train] resuming from state={args.resume} model={model_source} step={resume_state.get('step')}")

    model = AutoModelForCausalLM.from_pretrained(model_source, dtype=torch.float32)
    model.to(device)
    model.train()

    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    ds = ChatSFTDataset(train_rows, tokenizer, args.max_tokens)
    n_examples = len(ds)
    if n_examples == 0:
        raise RuntimeError("no usable training examples")

    collator = Collator(tokenizer.pad_token_id)
    gen = torch.Generator()
    gen.manual_seed(args.seed)
    loader = DataLoader(ds, batch_size=args.batch_size, shuffle=True, generator=gen,
                        collate_fn=collator, drop_last=False)

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay, betas=(0.9, 0.95))

    steps_per_epoch = math.ceil(n_examples / args.batch_size)
    if args.resume and args.steps is not None:
        extra_steps = int(args.steps)
    elif args.steps is not None:
        extra_steps = int(args.steps)
    else:
        extra_steps = None

    if args.resume:
        start_step = int(resume_state.get("step", 0))
        this_run_steps = extra_steps if extra_steps is not None else args.epochs * steps_per_epoch
        total_steps = start_step + this_run_steps
    else:
        start_step = 0
        this_run_steps = extra_steps if extra_steps is not None else args.epochs * steps_per_epoch
        total_steps = this_run_steps
    this_run_steps = max(int(this_run_steps), 1)
    total_steps = max(total_steps, start_step + this_run_steps, 1)
    warmup = max(1, int(args.warmup_ratio * total_steps))

    scheduler = get_cosine_schedule_with_warmup(optimizer, num_warmup_steps=warmup,
                                                num_training_steps=total_steps)
    if args.resume:
        if "optimizer" in resume_state:
            optimizer.load_state_dict(resume_state["optimizer"])
        if "scheduler" in resume_state:
            try:
                scheduler.load_state_dict(resume_state["scheduler"])
            except Exception as exc:  # pragma: no cover
                print(f"[train] scheduler state not restored ({exc}); keeping fresh schedule")
        if "rng" in resume_state:
            load_rng_state(resume_state["rng"])

    # ---- loss before (teacher-forced, validation split per spec)
    if val_rows:
        loss_before = teacher_forced_loss(model, tokenizer, val_rows, args.max_tokens, device)
    else:
        loss_before = teacher_forced_loss(model, tokenizer, train_rows, args.max_tokens, device)
    fp_before = param_fingerprint(model)

    # ---- optimization loop
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    step = start_step
    accum = 0
    epoch = 0
    micro = 0
    optimizer.zero_grad(set_to_none=True)
    target_step = step + this_run_steps

    loss_trace = []
    while step < target_step:
        epoch_loss, epoch_ntok = 0.0, 0
        for batch in loader:
            batch = {k: v.to(device) for k, v in batch.items()}
            out = model(**batch)
            loss = out.loss
            (loss / args.grad_accum).backward()
            accum += 1
            ntok = int((batch["labels"] != -100).sum().item())
            epoch_loss += float(loss.item()) * ntok
            epoch_ntok += ntok
            micro += 1
            if accum % args.grad_accum == 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), args.max_grad_norm)
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad(set_to_none=True)
                step += 1
                loss_trace.append(epoch_loss / max(epoch_ntok, 1))
                if step >= target_step:
                    break
        epoch += 1
        if epoch > 10000:
            break

    torch.cuda.synchronize()
    train_seconds = time.perf_counter() - t0
    model.eval()
    fp_after = param_fingerprint(model)

    # ---- losses after
    if val_rows:
        loss_after = teacher_forced_loss(model, tokenizer, val_rows, args.max_tokens, device)
        val_loss_after = loss_after
        val_loss_before = loss_before
        train_loss_after = teacher_forced_loss(model, tokenizer, train_rows, args.max_tokens, device)
    else:
        loss_after = teacher_forced_loss(model, tokenizer, train_rows, args.max_tokens, device)
        val_loss_after = None
        val_loss_before = None
        train_loss_after = loss_after
    train_loss_before = None
    # loss_before/after are the validation teacher-forced losses required by the spec

    # ---- save HF checkpoint + tokenizer + config
    os.makedirs(ckpt_dir, exist_ok=True)
    model.save_pretrained(ckpt_dir, safe_serialization=True)
    tokenizer.save_pretrained(ckpt_dir)
    with open(os.path.join(ckpt_dir, "model_meta.json"), "w", encoding="utf-8") as f:
        json.dump({
            "base_model": args.model,
            "base_model_revision": MODEL_REVISION,
            "max_tokens": args.max_tokens,
            "trained_on": os.path.abspath(train_path),
            "task": "GPUv1-A01",
        }, f, indent=2)

    # ---- training state for exact resume
    state = {
        "step": step,
        "epoch": epoch,
        "micro_steps": micro,
        "optimizer": optimizer.state_dict(),
        "scheduler": scheduler.state_dict(),
        "rng": rng_state(),
        "seed": args.seed,
        "max_tokens": args.max_tokens,
        "batch_size": args.batch_size,
        "grad_accum": args.grad_accum,
        "lr": args.lr,
        "weight_decay": args.weight_decay,
        "warmup_ratio": args.warmup_ratio,
        "model": args.model,
        "model_revision": MODEL_REVISION,
        "checkpoint_dir": ckpt_dir,
        "train_examples": n_examples,
        "train_file": os.path.abspath(train_path),
        "input_hashes": {
            "train.jsonl": sha256_file(train_path),
            "validation.jsonl": sha256_file(val_path) if os.path.exists(val_path) else None,
        },
    }
    torch.save(state, state_path)

    n_param = sum(p.numel() for p in model.parameters())
    max_delta = 0.0
    changed = 0
    # re-measure per-parameter delta against the base weights for the "weights actually changed" check
    base = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.float32)
    with torch.no_grad():
        for (n1, p1), (n2, p2) in zip(base.named_parameters(), model.named_parameters()):
            d = (p1.float() - p2.detach().float().cpu()).abs().max().item()
            if d > 0:
                changed += 1
            max_delta = max(max_delta, d)
    del base

    run = {
        "task_id": "GPUv1-A01",
        "train_examples": n_examples,
        "optimizer_steps": step,
        "optimizer_steps_this_run": step - start_step,
        "seed": args.seed,
        "loss_before": loss_before,
        "loss_after": loss_after,
        "val_loss_before": val_loss_before,
        "val_loss_after": val_loss_after,
        "train_loss_after": train_loss_after,
        "device": str(device),
        "gpu": torch.cuda.get_device_name(0),
        "dtype": "float32",
        "resumed": bool(args.resume),
        "start_step": start_step,
        "loss_trace": loss_trace,
        "weight_change": {
            "max_abs_delta": max_delta,
            "params_changed": changed,
            "fingerprint_before": fp_before,
            "fingerprint_after": fp_after,
        },
        "train_seconds_synchronized": train_seconds,
        "training_params": {
            "model_path": args.model,
            "model_revision": MODEL_REVISION,
            "method": "full_finetune",
            "max_tokens": args.max_tokens,
            "batch_size": args.batch_size,
            "grad_accum": args.grad_accum,
            "epochs": args.epochs,
            "lr": args.lr,
            "weight_decay": args.weight_decay,
            "warmup_ratio": args.warmup_ratio,
            "max_grad_norm": args.max_grad_norm,
            "total_params": n_param,
            "trainable_params": n_param,
            "target_steps": total_steps,
        },
        "input_hashes": state["input_hashes"],
        "checkpoint_dir": ckpt_dir,
        "training_state_path": state_path,
    }
    run_path = os.path.join(args.output, "run.json")
    if os.path.exists(run_path):
        try:
            prev = json.load(open(run_path))
            hist = prev.get("history", [])
        except Exception:
            hist = []
    else:
        hist = []
    run["history"] = hist + [{
        "resumed": bool(args.resume),
        "start_step": start_step,
        "optimizer_steps": step,
        "loss_before": loss_before,
        "loss_after": loss_after,
        "train_seconds_synchronized": train_seconds,
    }]
    with open(run_path, "w", encoding="utf-8") as f:
        json.dump(run, f, indent=2, ensure_ascii=False)

    print(json.dumps({k: run[k] for k in [
        "train_examples", "optimizer_steps", "optimizer_steps_this_run", "loss_before",
        "loss_after", "device", "train_seconds_synchronized"]}, indent=2))
    return run


# ----------------------------------------------------------------------------- infer
@torch.no_grad()
def infer(args) -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ckpt = args.checkpoint
    tokenizer = AutoTokenizer.from_pretrained(ckpt)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(ckpt, dtype=torch.float32).to(device)
    model.eval()

    rows = read_jsonl(args.input)
    out_rows = []
    for r in rows:
        prefix = prompt_prefix(r["messages"])
        prompt_text = tokenizer.apply_chat_template(prefix, tokenize=False, add_generation_prompt=True)
        prompt_ids = render_ids(tokenizer, prefix, add_generation_prompt=True, max_tokens=args.max_tokens)
        prompt_text_trunc = tokenizer.decode(prompt_ids, skip_special_tokens=False)
        inputs = torch.tensor([prompt_ids], dtype=torch.long, device=device)
        attn = torch.ones_like(inputs)
        gen = model.generate(
            inputs,
            attention_mask=attn,
            max_new_tokens=args.max_new_tokens,
            min_new_tokens=1,
            do_sample=False,
            eos_token_id=tokenizer.eos_token_id,
            pad_token_id=tokenizer.pad_token_id,
            repetition_penalty=1.0,
        )
        new_ids = gen[0, inputs.shape[1]:].tolist()
        # guarantee a non-empty textual response (still within 1..32 new tokens)
        if tokenizer.decode(new_ids, skip_special_tokens=True).strip() == "" and len(new_ids) < args.max_new_tokens:
            gen = model.generate(
                inputs,
                attention_mask=attn,
                max_new_tokens=args.max_new_tokens,
                min_new_tokens=1,
                do_sample=False,
                eos_token_id=None,
                pad_token_id=tokenizer.pad_token_id,
            )
            new_ids = gen[0, inputs.shape[1]:].tolist()
        new_ids = [int(t) for t in new_ids][: args.max_new_tokens]
        text = tokenizer.decode(new_ids, skip_special_tokens=True).strip()
        out_rows.append({
            "id": r["id"],
            "prompt": prompt_text_trunc,
            "generated_text": text,
            "generated_token_ids": new_ids,
        })

    write_jsonl(args.output, out_rows)
    lens = [len(r["generated_token_ids"]) for r in out_rows]
    print(json.dumps({
        "responses": len(out_rows),
        "min_new_tokens": min(lens) if lens else 0,
        "max_new_tokens": max(lens) if lens else 0,
        "output": os.path.abspath(args.output),
    }, indent=2))


# ----------------------------------------------------------------------------- cli
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="GPUv1-A01 SmolLM2-135M-Instruct UltraChat SFT")
    sub = p.add_subparsers(dest="command", required=True)

    t = sub.add_parser("train")
    t.add_argument("--input", default="input")
    t.add_argument("--output", default="output")
    t.add_argument("--model", default=DEFAULT_MODEL)
    t.add_argument("--checkpoint", default=None)
    t.add_argument("--state", default=None)
    t.add_argument("--resume", default=None, help="path to training_state.pt to continue from")
    t.add_argument("--steps", type=int, default=None,
                   help="on fresh run: total optimizer steps; on --resume: extra optimizer steps")
    t.add_argument("--epochs", type=int, default=3)
    t.add_argument("--batch-size", type=int, default=4)
    t.add_argument("--grad-accum", type=int, default=1)
    t.add_argument("--lr", type=float, default=2e-5)
    t.add_argument("--weight-decay", type=float, default=0.0)
    t.add_argument("--warmup-ratio", type=float, default=0.05)
    t.add_argument("--max-grad-norm", type=float, default=1.0)
    t.add_argument("--max-tokens", type=int, default=256)
    t.add_argument("--seed", type=int, default=42)

    i = sub.add_parser("infer")
    i.add_argument("--checkpoint", required=True)
    i.add_argument("--input", required=True)
    i.add_argument("--output", required=True)
    i.add_argument("--max-tokens", type=int, default=256)
    i.add_argument("--max-new-tokens", type=int, default=32)
    return p


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "train":
        train(args)
    elif args.command == "infer":
        infer(args)


if __name__ == "__main__":
    main()
