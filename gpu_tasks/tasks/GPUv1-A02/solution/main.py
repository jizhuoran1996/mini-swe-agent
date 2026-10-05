#!/usr/bin/env python3
"""GPUv1-A02 (debug variant): real CUDA DPO alignment of SmolLM2-135M-Instruct.

Commands:
  doctor   --input DIR                    : inspect inputs/deps, no model load
  train    --input DIR --output DIR       : real DPO training + checkpoint
  evaluate --checkpoint DIR --input FILE --output FILE

Row schema handling (UltraFeedback binarized):
  row["prompt"] is the conversation prefix (string or message list).
  row["chosen"]/row["rejected"] may be a plain assistant string OR a full
  conversation array whose earlier entries duplicate the prompt.  Only the
  FINAL assistant message is used as the response; the shared prompt is taken
  from row["prompt"] (or derived as the common prefix of chosen/rejected when
  the field is absent) and included exactly once.  This prevents double-
  counting user prompt tokens inside the assistant mask.

Masking is string-based (TRL-style): the prompt is rendered with the model's
chat template (with the generation prefix), the full conversation is rendered
without it, and the response substring is the exact prefix-suffix difference.
The response terminator emitted by the template is retained.
"""
import argparse
import hashlib
import json
import math
import os
import random
import sys
import time

import torch
import torch.nn.functional as F

SEED = 0
BETA = 0.1
MAX_TOKENS = 256
MAX_PROMPT_KEEP_ON_RESP_OVERFLOW = 64
DEFAULT_MODEL = "/models/HuggingFaceTB--SmolLM2-135M-Instruct"


def now():
    return time.time()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_params(model):
    h = hashlib.sha256()
    for name, p in model.named_parameters():
        h.update(name.encode())
        h.update(p.detach().to("cpu", torch.float32).numpy().tobytes())
    return h.hexdigest()


def load_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                rows.append(json.loads(ln))
    return rows


def find_model_path(inp_dir):
    cands = []
    mf = os.path.join(inp_dir, "manifest.json")
    if os.path.exists(mf):
        try:
            m = json.load(open(mf, encoding="utf-8"))
            p = m.get("model_container_path")
            if p:
                cands.append(p)
        except Exception:
            pass
    cands.append(DEFAULT_MODEL)
    for c in cands:
        if c and os.path.isdir(c):
            return c
    return None


def read_revision(inp_dir):
    mf = os.path.join(inp_dir, "manifest.json")
    if os.path.exists(mf):
        try:
            return json.load(open(mf, encoding="utf-8")).get("model_revision")
        except Exception:
            return None
    return None


# --------------------------------------------------------------------------- #
# data normalization
# --------------------------------------------------------------------------- #
def _iter_msgs(x, default_role):
    if isinstance(x, str):
        yield {"role": default_role, "content": x}
        return
    if isinstance(x, dict):
        yield {"role": x.get("role", default_role), "content": x.get("content", "")}
        return
    for m in x:
        if isinstance(m, dict):
            yield {"role": m.get("role", default_role), "content": m.get("content", "")}
        elif isinstance(m, str):
            yield {"role": default_role, "content": m}


def _final_assistant(x):
    """Return the last assistant message from x as a singleton list.

    If x is a plain string it is treated as one assistant message.  If x is a
    conversation array, only the last assistant message is kept so that any
    preceding user turns (which are duplicates of the prompt) are not counted
    inside the response mask.
    """
    msgs = list(_iter_msgs(x, "assistant"))
    for m in reversed(msgs):
        if m.get("role") == "assistant":
            return [{"role": "assistant", "content": m.get("content", "")}]
    raise ValueError("no assistant message found in chosen/rejected")


def _prompt_from_conversation(c_msgs, r_msgs):
    """Common message prefix of two conversations, up to (not including) their
    final assistant turns."""
    cl = list(c_msgs)
    rl = list(r_msgs)
    # drop the trailing assistant message from each
    def trim(ms):
        ms = list(ms)
        while ms and ms[-1].get("role") == "assistant":
            ms = ms[:-1]
        return ms
    ct = trim(cl)
    rt = trim(rl)
    n = min(len(ct), len(rt))
    out = []
    for i in range(n):
        if ct[i] == rt[i]:
            out.append(ct[i])
        else:
            break
    if not out:
        # fall back to chosen's prefix
        out = ct
    return out


