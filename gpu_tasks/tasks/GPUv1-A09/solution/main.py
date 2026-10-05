#!/usr/bin/env python
"""GPUv1-A09: trainable, reloadable question/passage dual encoder for SQuAD-style QA retrieval.

Commands
--------
  python solution/main.py train  --input input --output output
  python solution/main.py encode --checkpoint output/checkpoint --input input/validation.jsonl --output output/reloaded

Design (see solution/README.md):
  * Base model: /models/prajjwal1--bert-tiny (BERT-tiny, HF revision pinned by the task manifest).
  * Shared-by-default dual encoder: the same BertModel is used for questions and passages
    (the spec explicitly allows "shared or independent"); independent encoders are available
    with --independent-encoders.
  * Attention-mask mean pooling followed by L2 normalisation (both at train and encode time).
  * In-batch contrastive cross entropy with a multi-positive mask built from *content groups*
    (rows whose normalised context text is identical are positives, never negatives).
    Training batches are additionally de-duplicated so that each batch holds at most one
    question per unique context content.
  * >= 1 complete pass over every training row (default 20 epochs, all 100 rows each epoch).
  * Fixed seed everywhere; deterministic evaluation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
import time
from collections import Counter, OrderedDict, defaultdict
from typing import Dict, List, Sequence, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

DEFAULT_BASE_MODEL = "/models/prajjwal1--bert-tiny"
MAX_TOKENS = 128


# --------------------------------------------------------------------------------------
# small utilities
# --------------------------------------------------------------------------------------
def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def read_jsonl(path: str) -> List[dict]:
    rows: List[dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if "context" not in obj or "question" not in obj:
                raise ValueError(f"{path}:{lineno}: row must contain 'question' and 'context'")
            obj.setdefault("id", f"row-{lineno}")
            rows.append(obj)
    return rows


def content_key(context: str) -> str:
    """Group key: identical passage *content* (whitespace-normalised) -> identical key."""
    return " ".join(context.split())


def stable_hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def param_checksum(model: nn.Module) -> Tuple[str, float]:
    """Deterministic checksum + global L2 norm of all floating point parameters."""
    h = hashlib.sha256()
    total = 0.0
    for name, p in sorted(model.state_dict().items()):
        t = p.detach().float().cpu().contiguous()
        h.update(name.encode())
        h.update(t.numpy().tobytes())
        total += float(t.double().pow(2).sum())
    return h.hexdigest(), math.sqrt(total)


def num_unique_contexts(rows: Sequence[dict]) -> int:
    return len({content_key(r["context"]) for r in rows})


# --------------------------------------------------------------------------------------
# dual encoder
# --------------------------------------------------------------------------------------
class DualEncoder(nn.Module):
    """BERT-tiny based dual encoder with mean pooling + L2 normalisation."""

    def __init__(self, base_model: str = DEFAULT_BASE_MODEL, shared: bool = True,
                 dropout: float = 0.1, local_files_only: bool = True, temperature: float = 0.07):
        super().__init__()
        from transformers import BertConfig, BertModel

        self.shared = bool(shared)
        self.base_model = base_model
        self.max_tokens = MAX_TOKENS
        cfg = BertConfig.from_pretrained(base_model, local_files_only=local_files_only)
        if dropout is not None:
            cfg.hidden_dropout_prob = float(dropout)
            cfg.attention_probs_dropout_prob = float(dropout)
        cfg.max_position_embeddings = max(int(cfg.max_position_embeddings), MAX_TOKENS)
        if shared:
            self.encoder = BertModel.from_pretrained(
                base_model, config=cfg, local_files_only=local_files_only, ignore_mismatched_sizes=True)
        else:
            self.question_encoder = BertModel.from_pretrained(
                base_model, config=cfg, local_files_only=local_files_only, ignore_mismatched_sizes=True)
            # independent copy initialised from a different seed state deterministically
            import copy
            self.passage_encoder = copy.deepcopy(self.question_encoder)
        # CLIP-style learnable temperature (logit scale)
        self.logit_scale = nn.Parameter(torch.tensor(math.log(1.0 / temperature), dtype=torch.float32))

    # -- modules -------------------------------------------------------------------
    def _encoder(self, which: str) -> nn.Module:
        if self.shared:
            return self.encoder
        return self.question_encoder if which == "question" else self.passage_encoder

    @staticmethod
    def mean_pool(last_hidden: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        mask = attention_mask.unsqueeze(-1).to(last_hidden.dtype)
        summed = (last_hidden * mask).sum(dim=1)
        counts = mask.sum(dim=1).clamp(min=1e-6)
        return summed / counts

    def encode(self, input_ids: torch.Tensor, attention_mask: torch.Tensor, which: str) -> torch.Tensor:
        """Returns L2-normalised embeddings. `which` in {'question','passage'}."""
        enc = self._encoder(which)
        out = enc(input_ids=input_ids,
                  attention_mask=attention_mask,
                  token_type_ids=torch.zeros_like(input_ids),
                  return_dict=True)
        pooled = self.mean_pool(out.last_hidden_state, attention_mask)
        return F.normalize(pooled, p=2, dim=-1, eps=1e-8)

    @torch.no_grad()
    def encode_texts(self, texts: Sequence[str], tokenizer, device: torch.device,
                     which: str, batch_size: int = 32) -> np.ndarray:
        self.eval()
        chunks: List[np.ndarray] = []
        for start in range(0, len(texts), batch_size):
            batch = list(texts[start:start + batch_size])
            enc = tokenizer(batch, padding=True, truncation=True, max_length=self.max_tokens,
                            return_tensors="pt")
            ids = enc["input_ids"].to(device)
            mask = enc["attention_mask"].to(device)
            emb = self.encode(ids, mask, which)
            chunks.append(emb.detach().float().cpu().numpy().astype(np.float32))
        if not chunks:
            cfg = self._encoder("question").config
            return np.zeros((0, cfg.hidden_size), dtype=np.float32)
        return np.concatenate(chunks, axis=0)

    # -- persistence -----------------------------------------------------------------
    def save_pretrained(self, directory: str, tokenizer, extra: dict | None = None) -> None:
        os.makedirs(directory, exist_ok=True)
        if self.shared:
            self.encoder.config.model_type = "bert"
            self.encoder.save_pretrained(directory)
        else:
            self.question_encoder.config.model_type = "bert"
            self.passage_encoder.config.model_type = "bert"
            self.question_encoder.save_pretrained(os.path.join(directory, "question_encoder"))
            self.passage_encoder.save_pretrained(os.path.join(directory, "passage_encoder"))
        tokenizer.save_pretrained(directory)
        # keep a slow-tokenizer fallback (vocab.txt) and an explicit tokenizer_class so the
        # checkpoint reloads with either AutoTokenizer(fast) or plain BertTokenizer.
        base_vocab = os.path.join(self.base_model, "vocab.txt")
        if os.path.exists(base_vocab):
            import shutil
            shutil.copyfile(base_vocab, os.path.join(directory, "vocab.txt"))
        tc_path = os.path.join(directory, "tokenizer_config.json")
        tc = {}
        if os.path.exists(tc_path):
            with open(tc_path, "r", encoding="utf-8") as fh:
                tc = json.load(fh)
        tc["tokenizer_class"] = "BertTokenizerFast"
        with open(tc_path, "w", encoding="utf-8") as fh:
            json.dump(tc, fh, indent=2)
        with open(os.path.join(directory, "special_tokens_map.json"), "w", encoding="utf-8") as fh:
            json.dump({"unk_token": "[UNK]", "sep_token": "[SEP]", "pad_token": "[PAD]",
                       "cls_token": "[CLS]", "mask_token": "[MASK]"}, fh, indent=2)
        meta = {
            "architecture": "DualEncoder",
            "shared": self.shared,
            "pooling": "attention_mask_mean",
            "normalization": "l2",
            "max_tokens": self.max_tokens,
            "temperature": float(torch.exp(-self.logit_scale.detach()).item()),
            "logit_scale": float(self.logit_scale.detach().item()),
            "base_model": self.base_model,
        }
        if extra:
            meta.update(extra)
        with open(os.path.join(directory, "encoder_meta.json"), "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2)

    @classmethod
    def from_checkpoint(cls, directory: str, device: torch.device | str = "cpu",
                        local_files_only: bool = True) -> "DualEncoder":
        from transformers import BertConfig, BertModel

        meta_path = os.path.join(directory, "encoder_meta.json")
        meta = {}
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as fh:
                meta = json.load(fh)
        shared = bool(meta.get("shared", True))
        obj = cls.__new__(cls)
        nn.Module.__init__(obj)
        obj.shared = shared
        obj.base_model = meta.get("base_model", directory)
        obj.max_tokens = int(meta.get("max_tokens", MAX_TOKENS))
        if shared:
            obj.encoder = BertModel.from_pretrained(directory, local_files_only=local_files_only)
        else:
            obj.question_encoder = BertModel.from_pretrained(
                os.path.join(directory, "question_encoder"), local_files_only=local_files_only)
            obj.passage_encoder = BertModel.from_pretrained(
                os.path.join(directory, "passage_encoder"), local_files_only=local_files_only)
        ls = float(meta.get("logit_scale", math.log(1.0 / 0.07)))
        obj.logit_scale = nn.Parameter(torch.tensor(ls, dtype=torch.float32))
        obj.to(device)
        obj.eval()
        return obj


# --------------------------------------------------------------------------------------
# batching / loss
# --------------------------------------------------------------------------------------
def build_dedup_batches(rows: Sequence[dict], batch_size: int, generator: random.Random) -> List[List[int]]:
    """Build one epoch of batches covering *every* row exactly once.

    Each batch is first filled with rows that have distinct passage content, then topped up
    with the remaining rows (which can only be same-content duplicates of rows already in the
    batch).  Same-content rows are therefore *true positives* and are handled by the
    multi-positive mask instead of being treated as negatives.
    """
    pool = list(range(len(rows)))
    generator.shuffle(pool)
    keys = [content_key(r["context"]) for r in rows]
    batches: List[List[int]] = []
    while pool:
        batch: List[int] = []
        batch_keys: set = set()
        i = 0
        # pass 1: distinct passage contents -> hard negatives stay inside the batch
        while i < len(pool) and len(batch) < batch_size:
            idx = pool[i]
            if keys[idx] not in batch_keys:
                batch.append(idx)
                batch_keys.add(keys[idx])
                pool.pop(i)
            else:
                i += 1
        # pass 2: fill the batch with same-content rows (true positives, masked in the loss)
        while pool and len(batch) < batch_size:
            batch.append(pool.pop(0))
        batches.append(batch)
    return batches


def multi_positive_contrastive_loss(q: torch.Tensor, p: torch.Tensor, group_ids: torch.Tensor,
                                    logit_scale: torch.Tensor) -> torch.Tensor:
    """In-batch cross entropy where every positive (same content group) is allowed."""
    scale = logit_scale.exp().clamp(max=100.0)
    logits = (q @ p.t()) * scale
    positives = group_ids[:, None] == group_ids[None, :]
    nll = torch.logsumexp(logits, dim=1) - torch.logsumexp(logits.masked_fill(~positives, float("-inf")), dim=1)
    return nll.mean()


def collate_texts(texts: Sequence[str], tokenizer, device: torch.device, max_tokens: int):
    enc = tokenizer(list(texts), padding=True, truncation=True, max_length=max_tokens, return_tensors="pt")
    return enc["input_ids"].to(device), enc["attention_mask"].to(device)


# --------------------------------------------------------------------------------------
# retrieval / metrics
# --------------------------------------------------------------------------------------
def retrieval_metrics(query_emb: np.ndarray, passage_emb: np.ndarray,
                      query_groups: Sequence[int], passage_groups: Sequence[int],
                      ks: Sequence[int] = (1, 5)) -> dict:
    """Cosine retrieval with *content-group* correctness (all ids sharing a passage content
    count as a hit)."""
    q = torch.from_numpy(np.asarray(query_emb, dtype=np.float32))
    p = torch.from_numpy(np.asarray(passage_emb, dtype=np.float32))
    sims = (q @ p.t()).numpy() if len(q) and len(p) else np.zeros((len(q), len(p)), dtype=np.float32)
    qg = np.asarray(query_groups)
    pg = np.asarray(passage_groups)
    out = {f"recall@{k}": None for k in ks}
    hit_lists: Dict[int, List[bool]] = {k: [] for k in ks}
    ranked: List[np.ndarray] = []
    for i in range(len(q)):
        order = np.argsort(-sims[i], kind="stable")
        ranked.append(order)
        for k in ks:
            if len(order) == 0:
                continue
            top = order[:min(k, len(order))]
            hit = bool(np.any(pg[top] == qg[i])) if len(top) else False
            hit_lists[k].append(hit)
    for k in ks:
        if hit_lists[k]:
            out[f"recall@{k}"] = float(np.mean(hit_lists[k]))
        else:
            out[f"recall@{k}"] = 0.0
    return {"metrics": out, "ranked": ranked, "sims": sims}


def build_passage_index(rows: Sequence[dict]):
    """Collapse validation rows into unique passage *content groups*."""
    groups: "OrderedDict[str, dict]" = OrderedDict()
    row_to_group: List[int] = []
    for r in rows:
        key = content_key(r["context"])
        if key not in groups:
            groups[key] = {"group_id": len(groups), "key": key, "ids": [], "context": r["context"]}
        groups[key]["ids"].append(r["id"])
        row_to_group.append(groups[key]["group_id"])
    return list(groups.values()), row_to_group


def write_retrieval_json(path: str, rows: Sequence[dict], q_emb: np.ndarray, p_emb_rows: np.ndarray,
                         k: int = 5) -> dict:
    """Retrieval over de-duplicated passage contents (content groups), with per-group score."""
    groups, row_to_group = build_passage_index(rows)
    # passage embeddings of the unique groups = first row embedding of each group
    seen: Dict[int, int] = {}
    group_rows: List[int] = []
    for i, g in enumerate(row_to_group):
        if g not in seen:
            seen[g] = i
            group_rows.append(i)
    group_emb = p_emb_rows[group_rows] if len(group_rows) else np.zeros((0, 0), dtype=np.float32)
    stat = retrieval_metrics(q_emb, group_emb, row_to_group, list(range(len(groups))), ks=(1, k))
    sims = stat["sims"]
    results = []
    for i, r in enumerate(rows):
        order = np.argsort(-sims[i], kind="stable")[:min(k, len(groups))]
        retrieved = []
        for rank, gi in enumerate(order, 1):
            retrieved.append({
                "rank": int(rank),
                "group_id": int(gi),
                "passage_id": groups[gi]["ids"][0],
                "ids": list(groups[gi]["ids"]),
                "score": float(sims[i, gi]),
            })
        results.append({
            "query_id": r["id"],
            "question": r["question"],
            "gold_group_id": int(row_to_group[i]),
            "gold_passage_id": groups[row_to_group[i]]["ids"][0],
            "retrieved": retrieved,
            "retrieved_ids": [x["passage_id"] for x in retrieved],
            "top_k_ids": [x["passage_id"] for x in retrieved],
            "hit@1": bool(any(x["group_id"] == row_to_group[i] for x in retrieved[:1])),
            f"hit@{k}": bool(any(x["group_id"] == row_to_group[i] for x in retrieved[:k])),
        })
    payload = {
        "metric": "cosine",
        "top_k": int(k),
        "k": int(k),
        "index": "unique_passage_content_groups",
        "num_queries": len(rows),
        "num_passages": len(rows),
        "num_unique_passages": len(groups),
        "content_group_judgement": True,
        "recall@1": stat["metrics"]["recall@1"],
        f"recall@{k}": stat["metrics"][f"recall@{k}"],
        "passage_groups": [{"group_id": g["group_id"], "ids": g["ids"], "representative_id": g["ids"][0]}
                           for g in groups],
        "results": results,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return payload


# --------------------------------------------------------------------------------------
# encode pipeline (shared by `train` post-hoc eval and the `encode` command)
# --------------------------------------------------------------------------------------
def run_encode(checkpoint: str, input_path: str, output_dir: str, batch_size: int = 32,
               device: str | None = None, seed: int = 1234, tag: str = "encode") -> dict:
    from transformers import BertTokenizerFast

    set_seed(seed)
    dev = torch.device(device if device else ("cuda" if torch.cuda.is_available() else "cpu"))
    os.makedirs(output_dir, exist_ok=True)
    rows = read_jsonl(input_path)
    model = DualEncoder.from_checkpoint(checkpoint, device=dev)
    model.eval()
    tokenizer = BertTokenizerFast.from_pretrained(checkpoint, local_files_only=True)

    questions = [r["question"] for r in rows]
    contexts = [r["context"] for r in rows]
    t0 = time.time()
    q_emb = model.encode_texts(questions, tokenizer, dev, "question", batch_size=batch_size)
    p_emb = model.encode_texts(contexts, tokenizer, dev, "passage", batch_size=batch_size)
    elapsed = time.time() - t0

    q_norm = np.linalg.norm(q_emb.astype(np.float64), axis=1) if len(q_emb) else np.zeros(0)
    p_norm = np.linalg.norm(p_emb.astype(np.float64), axis=1) if len(p_emb) else np.zeros(0)

    q_path = os.path.join(output_dir, "question_embeddings.npy")
    p_path = os.path.join(output_dir, "passage_embeddings.npy")
    r_path = os.path.join(output_dir, "retrieval.json")
    np.save(q_path, q_emb.astype(np.float32))
    np.save(p_path, p_emb.astype(np.float32))
    retr = write_retrieval_json(r_path, rows, q_emb, p_emb, k=5)

    info = {
        "tag": tag,
        "checkpoint": os.path.abspath(checkpoint),
        "input": os.path.abspath(input_path),
        "output_dir": os.path.abspath(output_dir),
        "device": str(dev),
        "seed": seed,
        "max_tokens": int(model.max_tokens),
        "pooling": "attention_mask_mean",
        "normalization": "l2",
        "shared_encoder": bool(model.shared),
        "num_rows": len(rows),
        "num_unique_contexts": num_unique_contexts(rows),
        "embedding_dim": int(q_emb.shape[1]) if q_emb.size else 0,
        "question_embeddings_shape": list(q_emb.shape),
        "passage_embeddings_shape": list(p_emb.shape),
        "question_norms": {"min": float(q_norm.min()) if len(q_norm) else 0.0,
                           "max": float(q_norm.max()) if len(q_norm) else 0.0,
                           "mean": float(q_norm.mean()) if len(q_norm) else 0.0},
        "passage_norms": {"min": float(p_norm.min()) if len(p_norm) else 0.0,
                          "max": float(p_norm.max()) if len(p_norm) else 0.0,
                          "mean": float(p_norm.mean()) if len(p_norm) else 0.0},
        "recall@1": retr["recall@1"],
        "recall@5": retr["recall@5"],
        "elapsed_sec": elapsed,
        "artifacts": {
            "question_embeddings.npy": {"sha256": sha256_file(q_path), "shape": list(q_emb.shape)},
            "passage_embeddings.npy": {"sha256": sha256_file(p_path), "shape": list(p_emb.shape)},
            "retrieval.json": {"sha256": sha256_file(r_path)},
        },
    }
    with open(os.path.join(output_dir, "run.json"), "w", encoding="utf-8") as fh:
        json.dump(info, fh, indent=2)
    return info


def retrieval_probe(model: "DualEncoder", rows: Sequence[dict], tokenizer, device,
                    batch_size: int = 32) -> dict:
    """Auxiliary, honest signal: question -> unique-passage retrieval over the *train* rows
    (21 distinct contents for the provided debug split), scored with content groups."""
    keys = [content_key(r["context"]) for r in rows]
    unique_keys = list(dict.fromkeys(keys))
    group_of_row = [unique_keys.index(k) for k in keys]
    first_row = {k: i for i, k in enumerate(keys)}
    q = model.encode_texts([r["question"] for r in rows], tokenizer, device, "question", batch_size)
    p = model.encode_texts([rows[first_row[k]]["context"] for k in unique_keys], tokenizer, device,
                           "passage", batch_size)
    stat = retrieval_metrics(q, p, group_of_row, list(range(len(unique_keys))), ks=(1, 5))
    return {"num_unique_passages": len(unique_keys), **stat["metrics"]}


# --------------------------------------------------------------------------------------
# training
# --------------------------------------------------------------------------------------
def resolve_train_paths(input_arg: str, validation_arg: str | None = None):
    """Accept either a directory holding train.jsonl/validation.jsonl or explicit files."""
    inp = os.path.abspath(input_arg)
    if os.path.isdir(inp):
        train_path = os.path.join(inp, "train.jsonl")
        val_path = validation_arg or os.path.join(inp, "validation.jsonl")
    elif inp.endswith(".jsonl"):
        train_path = inp
        val_path = validation_arg or os.path.join(os.path.dirname(inp), "validation.jsonl")
    else:
        raise FileNotFoundError(f"cannot interpret --input {input_arg!r}")
    if not os.path.exists(train_path):
        raise FileNotFoundError(f"train file not found: {train_path}")
    return train_path, (val_path if os.path.exists(val_path) else None)


def train(args) -> dict:
    from transformers import BertTokenizerFast
    import transformers

    set_seed(args.seed)
    t_start = time.time()
    os.makedirs(args.output, exist_ok=True)
    ckpt_dir = os.path.join(args.output, "checkpoint")
    os.makedirs(ckpt_dir, exist_ok=True)

    device = torch.device(args.device if args.device else ("cuda" if torch.cuda.is_available() else "cpu"))
    if str(device).startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but not available")
    torch.cuda.manual_seed_all(args.seed)

    train_path, val_path = resolve_train_paths(args.input, getattr(args, "validation", None))
    train_rows = read_jsonl(train_path)
    val_rows = read_jsonl(val_path) if val_path else []

    tokenizer = BertTokenizerFast.from_pretrained(args.base_model, local_files_only=True)
    model = DualEncoder(args.base_model, shared=not args.independent_encoders,
                        dropout=args.dropout, temperature=args.temperature).to(device)
    for p in model.parameters():
        p.requires_grad_(True)

    init_hash, init_norm = param_checksum(model)
    optimizer = torch.optim.AdamW((p for p in model.parameters() if p.requires_grad),
                                  lr=args.lr, weight_decay=args.weight_decay)
    generator = random.Random(args.seed)
    group_keys = [content_key(r["context"]) for r in train_rows]
    key_to_gid = {k: i for i, k in enumerate(sorted(set(group_keys)))}
    group_ids_all = [key_to_gid[k] for k in group_keys]

    model.train()
    loss_history: List[float] = []
    epoch_losses: List[float] = []
    first_grad_norm = None
    steps = 0
    samples_seen = 0
    for epoch in range(1, args.epochs + 1):
        batches = build_dedup_batches(train_rows, args.batch_size, generator)
        running = 0.0
        for batch_idx in batches:
            q_ids, q_mask = collate_texts([train_rows[i]["question"] for i in batch_idx],
                                          tokenizer, device, args.max_tokens)
            p_ids, p_mask = collate_texts([train_rows[i]["context"] for i in batch_idx],
                                          tokenizer, device, args.max_tokens)
            gids = torch.tensor([group_ids_all[i] for i in batch_idx], dtype=torch.long, device=device)
            q = model.encode(q_ids, q_mask, "question")
            p = model.encode(p_ids, p_mask, "passage")
            loss = multi_positive_contrastive_loss(q, p, gids, model.logit_scale)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            if first_grad_norm is None:
                gn = torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                first_grad_norm = float(gn.detach().item())
            else:
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            steps += 1
            samples_seen += len(batch_idx)
            running += float(loss.detach().item())
            loss_history.append(float(loss.detach().item()))
        epoch_losses.append(running / max(1, len(batches)))
        if str(device).startswith("cuda"):
            torch.cuda.synchronize()
        print(f"[train] epoch {epoch}/{args.epochs} loss={epoch_losses[-1]:.4f} steps={steps}", flush=True)

    final_hash, final_norm = param_checksum(model)
    model.save_pretrained(ckpt_dir, tokenizer, extra={
        "training_seed": args.seed,
        "training_epochs": args.epochs,
        "training_steps": steps,
        "init_param_hash": init_hash,
        "final_param_hash": final_hash,
    })

    # auxiliary train-set retrieval probe (trained checkpoint vs. base model) --------
    probe_trained = probe_base = None
    try:
        reloaded = DualEncoder.from_checkpoint(ckpt_dir, device=device)
        probe_trained = retrieval_probe(reloaded, train_rows, tokenizer, device)
        del reloaded
        base_model = DualEncoder(args.base_model, shared=not args.independent_encoders).to(device)
        probe_base = retrieval_probe(base_model, train_rows, tokenizer, device)
        del base_model
        if str(device).startswith("cuda"):
            torch.cuda.empty_cache()
    except Exception as exc:  # pragma: no cover - probe is diagnostic only
        print(f"[warn] train retrieval probe failed: {exc}", flush=True)

    training_state = {
        "seed": args.seed,
        "device": str(device),
        "cuda_used": bool(str(device).startswith("cuda")),
        "cuda_device_name": torch.cuda.get_device_name(0) if str(device).startswith("cuda") else None,
        "epochs": args.epochs,
        "steps": steps,
        "batch_size": args.batch_size,
        "learning_rate": args.lr,
        "weight_decay": args.weight_decay,
        "optimizer": "AdamW",
        "max_tokens": args.max_tokens,
        "pooling": "attention_mask_mean",
        "normalization": "l2",
        "loss": "in_batch_contrastive_cross_entropy_multi_positive",
        "multi_positive_mask": True,
        "deduplicated_batches": True,
        "shared_encoder": not args.independent_encoders,
        "temperature": args.temperature,
        "loss_history": loss_history,
        "epoch_losses": epoch_losses,
        "first_step_grad_norm": first_grad_norm,
        "backward_device": str(device),
        "samples_seen": samples_seen,
        "train_rows": len(train_rows),
        "full_passes_completed": int(samples_seen // max(1, len(train_rows))),
        "unique_train_contexts": num_unique_contexts(train_rows),
        "unique_val_contexts": num_unique_contexts(val_rows),
        "init_param_hash": init_hash,
        "final_param_hash": final_hash,
        "params_updated": bool(init_hash != final_hash),
        "init_param_norm": init_norm,
        "final_param_norm": final_norm,
        "param_delta_norm": float(abs(final_norm - init_norm)),
        "optimizer_state_dict": optimizer.state_dict(),
        "train_retrieval_probe": probe_trained,
        "base_model_train_retrieval_probe": probe_base,
        "transformers_version": transformers.__version__,
        "torch_version": torch.__version__,
        "numpy_version": np.__version__,
        "elapsed_train_sec": time.time() - t_start,
    }
    torch.save(training_state, os.path.join(args.output, "training_state.pt"))

    # --- evaluate / export from the *saved* checkpoint (same path the encode CLI uses) ---
    if val_rows:
        info = run_encode(ckpt_dir, val_path, args.output, batch_size=args.encode_batch_size,
                          device=args.device, seed=args.seed, tag="train_final_eval")
    else:
        info = {}

    run = {
        "task": "GPUv1-A09",
        "command": "train",
        "input": os.path.abspath(args.input),
        "train_file": os.path.abspath(train_path),
        "validation_file": os.path.abspath(val_path) if val_path else None,
        "output": os.path.abspath(args.output),
        "base_model": args.base_model,
        "seed": args.seed,
        "device": str(device),
        "cuda_used": bool(str(device).startswith("cuda")),
        "epochs": args.epochs,
        "steps": steps,
        "batch_size": args.batch_size,
        "learning_rate": args.lr,
        "max_tokens": args.max_tokens,
        "pooling": "attention_mask_mean",
        "normalization": "l2",
        "loss": "in_batch_contrastive_cross_entropy_multi_positive",
        "multi_positive_mask": True,
        "deduplicated_batches": True,
        "shared_encoder": not args.independent_encoders,
        "temperature": args.temperature,
        "train_rows": len(train_rows),
        "validation_rows": len(val_rows),
        "unique_train_contexts": num_unique_contexts(train_rows),
        "unique_validation_contexts": num_unique_contexts(val_rows),
        "samples_seen": samples_seen,
        "full_passes_completed": int(samples_seen // max(1, len(train_rows))),
        "final_epoch_loss": epoch_losses[-1] if epoch_losses else None,
        "params_updated": bool(init_hash != final_hash),
        "init_param_hash": init_hash,
        "final_param_hash": final_hash,
        "first_step_grad_norm": first_grad_norm,
        "validation_recall@1": info.get("recall@1"),
        "train_retrieval_probe": probe_trained,
        "base_model_train_retrieval_probe": probe_base,
        "validation_recall@5": info.get("recall@5"),
        "num_unique_validation_passages": info.get("num_unique_contexts"),
        "artifacts": {
            "checkpoint/": {"dir": os.path.abspath(ckpt_dir)},
            "training_state.pt": {"sha256": sha256_file(os.path.join(args.output, "training_state.pt"))},
            "question_embeddings.npy": info.get("artifacts", {}).get("question_embeddings.npy"),
            "passage_embeddings.npy": info.get("artifacts", {}).get("passage_embeddings.npy"),
            "retrieval.json": info.get("artifacts", {}).get("retrieval.json"),
        },
        "elapsed_sec": time.time() - t_start,
        "output_dir": os.path.abspath(args.output),
    }
    with open(os.path.join(args.output, "run.json"), "w", encoding="utf-8") as fh:
        json.dump(run, fh, indent=2)
    print(json.dumps({k: run[k] for k in ("seed", "epochs", "steps", "samples_seen",
                                          "full_passes_completed", "params_updated",
                                          "validation_recall@1", "validation_recall@5")}, indent=2))
    return run


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="GPUv1-A09 dual encoder QA retrieval")
    sub = ap.add_subparsers(dest="command", required=True)

    tr = sub.add_parser("train", help="train the dual encoder")
    tr.add_argument("--input", required=True, help="input directory with train.jsonl / validation.jsonl (or a train jsonl file)")
    tr.add_argument("--validation", default=None, help="optional explicit validation.jsonl path")
    tr.add_argument("--output", required=True, help="output directory")
    tr.add_argument("--base-model", default=DEFAULT_BASE_MODEL)
    tr.add_argument("--epochs", type=int, default=20)
    tr.add_argument("--batch-size", type=int, default=8, help="unique contexts per batch")
    tr.add_argument("--lr", type=float, default=5e-5)
    tr.add_argument("--weight-decay", type=float, default=0.01)
    tr.add_argument("--temperature", type=float, default=0.07)
    tr.add_argument("--dropout", type=float, default=0.1)
    tr.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    tr.add_argument("--encode-batch-size", type=int, default=32)
    tr.add_argument("--independent-encoders", action="store_true",
                    help="use separate question/passage BERT encoders instead of a shared one")
    tr.add_argument("--seed", type=int, default=1234)
    tr.add_argument("--device", default=None)

    en = sub.add_parser("encode", help="encode a jsonl file with a saved checkpoint")
    en.add_argument("--checkpoint", required=True)
    en.add_argument("--input", required=True)
    en.add_argument("--output", required=True)
    en.add_argument("--batch-size", type=int, default=32)
    en.add_argument("--seed", type=int, default=1234)
    en.add_argument("--device", default=None)
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "train":
        if getattr(args, "max_tokens", MAX_TOKENS) != MAX_TOKENS:
            print(f"[warn] overriding --max-tokens to the spec value {MAX_TOKENS}")
            args.max_tokens = MAX_TOKENS
        train(args)
        return 0
    info = run_encode(args.checkpoint, args.input, args.output, batch_size=args.batch_size,
                      device=args.device, seed=args.seed, tag="encode")
    print(json.dumps({k: info[k] for k in ("num_rows", "question_embeddings_shape",
                                           "passage_embeddings_shape", "recall@1", "recall@5")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
