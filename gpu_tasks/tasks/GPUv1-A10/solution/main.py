#!/usr/bin/env python
"""WikiText-2 masked-language-model training / encoding for prajjwal1/bert-tiny.

Entry points
------------
    python solution/main.py train --input input --output output
    python solution/main.py embed --checkpoint output/checkpoint \\
        --input input/validation.jsonl --output output/embeddings.npy

Everything is deterministic given ``--seed``: dynamic MLM masks are drawn from a
per-epoch seeded NumPy generator, tokenizer order is fixed and evaluation runs
with dropout disabled.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset

MODEL_DIR = "/models/prajjwal1--bert-tiny"
DEFAULT_SEED = 1234
DEFAULT_EPOCHS = 30
DEFAULT_LR = 1e-5
MASK_RATE = 0.15
MAX_TOKENS = 128


# --------------------------------------------------------------------------- #
# data
# --------------------------------------------------------------------------- #
def read_jsonl(path: str) -> list[dict]:
    rows: list[dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def resolve_input(spec: str, name: str) -> str:
    """``spec`` may be a jsonl file or a directory containing ``name``."""
    if os.path.isdir(spec):
        return os.path.join(spec, name)
    return spec


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


# --------------------------------------------------------------------------- #
# MLM masking
# --------------------------------------------------------------------------- #
def mask_sequence(
    input_ids: list[int],
    special_tokens_mask: list[int],
    rng: np.random.Generator,
    mask_token_id: int,
    vocab_size: int,
    mask_rate: float = MASK_RATE,
) -> tuple[list[int], list[int]]:
    """Apply the standard 80/10/10 BERT masking scheme.

    Only real word tokens are candidates: padding / special tokens are skipped.
    Unselected tokens get label ``-100`` (ignored by the cross-entropy loss).
    """
    ids = list(input_ids)
    labels = [-100] * len(ids)

    candidates = [i for i, s in enumerate(special_tokens_mask) if s == 0]
    n_tokens = len(candidates)
    if n_tokens == 0:
        return ids, labels

    n_mask = int(round(mask_rate * n_tokens))
    n_mask = max(1, min(n_mask, n_tokens))  # guarantee at least one prediction
    chosen = rng.choice(np.asarray(candidates), size=n_mask, replace=False)
    chosen = np.sort(chosen)

    for idx in chosen:
        idx = int(idx)
        original = ids[idx]
        labels[idx] = original
        draw = rng.random()
        if draw < 0.8:
            ids[idx] = mask_token_id
        elif draw < 0.9:
            ids[idx] = int(rng.integers(0, vocab_size))
        # else: keep the original token (10%)

    return ids, labels


class TokenizedDataset(Dataset):
    def __init__(self, encodings: list[dict]):
        self.encodings = encodings

    def __len__(self) -> int:
        return len(self.encodings)

    def __getitem__(self, idx: int) -> dict:
        return self.encodings[idx]


def collate_batch(
    batch: list[dict],
    rng: np.random.Generator,
    mask_token_id: int,
    vocab_size: int,
    pad_token_id: int,
    mask: bool = True,
):
    """Pad a batch and (optionally) apply MLM masking.

    Returns ``(input_ids, attention_mask, labels)`` tensors.  Padding never
    contributes to the loss: padded labels stay at ``-100`` and the attention
    mask is zero there.
    """
    max_len = max(len(ex["input_ids"]) for ex in batch)
    ids_batch, attn_batch, label_batch = [], [], []
    for ex in batch:
        ids = ex["input_ids"]
        special = ex["special_tokens_mask"]
        if mask:
            ids, labels = mask_sequence(
                ids, special, rng, mask_token_id, vocab_size
            )
        else:
            labels = list(ids)
        pad = max_len - len(ids)
        ids_batch.append(ids + [pad_token_id] * pad)
        attn_batch.append([1] * len(ids) + [0] * pad)
        label_batch.append(labels + [-100] * pad)

    return (
        torch.tensor(ids_batch, dtype=torch.long),
        torch.tensor(attn_batch, dtype=torch.long),
        torch.tensor(label_batch, dtype=torch.long),
    )


# --------------------------------------------------------------------------- #
# train
# --------------------------------------------------------------------------- #
def run_train(args: argparse.Namespace) -> None:
    from transformers import BertForMaskedLM, BertTokenizerFast

    seed = args.seed
    set_seed(seed)
    os.makedirs(args.output, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    train_path = resolve_input(args.input, "train.jsonl")
    valid_path = resolve_input(args.input, "validation.jsonl")
    train_rows = read_jsonl(train_path)
    valid_rows = read_jsonl(valid_path) if os.path.exists(valid_path) else []

    tokenizer = BertTokenizerFast.from_pretrained(MODEL_DIR)
    model = BertForMaskedLM.from_pretrained(MODEL_DIR)
    model.to(device)
    model.train()

    def encode(rows: list[dict]) -> list[dict]:
        out = []
        for row in rows:
            enc = tokenizer(
                row["text"],
                truncation=True,
                max_length=args.max_tokens,
                return_special_tokens_mask=True,
            )
            out.append(
                {
                    "id": row.get("id"),
                    "input_ids": enc["input_ids"],
                    "special_tokens_mask": enc["special_tokens_mask"],
                }
            )
        return out

    train_enc = encode(train_rows)
    train_ds = TokenizedDataset(train_enc)

    mask_token_id = tokenizer.mask_token_id
    pad_token_id = tokenizer.pad_token_id
    vocab_size = tokenizer.vocab_size

    optimizer = torch.optim.AdamW(
        model.parameters(), lr=args.lr, weight_decay=0.01
    )

    global_step = 0
    epoch_losses: list[float] = []
    t0 = time.time()

    for epoch in range(args.epochs):
        # deterministic shuffling + masking per epoch
        perm_rng = torch.Generator()
        perm_rng.manual_seed(seed + epoch)
        order = torch.randperm(len(train_ds), generator=perm_rng).tolist()
        ordered = [train_ds[i] for i in order]

        mask_rng = np.random.default_rng([seed, epoch])

        def make_loader():
            return DataLoader(
                TokenizedDataset(ordered),
                batch_size=args.batch_size,
                shuffle=False,
                collate_fn=lambda b: collate_batch(
                    b, mask_rng, mask_token_id, vocab_size, pad_token_id, True
                ),
            )

        model.train()
        running, n_batches = 0.0, 0
        for input_ids, attn, labels in make_loader():
            input_ids = input_ids.to(device)
            attn = attn.to(device)
            labels = labels.to(device)

            out = model(input_ids=input_ids, attention_mask=attn, labels=labels)
            loss = out.loss
            if not torch.isfinite(loss):
                raise RuntimeError(f"non-finite loss at step {global_step}")

            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

            running += float(loss.detach().item())
            n_batches += 1
            global_step += 1

        epoch_loss = running / max(1, n_batches)
        epoch_losses.append(epoch_loss)
        print(
            f"[train] epoch {epoch} loss={epoch_loss:.4f} "
            f"steps={n_batches} global_step={global_step}",
            flush=True,
        )

    train_seconds = time.time() - t0

    # ---------------- validation (fixed seed mask) ---------------- #
    val_loss, val_masked = evaluate_mlm(
        model, tokenizer, valid_rows, device, seed, args.max_tokens,
        args.batch_size,
    )
    print(
        f"[valid] loss={val_loss:.4f} masked_tokens={val_masked}", flush=True
    )

    # ---------------- save HF checkpoint ---------------- #
    ckpt_dir = os.path.join(args.output, "checkpoint")
    os.makedirs(ckpt_dir, exist_ok=True)
    model.to("cpu")
    model.save_pretrained(ckpt_dir)
    tokenizer.save_pretrained(ckpt_dir)
    model.to(device)

    # ---------------- training state ---------------- #
    np_state = np.random.get_state()
    npy_rng_state = {
        "name": str(np_state[0]),
        "keys": [int(k) for k in np_state[1]],
        "pos": int(np_state[2]),
        "has_gauss": int(np_state[3]),
        "cached_gaussian": float(np_state[4]),
    }
    state = {
        "optimizer": optimizer.state_dict(),
        "global_step": global_step,
        "epoch": args.epochs,
        "seed": seed,
        "mask_rate": args.mask_rate,
        "max_tokens": args.max_tokens,
        "rng": {
            "python": random.getstate(),
            # numpy state stored as plain python types so the file reloads
            # with torch.load(..., weights_only=True) as well
            "numpy": npy_rng_state,
            "torch": torch.get_rng_state(),
            "cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available()
            else None,
        },
    }
    torch.save(state, os.path.join(args.output, "training_state.pt"))

    # ---------------- validation_mlm.json ---------------- #
    with open(os.path.join(args.output, "validation_mlm.json"), "w") as fh:
        json.dump(
            {
                "seed": seed,
                "max_tokens": args.max_tokens,
                "mask_rate": args.mask_rate,
                "num_examples": len(valid_rows),
                "masked_tokens": val_masked,
                "loss": val_loss,
            },
            fh,
            indent=2,
        )

    # ---------------- run.json ---------------- #
    import transformers

    run_meta = {
        "task_id": "GPUv1-A10",
        "mode": "train",
        "model_repo": "prajjwal1/bert-tiny",
        "model_dir": MODEL_DIR,
        "dataset": "Salesforce/wikitext/wikitext-2-raw-v1",
        "seed": seed,
        "max_tokens": args.max_tokens,
        "mask_rate": args.mask_rate,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "lr": args.lr,
        "global_step": global_step,
        "num_train_examples": len(train_rows),
        "num_valid_examples": len(valid_rows),
        "epoch_losses": epoch_losses,
        "final_epoch_loss": epoch_losses[-1] if epoch_losses else None,
        "validation_loss": val_loss,
        "validation_masked_tokens": val_masked,
        "train_seconds": train_seconds,
        "device": str(device),
        "cuda_available": torch.cuda.is_available(),
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "numpy": np.__version__,
        "outputs": {
            "checkpoint": "checkpoint/",
            "training_state": "training_state.pt",
            "validation_mlm": "validation_mlm.json",
        },
    }
    with open(os.path.join(args.output, "run.json"), "w") as fh:
        json.dump(run_meta, fh, indent=2)

    print("[train] done ->", args.output, flush=True)


@torch.no_grad()
def evaluate_mlm(model, tokenizer, rows, device, seed, max_tokens, batch_size):
    """Token-weighted MLM loss on a fixed (seeded) mask."""
    if not rows:
        return 0.0, 0
    model.eval()
    rng = np.random.default_rng([seed, 10_000])  # fixed validation-mask seed
    encs = []
    for row in rows:
        enc = tokenizer(
            row["text"],
            truncation=True,
            max_length=max_tokens,
            return_special_tokens_mask=True,
        )
        encs.append(
            {
                "input_ids": enc["input_ids"],
                "special_tokens_mask": enc["special_tokens_mask"],
            }
        )

    ds = TokenizedDataset(encs)
    loader = DataLoader(
        ds,
        batch_size=batch_size,
        shuffle=False,
        collate_fn=lambda b: collate_batch(
            b,
            rng,
            tokenizer.mask_token_id,
            tokenizer.vocab_size,
            tokenizer.pad_token_id,
            True,
        ),
    )

    total_loss, total_masked = 0.0, 0
    for input_ids, attn, labels in loader:
        input_ids, attn, labels = (
            input_ids.to(device),
            attn.to(device),
            labels.to(device),
        )
        out = model(input_ids=input_ids, attention_mask=attn, labels=labels)
        n_masked = int((labels != -100).sum().item())
        if n_masked:
            total_loss += float(out.loss.detach().item()) * n_masked
            total_masked += n_masked
    loss = total_loss / total_masked if total_masked else 0.0
    return loss, total_masked


# --------------------------------------------------------------------------- #
# embed
# --------------------------------------------------------------------------- #
@torch.no_grad()
def run_embed(args: argparse.Namespace) -> None:
    from transformers import AutoModelForMaskedLM, BertTokenizerFast

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    set_seed(args.seed)

    model = AutoModelForMaskedLM.from_pretrained(args.checkpoint)
    try:
        tokenizer = BertTokenizerFast.from_pretrained(args.checkpoint)
    except Exception:
        tokenizer = BertTokenizerFast.from_pretrained(MODEL_DIR)
    model.to(device)
    model.eval()

    encoder = getattr(model, "bert", None)
    if encoder is None:
        encoder = model.get_base_model() if hasattr(model, "get_base_model") \
            else model

    rows = read_jsonl(args.input)
    embeddings = np.zeros((len(rows), model.config.hidden_size), dtype=np.float32)

    batch_size = args.batch_size
    for start in range(0, len(rows), batch_size):
        chunk = rows[start:start + batch_size]
        texts = [r["text"] for r in chunk]
        enc = tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=args.max_tokens,
            return_tensors="pt",
        )
        input_ids = enc["input_ids"].to(device)
        attn = enc["attention_mask"].to(device)
        out = encoder(input_ids=input_ids, attention_mask=attn)
        hidden = out.last_hidden_state.float()
        mask = attn.unsqueeze(-1).float()
        summed = (hidden * mask).sum(dim=1)
        counts = mask.sum(dim=1).clamp(min=1.0)
        pooled = summed / counts  # padding excluded from the average
        pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
        embeddings[start:start + len(chunk)] = pooled.cpu().numpy()

    np.save(args.output, embeddings)
    print(
        f"[embed] wrote {args.output} shape={embeddings.shape} "
        f"norm_range=({np.linalg.norm(embeddings, axis=1).min():.4f},"
        f"{np.linalg.norm(embeddings, axis=1).max():.4f})",
        flush=True,
    )


# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="BERT-tiny MLM on WikiText-2")
    sub = p.add_subparsers(dest="command", required=True)

    tr = sub.add_parser("train", help="train the MLM")
    tr.add_argument("--input", required=True,
                    help="input dir (train.jsonl/validation.jsonl) or jsonl file")
    tr.add_argument("--output", required=True, help="output directory")
    tr.add_argument("--seed", type=int, default=DEFAULT_SEED)
    tr.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    tr.add_argument("--batch-size", type=int, default=8)
    tr.add_argument("--lr", type=float, default=DEFAULT_LR)
    tr.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    tr.add_argument("--mask-rate", type=float, default=MASK_RATE)
    tr.set_defaults(func=run_train)

    em = sub.add_parser("embed", help="encode jsonl with a trained checkpoint")
    em.add_argument("--checkpoint", required=True)
    em.add_argument("--input", required=True)
    em.add_argument("--output", required=True)
    em.add_argument("--seed", type=int, default=DEFAULT_SEED)
    em.add_argument("--batch-size", type=int, default=16)
    em.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    em.set_defaults(func=run_embed)

    return p


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
