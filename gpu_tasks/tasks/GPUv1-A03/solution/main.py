#!/usr/bin/env python
"""GPUv1-A03 (debug variant): offline EN->DE Marian fine-tuning + translation.

Entry points
------------
train      : CUDA seq2seq teacher-forcing fine-tune of the provided Marian
             checkpoint on input/train.jsonl, then dump a reusable HF checkpoint,
             training_state.pt (optimizer/step/RNG) and run.json.
translate  : load the fine-tuned checkpoint and translate input/validation.jsonl
             using the English source only; writes translations.jsonl.

All artefacts are written by this script; the code below is the only source
of the delivered solution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import sys
import time
from typing import Any, Dict, List, Sequence

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset
from transformers import MarianMTModel, MarianTokenizer

# --------------------------------------------------------------------------- #
# Fixed configuration (spec: fixed seed, max_length=128, target padding = -100)
# --------------------------------------------------------------------------- #
SEED = 20240517
MAX_LENGTH = 128
IGNORE_INDEX = -100
MODEL_DIR_DEFAULT = "/models/Helsinki-NLP--opus-mt-en-de"
MODEL_REVISION = "6183067f769a302e3861815543b9f312c71b0ca4"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def set_seed(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def sync_time() -> float:
    """Wall-clock time after a CUDA synchronisation (true elapsed seconds)."""
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    return time.perf_counter()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: str, rows: Sequence[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_json(path: str, obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def rng_snapshot() -> Dict[str, Any]:
    snap: Dict[str, Any] = {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
        "torch": torch.get_rng_state(),
    }
    if torch.cuda.is_available():
        snap["torch_cuda"] = torch.cuda.get_rng_state_all()
    return snap


def param_checksum(model: torch.nn.Module) -> Dict[str, Any]:
    """Cheap but real fingerprint of the live weights (sum + L2 norm + count)."""
    total = 0.0
    sq = 0.0
    count = 0
    for p in model.parameters():
        d = p.detach().float().cpu()
        total += float(d.sum().item())
        sq += float((d * d).sum().item())
        count += int(d.numel())
    return {"sum": total, "l2": float(sq ** 0.5), "numel": count}



# --------------------------------------------------------------------------- #
# Debug-only quality metrics (self-contained; NOT an official benchmark run)
# --------------------------------------------------------------------------- #
_PUNCT = set('!\"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~')


def _tok_13a(text: str) -> List[str]:
    """Minimal mteval-v13a-style tokenisation (lowercase, punctuation split)."""
    out = []
    for word in text.strip().lower().split():
        buf = []
        for ch in word:
            if ch in _PUNCT:
                if buf:
                    out.append("".join(buf))
                    buf = []
                out.append(ch)
            else:
                buf.append(ch)
        if buf:
            out.append("".join(buf))
    return out


def _ngrams(tokens: Sequence[Any], n: int) -> Dict[Any, int]:
    counts: Dict[Any, int] = {}
    for i in range(len(tokens) - n + 1):
        key = tuple(tokens[i:i + n])
        counts[key] = counts.get(key, 0) + 1
    return counts


def corpus_bleu(hypotheses: Sequence[str], references: Sequence[str], max_order: int = 4) -> float:
    """Corpus BLEU (no smoothing), debug implementation."""
    matches = [0] * (max_order + 1)
    totals = [0] * (max_order + 1)
    hyp_len = ref_len = 0
    for hyp, ref in zip(hypotheses, references):
        h, r = _tok_13a(hyp), _tok_13a(ref)
        hyp_len += len(h)
        ref_len += len(r)
        for n in range(1, max_order + 1):
            hg, rg = _ngrams(h, n), _ngrams(r, n)
            totals[n] += max(len(h) - n + 1, 0)
            matches[n] += sum(min(c, rg.get(g, 0)) for g, c in hg.items())
    if hyp_len == 0:
        return 0.0
    bp = 1.0 if hyp_len > ref_len else float(np.exp(1.0 - ref_len / max(hyp_len, 1)))
    log_sum = 0.0
    for n in range(1, max_order + 1):
        if matches[n] == 0 or totals[n] == 0:
            return 0.0
        log_sum += np.log(matches[n] / totals[n])
    return float(bp * np.exp(log_sum / max_order) * 100.0)


def corpus_chrf(hypotheses: Sequence[str], references: Sequence[str],
                max_order: int = 6, beta: float = 2.0) -> float:
    """chrF (character n-gram F-score, whitespace removed), debug implementation."""
    def chars(text: str) -> List[str]:
        return [c for c in text if not c.isspace()]

    scores = []
    for n in range(1, max_order + 1):
        match = hyp_total = ref_total = 0
        for hyp, ref in zip(hypotheses, references):
            hg = _ngrams(chars(hyp), n)
            rg = _ngrams(chars(ref), n)
            hyp_total += sum(hg.values())
            ref_total += sum(rg.values())
            match += sum(min(c, rg.get(g, 0)) for g, c in hg.items())
        prec = match / hyp_total if hyp_total else 0.0
        rec = match / ref_total if ref_total else 0.0
        if prec + rec == 0:
            scores.append(0.0)
        else:
            b2 = beta * beta
            scores.append((1 + b2) * prec * rec / (b2 * prec + rec))
    return float(np.mean(scores) * 100.0)


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
class ParallelDataset(Dataset):
    """EN/DE sentence pairs, tokenised on demand (source | target)."""

    def __init__(self, rows: Sequence[Dict[str, Any]], tokenizer, max_length: int):
        self.rows = list(rows)
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        row = self.rows[idx]
        src = self.tokenizer(
            row["en"], truncation=True, max_length=self.max_length, add_special_tokens=True
        )
        tgt = self.tokenizer(
            row["de"], truncation=True, max_length=self.max_length, add_special_tokens=True
        )
        return {
            "id": row["id"],
            "en": row["en"],
            "de": row["de"],
            "input_ids": list(src["input_ids"]),
            "attention_mask": list(src["attention_mask"]),
            "labels": list(tgt["input_ids"]),  # padding -> -100 in the collator
        }


def make_collator(pad_token_id: int, ignore_index: int = IGNORE_INDEX):
    def collate(features: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        max_src = max(len(f["input_ids"]) for f in features)
        max_tgt = max(len(f["labels"]) for f in features)
        input_ids, attn, labels = [], [], []
        for f in features:
            src_ids = list(f["input_ids"])
            src_mask = list(f["attention_mask"])
            tgt_ids = list(f["labels"])
            pad_src = max_src - len(src_ids)
            pad_tgt = max_tgt - len(tgt_ids)
            input_ids.append(src_ids + [pad_token_id] * pad_src)
            attn.append(src_mask + [0] * pad_src)
            labels.append(tgt_ids + [ignore_index] * pad_tgt)
        return {
            "input_ids": torch.tensor(input_ids, dtype=torch.long),
            "attention_mask": torch.tensor(attn, dtype=torch.long),
            "labels": torch.tensor(labels, dtype=torch.long),
            "ids": [f["id"] for f in features],
        }

    return collate


# --------------------------------------------------------------------------- #
# Teacher-forced NLL
# --------------------------------------------------------------------------- #
def teacher_forcing_nll(
    model: MarianMTModel,
    dataset: Dataset,
    collator,
    device: torch.device,
    batch_size: int,
) -> Dict[str, Any]:
    """Token-weighted teacher-forcing negative log-likelihood (eval mode)."""
    was_training = model.training
    model.eval()
    loader = DataLoader(
        dataset, batch_size=batch_size, shuffle=False, collate_fn=collator, num_workers=0
    )
    total_nll = 0.0
    total_tokens = 0
    with torch.no_grad():
        for batch in loader:
            labels = batch["labels"].to(device)
            out = model(
                input_ids=batch["input_ids"].to(device),
                attention_mask=batch["attention_mask"].to(device),
                labels=labels,
            )
            n_tok = int((labels != IGNORE_INDEX).sum().item())
            total_nll += float(out.loss.item()) * n_tok
            total_tokens += n_tok
    if was_training:
        model.train()
    mean_nll = total_nll / max(total_tokens, 1)
    return {
        "mean_nll": mean_nll,
        "perplexity": float(np.exp(mean_nll)) if mean_nll < 50 else float("inf"),
        "target_tokens": total_tokens,
    }


# --------------------------------------------------------------------------- #
# train
# --------------------------------------------------------------------------- #
def cmd_train(args: argparse.Namespace) -> int:
    t_start = sync_time()
    set_seed(args.seed)
    os.makedirs(args.output, exist_ok=True)
    checkpoint_dir = args.checkpoint or os.path.join(args.output, "checkpoint")

    train_path = os.path.join(args.input, "train.jsonl")
    valid_path = os.path.join(args.input, "validation.jsonl")
    train_rows = read_jsonl(train_path)
    valid_rows = read_jsonl(valid_path)
    source_hashes = {
        "train.jsonl": sha256_file(train_path),
        "validation.jsonl": sha256_file(valid_path),
        "model_dir": MODEL_DIR_DEFAULT,
        "model_revision": MODEL_REVISION,
        "model_files": {
            name: sha256_file(os.path.join(args.model_dir, name))
            for name in ("config.json", "pytorch_model.bin", "vocab.json",
                         "source.spm", "target.spm")
            if os.path.exists(os.path.join(args.model_dir, name))
        },
    }

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        print("[warn] CUDA unavailable, running on CPU", file=sys.stderr)

    tokenizer = MarianTokenizer.from_pretrained(args.model_dir)
    model = MarianMTModel.from_pretrained(args.model_dir).to(device)
    pad_token_id = int(tokenizer.pad_token_id)
    model.config.pad_token_id = pad_token_id

    train_ds = ParallelDataset(train_rows, tokenizer, args.max_length)
    valid_ds = ParallelDataset(valid_rows, tokenizer, args.max_length)
    collator = make_collator(pad_token_id)

    # ---- before-loss (frozen pretrained weights) -------------------------- #
    t = sync_time()
    before_train = teacher_forcing_nll(model, train_ds, collator, device, args.batch_size)
    before_valid = teacher_forcing_nll(model, valid_ds, collator, device, args.batch_size)
    before_time = sync_time() - t
    before_fingerprint = param_checksum(model)

    # ---- optimiser / training --------------------------------------------- #
    optim = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.0)
    loader = DataLoader(
        train_ds, batch_size=args.batch_size, shuffle=True, collate_fn=collator,
        num_workers=0, generator=torch.Generator().manual_seed(args.seed),
        drop_last=False,
    )

    model.train()
    step = 0
    update_count = {row["id"]: 0 for row in train_rows}
    step_losses: List[float] = []
    epoch_losses: List[float] = []

    t = sync_time()
    for epoch in range(args.epochs):
        running, n_batches = 0.0, 0
        for batch in loader:
            optim.zero_grad(set_to_none=True)
            out = model(
                input_ids=batch["input_ids"].to(device),
                attention_mask=batch["attention_mask"].to(device),
                labels=batch["labels"].to(device),
            )
            loss = out.loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), args.max_grad_norm)
            optim.step()
            step += 1
            for sample_id in batch["ids"]:
                update_count[sample_id] += 1
            running += float(loss.item())
            n_batches += 1
            step_losses.append(float(loss.item()))
        epoch_losses.append(running / max(n_batches, 1))
        print(f"[train] epoch {epoch + 1}/{args.epochs} loss={epoch_losses[-1]:.4f} steps={step}")
    train_time = sync_time() - t

    # ---- after-loss (fine-tuned weights, same recipe) --------------------- #
    t = sync_time()
    after_train = teacher_forcing_nll(model, train_ds, collator, device, args.batch_size)
    after_valid = teacher_forcing_nll(model, valid_ds, collator, device, args.batch_size)
    after_time = sync_time() - t
    after_fingerprint = param_checksum(model)

    # ---- persist HF checkpoint ------------------------------------------- #
    os.makedirs(checkpoint_dir, exist_ok=True)
    model.config.pad_token_id = pad_token_id
    model.save_pretrained(checkpoint_dir, safe_serialization=True)
    tokenizer.save_pretrained(checkpoint_dir)

    # ---- training state (optimizer / step / RNG) -------------------------- #
    state = {
        "optimizer": optim.state_dict(),
        "step": step,
        "epoch": args.epochs,
        "rng": rng_snapshot(),
        "seed": args.seed,
        "learning_rate": args.lr,
        "batch_size": args.batch_size,
        "max_length": args.max_length,
        "ignore_index": IGNORE_INDEX,
        "pad_token_id": pad_token_id,
        "train_sentence_updates": update_count,
        "before_loss": before_train["mean_nll"],
        "after_loss": after_train["mean_nll"],
    }
    torch.save(state, os.path.join(args.output, "training_state.pt"))

    ckpt_files = sorted(
        f for f in os.listdir(checkpoint_dir) if os.path.isfile(os.path.join(checkpoint_dir, f))
    )
    min_updates = min(update_count.values()) if update_count else 0
    assert step >= 1, "no optimizer update happened"
    assert min_updates >= 1, "some training sentences never received a parameter update"

    run = {
        "task_id": "GPUv1-A03",
        "scale": "debug_only",
        "seed": args.seed,
        "device": str(device),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "dtype": str(next(model.parameters()).dtype),
        "model_source": MODEL_DIR_DEFAULT,
        "model_revision": MODEL_REVISION,
        "max_length": args.max_length,
        "label_padding": IGNORE_INDEX,
        "train_rows": len(train_rows),
        "validation_rows": len(valid_rows),
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "learning_rate": args.lr,
        "optimizer": "AdamW",
        "optimizer_steps": step,
        "min_optimizer_updates_per_train_sentence": min_updates,
        "max_optimizer_updates_per_train_sentence": max(update_count.values()),
        "step_losses": step_losses,
        "epoch_losses": epoch_losses,
        "before_loss": before_train["mean_nll"],
        "after_loss": after_train["mean_nll"],
        "loss_delta": before_train["mean_nll"] - after_train["mean_nll"],
        "before_perplexity": before_train["perplexity"],
        "after_perplexity": after_train["perplexity"],
        "before_loss_validation": before_valid["mean_nll"],
        "after_loss_validation": after_valid["mean_nll"],
        "target_tokens_train": after_train["target_tokens"],
        "num_parameters": after_fingerprint["numel"],
        "trainable_parameters": int(sum(p.numel() for p in model.parameters() if p.requires_grad)),
        "teachers_forcing_labels_ignore_index": IGNORE_INDEX,
        "data_sha256": {
            "train.jsonl": source_hashes["train.jsonl"],
            "validation.jsonl": source_hashes["validation.jsonl"],
        },
        "sync_train_seconds": train_time,
        "sync_total_seconds": sync_time() - t_start,
        "params": {
            "num_parameters": after_fingerprint["numel"],
            "trainable_parameters": int(sum(p.numel() for p in model.parameters() if p.requires_grad)),
            "before_checksum": before_fingerprint,
            "after_checksum": after_fingerprint,
            "changed": before_fingerprint != after_fingerprint,
        },
        "source_hashes": source_hashes,
        "checkpoint_dir": os.path.abspath(checkpoint_dir),
        "checkpoint_files": ckpt_files,
        "training_state_path": os.path.abspath(os.path.join(args.output, "training_state.pt")),
        "sync_timing_seconds": {
            "before_loss": before_time,
            "train": train_time,
            "after_loss": after_time,
            "total_train_command": sync_time() - t_start,
        },
        "environment": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "transformers": __import__("transformers").__version__,
            "numpy": np.__version__,
        },
    }
    write_json(os.path.join(args.output, "run.json"), run)

    print(
        f"[train] done steps={step} before_loss={run['before_loss']:.4f} "
        f"after_loss={run['after_loss']:.4f} train_time={train_time:.2f}s"
    )
    assert run["after_loss"] < run["before_loss"], "fine-tuning did not reduce teacher-forcing NLL"
    return 0



# --------------------------------------------------------------------------- #
# evaluate (debug-only quality report)
# --------------------------------------------------------------------------- #
def cmd_evaluate(args: argparse.Namespace) -> int:
    rows = read_jsonl(args.input)
    refs = {r["id"]: r["de"] for r in rows if "de" in r}
    hyps = read_jsonl(args.translations)
    pairs = [(h["translation"], refs[h["id"]]) for h in hyps if h["id"] in refs]
    report = {
        "task_id": "GPUv1-A03",
        "note": "debug self-report only; not an official WMT/BLEU/chrF benchmark run",
        "n_sentences": len(pairs),
        "coverage": f"{len(pairs)}/{len(rows)}",
        "bleu": corpus_bleu([h for h, _ in pairs], [r for _, r in pairs]),
        "chrf": corpus_chrf([h for h, _ in pairs], [r for _, r in pairs]),
        "metric_implementation": "self-contained (this file), no external metric library available",
    }
    write_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


# --------------------------------------------------------------------------- #
# translate
# --------------------------------------------------------------------------- #
def cmd_translate(args: argparse.Namespace) -> int:
    t_start = sync_time()
    set_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    tokenizer = MarianTokenizer.from_pretrained(args.checkpoint)
    model = MarianMTModel.from_pretrained(args.checkpoint).to(device)
    model.eval()

    rows = read_jsonl(args.input)
    if not rows:
        raise RuntimeError(f"no input rows in {args.input}")

    decoder_start = int(model.config.decoder_start_token_id)
    eos_id = int(model.config.eos_token_id)
    pad_id = int(model.config.pad_token_id)

    results: List[Dict[str, Any]] = []
    t = sync_time()
    for row in rows:
        assert "en" in row, f"row {row.get('id')} missing 'en'"
        enc = tokenizer(
            row["en"], return_tensors="pt", truncation=True, max_length=args.max_length,
            add_special_tokens=True,
        )
        enc = {k: v.to(device) for k, v in enc.items()}
        with torch.no_grad():
            generated = model.generate(
                **enc,
                max_new_tokens=args.max_new_tokens,
                num_beams=args.num_beams,
                do_sample=False,
                early_stopping=True,
                use_cache=True,
            )
        seq = generated[0].tolist()
        # strip decoder-start prefix and eos/pad tail -> clean target token ids
        if seq and seq[0] in (decoder_start, pad_id):
            seq = seq[1:]
        while seq and seq[-1] in (eos_id, pad_id):
            seq = seq[:-1]
        token_ids = [int(t) for t in seq]
        translation = tokenizer.decode(token_ids, skip_special_tokens=True).strip()
        if not translation:
            raise RuntimeError(
                f"empty translation for id={row.get('id')} (source={row['en']!r}); failing loudly"
            )
        results.append(
            {
                "id": row["id"],
                "en": row["en"],
                "translation": translation,
                "token_ids": token_ids,
            }
        )
    translate_time = sync_time() - t

    write_jsonl(args.output, results)
    assert len(results) == len(rows), "incomplete coverage of the input file"
    if getattr(args, "timing", None):
        write_json(
            args.timing,
            {
                "command": "translate",
                "checkpoint": os.path.abspath(args.checkpoint),
                "input": os.path.abspath(args.input),
                "output": os.path.abspath(args.output),
                "rows": len(results),
                "device": str(device),
                "num_beams": args.num_beams,
                "max_new_tokens": args.max_new_tokens,
                "sync_seconds": translate_time,
                "sync_total_seconds": sync_time() - t_start,
            },
        )
    print(
        f"[translate] wrote {len(results)}/{len(rows)} translations "
        f"in {translate_time:.2f}s -> {args.output}"
    )
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GPUv1-A03 EN->DE Marian fine-tune / translate")
    sub = parser.add_subparsers(dest="command", required=True)

    p_train = sub.add_parser("train", help="fine-tune the Marian model and dump artefacts")
    p_train.add_argument("--input", default="input", help="input directory with train/validation jsonl")
    p_train.add_argument("--output", default="output", help="output directory for artefacts")
    p_train.add_argument("--model-dir", default=MODEL_DIR_DEFAULT, help="base Marian checkpoint")
    p_train.add_argument("--checkpoint", default=None, help="checkpoint output dir (default <output>/checkpoint)")
    p_train.add_argument("--epochs", type=int, default=3)
    p_train.add_argument("--batch-size", type=int, default=8)
    p_train.add_argument("--lr", type=float, default=2e-5)
    p_train.add_argument("--max-grad-norm", type=float, default=1.0)
    p_train.add_argument("--max-length", type=int, default=MAX_LENGTH)
    p_train.add_argument("--seed", type=int, default=SEED)
    p_train.set_defaults(func=cmd_train)

    p_tr = sub.add_parser("translate", help="translate an en jsonl file with a saved checkpoint")
    p_tr.add_argument("--checkpoint", required=True)
    p_tr.add_argument("--input", required=True)
    p_tr.add_argument("--output", required=True)
    p_tr.add_argument("--max-length", type=int, default=MAX_LENGTH)
    p_tr.add_argument("--max-new-tokens", type=int, default=MAX_LENGTH)
    p_tr.add_argument("--num-beams", type=int, default=4)
    p_tr.add_argument("--seed", type=int, default=SEED)
    p_tr.add_argument("--timing", default=None, help="optional json path for synchronised timing")
    p_tr.set_defaults(func=cmd_translate)

    p_ev = sub.add_parser("evaluate", help="debug-only chrF/BLEU report for translations")
    p_ev.add_argument("--translations", required=True)
    p_ev.add_argument("--input", required=True)
    p_ev.add_argument("--output", required=True)
    p_ev.set_defaults(func=cmd_evaluate)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    set_seed(getattr(args, "seed", SEED))
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