def normalize(row):
    """Return (prompt_messages, chosen_response_msgs, rejected_response_msgs).

    The prompt is taken from row["prompt"] when present, otherwise derived as
    the shared prefix of chosen/rejected up to the last assistant turn.  Only
    the final assistant message from each of chosen/rejected is used as a
    response.
    """
    raw_prompt = row.get("prompt")
    chosen = row["chosen"]
    rejected = row["rejected"]

    chosen_resp = _final_assistant(chosen)
    rejected_resp = _final_assistant(rejected)

    if raw_prompt is not None and raw_prompt != "":
        prompt_msgs = [dict(m) for m in _iter_msgs(raw_prompt, "user")]
        # Ensure it ends on a non-assistant turn; drop any trailing assistant.
        while prompt_msgs and prompt_msgs[-1].get("role") == "assistant":
            prompt_msgs = prompt_msgs[:-1]
        if not prompt_msgs:
            prompt_msgs = [{"role": "user", "content": ""}]
    else:
        c_all = list(_iter_msgs(chosen, "assistant"))
        r_all = list(_iter_msgs(rejected, "assistant"))
        prompt_msgs = _prompt_from_conversation(c_all, r_all)
        if not prompt_msgs:
            prompt_msgs = [{"role": "user", "content": ""}]
    return prompt_msgs, chosen_resp, rejected_resp


def row_id(row, idx):
    v = row.get("id", row.get("prompt_id", row.get("uid")))
    if v is None:
        return str(idx)
    return str(v)


# --------------------------------------------------------------------------- #
# encoding with explicit assistant-only mask
# --------------------------------------------------------------------------- #
def encode_pair(tokenizer, prompt_msgs, resp_msgs, max_tokens):
    """Return (input_ids, resp_start, response_len, prompt_len_kept)."""
    prompt_str = tokenizer.apply_chat_template(
        prompt_msgs, tokenize=False, add_generation_prompt=True
    )
    full_str = tokenizer.apply_chat_template(
        prompt_msgs + resp_msgs, tokenize=False, add_generation_prompt=False
    )
    if not isinstance(prompt_str, str) or not isinstance(full_str, str):
        raise ValueError("chat template did not return a string")

    if full_str.startswith(prompt_str):
        response_str = full_str[len(prompt_str):]
        prompt_used = prompt_str
    else:
        c = 0
        m = min(len(prompt_str), len(full_str))
        while c < m and prompt_str[c] == full_str[c]:
            c += 1
        if c == 0:
            raise ValueError("chat template has no common prefix between prompt and full")
        response_str = full_str[c:]
        prompt_used = full_str[:c]

    prompt_ids = list(tokenizer(prompt_used, add_special_tokens=False)["input_ids"])
    response_ids = list(tokenizer(response_str, add_special_tokens=False)["input_ids"])

    if not response_ids:
        raise ValueError("chat template produced no response tokens")
    if not prompt_ids:
        raise ValueError("chat template produced no prompt tokens")

    truncated = False
    if len(prompt_ids) + len(response_ids) > max_tokens:
        truncated = True
        if len(response_ids) + 1 <= max_tokens:
            n_prompt = max_tokens - len(response_ids)
            prompt_ids = prompt_ids[-n_prompt:]
        else:
            n_prompt = min(len(prompt_ids),
                           MAX_PROMPT_KEEP_ON_RESP_OVERFLOW,
                           max_tokens - 1)
            if n_prompt < 1:
                n_prompt = 1
            n_resp = max_tokens - n_prompt
            if n_resp < 1:
                n_resp = 1
                n_prompt = max_tokens - 1
            if n_resp > len(response_ids):
                n_resp = len(response_ids)
                n_prompt = max(1, max_tokens - n_resp)
            prompt_ids = prompt_ids[-n_prompt:]
            response_ids = response_ids[:n_resp]

    if not response_ids:
        raise ValueError("response became empty after truncation")
    if not prompt_ids:
        raise ValueError("prompt became empty after truncation")

    full_ids = prompt_ids + response_ids
    return full_ids, len(prompt_ids), len(response_ids), len(prompt_ids), truncated


def seq_logprob(model, input_ids, resp_start):
    """Sum of log p(token) over response positions only (prompt excluded)."""
    if resp_start <= 0:
        raise ValueError("resp_start must be >= 1")
    out = model(input_ids=input_ids)
    logits = out.logits[0]
    t = input_ids.shape[1]
    pred = logits[resp_start - 1: t - 1, :]
    tgt = input_ids[0, resp_start:t]
    logp = F.log_softmax(pred.float(), dim=-1)
    lp = logp.gather(-1, tgt.unsqueeze(-1)).squeeze(-1)
    return lp.sum()


# --------------------------------------------------------------------------- #
# doctor
# --------------------------------------------------------------------------- #
def cmd_doctor(args):
    missing = []
    inp = args.input
    for fname in ("manifest.json", "train.jsonl", "validation.jsonl"):
        p = os.path.join(inp, fname)
        if not os.path.exists(p):
            missing.append(p)
    mp = find_model_path(inp)
    if mp is None:
        missing.append("model dir: %s or manifest model_container_path" % DEFAULT_MODEL)
    if not torch.cuda.is_available():
        missing.append("CUDA device")
    try:
        import transformers  # noqa: F401
    except Exception as e:
        missing.append("transformers: %s" % e)

    hashes = {}
    mf = os.path.join(inp, "manifest.json")
    if os.path.exists(mf):
        try:
            m = json.load(open(mf, encoding="utf-8"))
            for fname, want in (m.get("files") or {}).items():
                p = os.path.join(inp, fname)
                if os.path.exists(p):
                    got = sha256_file(p)
                    hashes[fname] = {"sha256": got, "matches_manifest": got == want}
                    if got != want:
                        missing.append("hash mismatch for %s" % fname)
        except Exception as e:
            missing.append("manifest parse: %s" % e)

    report = {
        "status": "missing" if missing else "ok",
        "missing": missing,
        "model_path": mp,
        "cuda": torch.cuda.is_available(),
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "torch": torch.__version__,
        "hashes": hashes,
    }
    print(json.dumps(report, indent=2))
    return 78 if missing else 0


# --------------------------------------------------------------------------- #
# shared model load
# --------------------------------------------------------------------------- #
def _from_pretrained_causal(model_path):
    from transformers import AutoModelForCausalLM
    try:
        return AutoModelForCausalLM.from_pretrained(model_path, dtype=torch.float32)
    except TypeError:
        return AutoModelForCausalLM.from_pretrained(model_path, torch_dtype=torch.float32)


def load_models(model_path):
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    policy = _from_pretrained_causal(model_path).to("cuda")
    reference = _from_pretrained_causal(model_path).to("cuda")
    reference.eval()
    for p in reference.parameters():
        p.requires_grad_(False)
    return tokenizer, policy, reference


def eval_pairs(tokenizer, rows, policy, reference, max_tokens):
    device = "cuda"
    recs = []
    for i, row in enumerate(rows):
        pm, cm, rm = normalize(row)
        ch_ids, ch_start, ch_len, ch_prompt, ch_tr = encode_pair(tokenizer, pm, cm, max_tokens)
        rj_ids, rj_start, rj_len, rj_prompt, rj_tr = encode_pair(tokenizer, pm, rm, max_tokens)
        ch_t = torch.tensor([ch_ids], dtype=torch.long, device=device)
        rj_t = torch.tensor([rj_ids], dtype=torch.long, device=device)
        with torch.no_grad():
            pi_c = float(seq_logprob(policy, ch_t, ch_start))
            pi_r = float(seq_logprob(policy, rj_t, rj_start))
            rf_c = float(seq_logprob(reference, ch_t, ch_start))
            rf_r = float(seq_logprob(reference, rj_t, rj_start))
        margin = BETA * ((pi_c - pi_r) - (rf_c - rf_r))
        dpo = float(-F.logsigmoid(torch.tensor(margin)).item())
        recs.append({
            "id": row_id(row, i),
            "policy": {"chosen_logprob": pi_c, "rejected_logprob": pi_r},
            "reference": {"chosen_logprob": rf_c, "rejected_logprob": rf_r},
            "dpo_loss": dpo,
            "margin": margin,
            "policy_prefers_chosen": bool((pi_c - pi_r) > 0.0),
            "preference": "chosen" if margin > 0.0 else "rejected",
            "chosen_tokens": ch_len,
            "rejected_tokens": rj_len,
            "chosen_truncated": ch_tr,
            "rejected_truncated": rj_tr,
            "responses_identical_after_truncation": bool(ch_ids == rj_ids),
            "finite": all(math.isfinite(v) for v in (pi_c, pi_r, rf_c, rf_r, margin, dpo)),
        })
    acc = sum(1 for r in recs if r["preference"] == "chosen") / max(1, len(recs))
    pol_acc = sum(1 for r in recs if r["policy_prefers_chosen"]) / max(1, len(recs))
    return recs, acc, pol_acc


# --------------------------------------------------------------------------- #
# train
# --------------------------------------------------------------------------- #
def cmd_train(args):
    t0 = now()
    if not torch.cuda.is_available():
        print("ERROR: CUDA is required for training", file=sys.stderr)
        return 3

    train_path = os.path.join(args.input, "train.jsonl")
    val_path = os.path.join(args.input, "validation.jsonl")
    for p in (train_path, val_path):
        if not os.path.exists(p):
            print("ERROR: missing input %s" % p, file=sys.stderr)
            return 78
    model_path = find_model_path(args.input)
    if model_path is None:
        print("ERROR: base model not found", file=sys.stderr)
        return 78
    revision = read_revision(args.input)
    os.makedirs(args.output, exist_ok=True)

    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    random.seed(SEED)
    import numpy as np
    np.random.seed(SEED)
    import transformers

    tokenizer, policy, reference = load_models(model_path)
    policy.train()

    ref_before = sha256_params(reference)
    pol_before = sha256_params(policy)

    train_rows = load_jsonl(train_path)
    val_rows = load_jsonl(val_path)

    enc_train = []
    truncated_rows = 0
    identical_truncated_rows = 0
    for i, row in enumerate(train_rows):
        pm, cm, rm = normalize(row)
        try:
            ch_ids, ch_start, ch_len, ch_prompt, ch_tr = encode_pair(tokenizer, pm, cm, MAX_TOKENS)
            rj_ids, rj_start, rj_len, rj_prompt, rj_tr = encode_pair(tokenizer, pm, rm, MAX_TOKENS)
        except Exception as e:
            print("ERROR: train row %s could not be encoded: %s" % (row_id(row, i), e),
                  file=sys.stderr)
            return 78
        enc_train.append((row_id(row, i), ch_ids, ch_start, rj_ids, rj_start))
        if ch_tr or rj_tr:
            truncated_rows += 1
        if ch_ids == rj_ids:
            identical_truncated_rows += 1

    opt = torch.optim.AdamW(policy.parameters(), lr=args.lr, betas=(0.9, 0.999),
                            weight_decay=0.0)
    device = "cuda"
    losses = []
    steps_used_per_row = {}
    step = 0
    torch.cuda.synchronize()
    train_start = now()
    for epoch in range(args.epochs):
        for rid, ch_ids, ch_start, rj_ids, rj_start in enc_train:
            ch_t = torch.tensor([ch_ids], dtype=torch.long, device=device)
            rj_t = torch.tensor([rj_ids], dtype=torch.long, device=device)
            pi_c = seq_logprob(policy, ch_t, ch_start)
            pi_r = seq_logprob(policy, rj_t, rj_start)
            with torch.no_grad():
                rf_c = seq_logprob(reference, ch_t, ch_start)
                rf_r = seq_logprob(reference, rj_t, rj_start)
            margin = BETA * ((pi_c - pi_r) - (rf_c - rf_r))
            loss = -F.logsigmoid(margin)
            if not torch.isfinite(loss):
                print("ERROR: non-finite loss at epoch %d row %s" % (epoch, rid),
                      file=sys.stderr)
                return 3
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(policy.parameters(), 1.0)
            opt.step()
            step += 1
            losses.append(float(loss.detach().item()))
            steps_used_per_row[rid] = steps_used_per_row.get(rid, 0) + 1
    torch.cuda.synchronize()
    train_s = now() - train_start

    pol_after = sha256_params(policy)
    ref_after = sha256_params(reference)

    policy.eval()
    val_recs, val_acc, val_pol_acc = eval_pairs(tokenizer, val_rows, policy, reference, MAX_TOKENS)
    train_recs, tr_acc, tr_pol_acc = eval_pairs(tokenizer, train_rows, policy, reference, MAX_TOKENS)

    ckpt = os.path.join(args.output, "checkpoint")
    os.makedirs(ckpt, exist_ok=True)
    policy.save_pretrained(ckpt)
    tokenizer.save_pretrained(ckpt)
    with open(os.path.join(ckpt, "reference_binding.json"), "w", encoding="utf-8") as f:
        json.dump({"model_path": model_path, "revision": revision, "frozen": True,
                   "reference_param_sha256": ref_after}, f, indent=2)

    torch.save({
        "optimizer": opt.state_dict(),
        "step": step,
        "epochs": args.epochs,
        "lr": args.lr,
        "beta": BETA,
        "max_tokens": MAX_TOKENS,
        "seed": SEED,
        "reference": {"model_path": model_path, "revision": revision,
                      "sha256_before": ref_before, "sha256_after": ref_after},
        "policy_sha256_before": pol_before,
        "policy_sha256_after": pol_after,
        "rng": {"torch": torch.get_rng_state(), "python": random.getstate()},
        "losses": losses,
        "steps_used_per_row": steps_used_per_row,
    }, os.path.join(args.output, "training_state.pt"))

    prefs = {
        "beta": BETA,
        "max_tokens": MAX_TOKENS,
        "split": "validation",
        "n": len(val_recs),
        "preference_accuracy": val_acc,
        "policy_self_accuracy": val_pol_acc,
        "pairs": val_recs,
    }
    with open(os.path.join(args.output, "preferences.json"), "w", encoding="utf-8") as f:
        json.dump(prefs, f, indent=2)

    train_prefs = {
        "beta": BETA,
        "max_tokens": MAX_TOKENS,
        "split": "train",
        "n": len(train_recs),
        "preference_accuracy": tr_acc,
        "pairs": train_recs,
    }
    with open(os.path.join(args.output, "train_preferences.json"), "w", encoding="utf-8") as f:
        json.dump(train_prefs, f, indent=2)

    run = {
        "task_id": "GPUv1-A02",
        "scale": "debug_only",
        "device": "cuda",
        "gpu_name": torch.cuda.get_device_name(0),
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "seed": SEED,
        "beta": BETA,
        "max_tokens": MAX_TOKENS,
        "epochs": args.epochs,
        "lr": args.lr,
        "steps": step,
        "train_rows": len(train_rows),
        "validation_rows": len(val_rows),
        "truncated_rows": truncated_rows,
        "identical_truncated_rows": identical_truncated_rows,
        "all_train_rows_used": bool(all(v >= 1 for v in steps_used_per_row.values())
                                       and len(steps_used_per_row) == len(train_rows)),
        "model_path": model_path,
        "model_revision": revision,
        "input_sha256": {f: sha256_file(os.path.join(args.input, f))
                         for f in ("train.jsonl", "validation.jsonl")},
        "reference_param_sha256_before": ref_before,
        "reference_param_sha256_after": ref_after,
        "reference_unchanged": ref_before == ref_after,
        "policy_param_sha256_before": pol_before,
        "policy_param_sha256_after": pol_after,
        "policy_changed": pol_before != pol_after,
        "loss_first": losses[0] if losses else None,
        "loss_last": losses[-1] if losses else None,
        "loss_mean": sum(losses) / len(losses) if losses else None,
        "all_losses_finite": all(math.isfinite(v) for v in losses),
        "train_preference_accuracy": tr_acc,
        "validation_preference_accuracy": val_acc,
        "durations_s": {
            "total_train": train_s,
            "total_wall": now() - t0,
            "per_step_median": (train_s / step) if step else None,
        },
    }
    with open(os.path.join(args.output, "run.json"), "w", encoding="utf-8") as f:
        json.dump(run, f, indent=2)

    print(json.dumps({
        "status": "ok",
        "steps": step,
        "policy_changed": pol_before != pol_after,
        "reference_unchanged": ref_before == ref_after,
        "truncated_rows": truncated_rows,
        "identical_truncated_rows": identical_truncated_rows,
        "validation_preference_accuracy": val_acc,
        "checkpoint": ckpt,
    }, indent=2))
    return 0


# --------------------------------------------------------------------------- #
# evaluate
# --------------------------------------------------------------------------- #
def cmd_evaluate(args):
    if not torch.cuda.is_available():
        print("ERROR: CUDA is required for evaluation", file=sys.stderr)
        return 3
    if not os.path.isdir(args.checkpoint):
        print("ERROR: checkpoint dir missing: %s" % args.checkpoint, file=sys.stderr)
        return 78
    if not os.path.exists(args.input):
        print("ERROR: validation file missing: %s" % args.input, file=sys.stderr)
        return 78

    from transformers import AutoTokenizer

    binding_path = os.path.join(args.checkpoint, "reference_binding.json")
    model_path = DEFAULT_MODEL
    revision = None
    if os.path.exists(binding_path):
        b = json.load(open(binding_path, encoding="utf-8"))
        model_path = b.get("model_path", DEFAULT_MODEL)
        revision = b.get("revision")
    if not os.path.isdir(model_path):
        print("ERROR: reference model dir missing: %s" % model_path, file=sys.stderr)
        return 78

    torch.manual_seed(SEED)
    tokenizer = AutoTokenizer.from_pretrained(args.checkpoint)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    policy = _from_pretrained_causal(args.checkpoint).to("cuda").eval()
    reference = _from_pretrained_causal(model_path).to("cuda").eval()
    for p in reference.parameters():
        p.requires_grad_(False)

    rows = load_jsonl(args.input)
    torch.cuda.synchronize()
    t0 = now()
    recs, acc, pol_acc = eval_pairs(tokenizer, rows, policy, reference, MAX_TOKENS)
    torch.cuda.synchronize()
    elapsed = now() - t0

    out = {
        "beta": BETA,
        "max_tokens": MAX_TOKENS,
        "reloaded": True,
        "checkpoint": args.checkpoint,
        "reference": {"model_path": model_path, "revision": revision, "frozen": True},
        "n": len(recs),
        "preference_accuracy": acc,
        "policy_self_accuracy": pol_acc,
        "all_finite": all(r["finite"] for r in recs),
        "evaluate_wall_s": elapsed,
        "pairs": recs,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(json.dumps({"status": "ok", "n": len(recs),
                      "preference_accuracy": acc,
                      "all_finite": out["all_finite"]}, indent=2))
    return 0


# --------------------------------------------------------------------------- #
def build_parser():
    p = argparse.ArgumentParser(prog="main.py", description="GPUv1-A02 DPO debug variant")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="inspect inputs and dependencies without loading models")
    d.add_argument("--input", required=True)

    t = sub.add_parser("train", help="run real CUDA DPO training")
    t.add_argument("--input", required=True)
    t.add_argument("--output", required=True)
    t.add_argument("--epochs", type=int, default=3)
    t.add_argument("--lr", type=float, default=1e-5)

    e = sub.add_parser("evaluate", help="reload the checkpoint and recompute log-probs")
    e.add_argument("--checkpoint", required=True)
    e.add_argument("--input", required=True)
    e.add_argument("--output", required=True)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.cmd == "doctor":
        return cmd_doctor(args)
    if args.cmd == "train":
        return cmd_train(args)
    if args.cmd == "evaluate":
        return cmd_evaluate(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
