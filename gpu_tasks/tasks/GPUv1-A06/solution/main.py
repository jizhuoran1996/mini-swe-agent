#!/usr/bin/env python3
"""GPUv1-A06 debug variant.

Self-supervised masked-latent contrastive pretraining of Wav2Vec2 on the real
16 kHz LibriSpeech dev-clean subset listed in input/train.jsonl.  No text
labels are used and no synthetic audio is created.
"""

import argparse
import hashlib
import json
import os
import sys
import time
import wave

import numpy as np


SEED = 1234
MODEL_DIR = "/models/facebook--wav2vec2-base"
SAMPLE_RATE = 16000
MAX_SECONDS = 4
MAX_SAMPLES = SAMPLE_RATE * MAX_SECONDS
BATCH_SIZE = 4
EPOCHS = 1
LR = 1e-5


def _fail(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def read_jsonl(path):
    recs = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    return recs


def resolve_audio_path(rec, base_dir):
    for k in ("audio", "audio_path", "path", "file", "wav", "filename"):
        v = rec.get(k)
        if isinstance(v, str):
            return v if os.path.isabs(v) else os.path.join(base_dir, v)
    for k in ("id", "audio_id", "utt_id", "utt", "name"):
        v = rec.get(k)
        if isinstance(v, str):
            for cand in (
                os.path.join(base_dir, "audio", v + ".wav"),
                os.path.join(base_dir, v + ".wav"),
            ):
                if os.path.exists(cand):
                    return cand
    raise ValueError(f"cannot resolve audio path from record keys {list(rec.keys())}")


def load_wav(path):
    with wave.open(path, "rb") as w:
        ch = w.getnchannels()
        sw = w.getsampwidth()
        sr = w.getframerate()
        n = w.getnframes()
        raw = w.readframes(n)
    if sr != SAMPLE_RATE:
        raise ValueError(f"{path}: expected {SAMPLE_RATE} Hz, got {sr}")
    if sw == 2:
        arr = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sw == 4:
        arr = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    elif sw == 1:
        arr = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"{path}: unsupported sample width {sw}")
    if ch > 1:
        arr = arr.reshape(-1, ch).mean(axis=1)
    return arr.astype(np.float32)


def params_hash(model):
    import torch

    h = hashlib.sha256()
    for name, p in sorted(model.named_parameters()):
        if not p.requires_grad:
            continue
        h.update(name.encode())
        t = p.detach().to("cpu", torch.float32).contiguous().numpy()
        h.update(t.tobytes())
    return h.hexdigest()


def compute_mask_time_indices(shape, mask_prob, mask_length, feat_attn_mask=None, min_masks=2):
    """Official-style span mask sampling that never selects padded positions."""
    import torch

    B, T = shape
    mask_length = int(max(mask_length, 1))
    if mask_length > T:
        return torch.zeros((B, T), dtype=torch.bool)

    num_masked_spans = int(mask_prob * T / mask_length + torch.rand(1).item())
    num_masked_spans = max(num_masked_spans, min_masks)
    if num_masked_spans * mask_length > T:
        num_masked_spans = max(T // mask_length, 1)

    mask = torch.zeros((B, T), dtype=torch.bool)
    if feat_attn_mask is None:
        valid = np.ones((B, T), dtype=np.int64)
    else:
        valid = feat_attn_mask.detach().to("cpu").numpy().astype(np.int64)

    for i in range(B):
        v = valid[i]
        if mask_length == 1:
            starts = np.where(v == 1)[0]
        else:
            if v.shape[0] < mask_length:
                continue
            csum = np.concatenate([[0], np.cumsum(v)])
            win = csum[mask_length:] - csum[:-mask_length]
            starts = np.where(win == mask_length)[0]
        if len(starts) == 0:
            continue
        chosen = np.random.choice(starts, size=num_masked_spans, replace=True)
        for s in chosen:
            mask[i, int(s) : int(s) + mask_length] = True
    return mask


def cmd_doctor(args):
    inp = args.input
    problems = []
    for name in ("train.jsonl", "validation.jsonl"):
        p = os.path.join(inp, name)
        if not os.path.exists(p):
            problems.append(f"missing input file: {p}")
    if not os.path.isdir(MODEL_DIR):
        problems.append(f"missing model dir: {MODEL_DIR}")
    else:
        if not os.path.exists(os.path.join(MODEL_DIR, "config.json")):
            problems.append(f"missing {MODEL_DIR}/config.json")
        has_w = any(
            os.path.exists(os.path.join(MODEL_DIR, n))
            for n in ("model.safetensors", "pytorch_model.bin")
        )
        if not has_w:
            problems.append(f"missing model weights in {MODEL_DIR}")

    for name in ("train.jsonl", "validation.jsonl"):
        p = os.path.join(inp, name)
        if not os.path.exists(p):
            continue
        try:
            recs = read_jsonl(p)
        except Exception as e:
            problems.append(f"cannot parse {p}: {e}")
            continue
        for r in recs:
            try:
                ap = resolve_audio_path(r, inp)
            except Exception as e:
                problems.append(f"cannot resolve audio in {p}: {e}")
                continue
            if not os.path.exists(ap):
                problems.append(f"missing audio: {ap}")

    try:
        import torch

        try:
            if not torch.cuda.is_available():
                problems.append("CUDA not available")
        except Exception as e:
            problems.append(f"CUDA check failed: {e}")
    except Exception as e:
        problems.append(f"torch not importable: {e}")
    try:
        import transformers  # noqa: F401
    except Exception as e:
        problems.append(f"transformers not importable: {e}")

    if problems:
        print("DOCTOR: unresolved requirements:")
        for p in problems:
            print(f"  - {p}")
        return 78
    print("DOCTOR: all required inputs and dependencies are available")
    return 0


def cmd_train(args):
    import torch
    from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2ForPreTraining

    if not torch.cuda.is_available():
        _fail("CUDA is required but not available")
    device = torch.device("cuda")
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    torch.cuda.manual_seed_all(SEED)

    inp, out = args.input, args.output
    ckpt_dir = os.path.join(out, "checkpoint")
    os.makedirs(ckpt_dir, exist_ok=True)

    train_jsonl = os.path.join(inp, "train.jsonl")
    if not os.path.exists(train_jsonl):
        _fail(f"missing {train_jsonl}")
    recs = read_jsonl(train_jsonl)
    if len(recs) == 0:
        _fail("train.jsonl is empty")

    t_start = time.time()
    t_load0 = time.time()
    wavs, lengths, ids = [], [], []
    trunc_total = 0.0
    for r in recs:
        ap = resolve_audio_path(r, inp)
        if not os.path.exists(ap):
            _fail(f"missing audio file: {ap}")
        a = load_wav(ap)
        t_trunc0 = time.time()
        a = a[:MAX_SAMPLES]
        trunc_total += time.time() - t_trunc0
        if a.shape[0] == 0:
            _fail(f"empty audio: {ap}")
        wavs.append(a)
        lengths.append(a.shape[0])
        ids.append(r.get("id") or r.get("audio_id") or os.path.basename(ap))
    data_load_s = time.time() - t_load0

    t_model0 = time.time()
    model = Wav2Vec2ForPreTraining.from_pretrained(MODEL_DIR)
    model.to(device)
    model.train()
    model.freeze_feature_encoder()
    model_load_s = time.time() - t_model0

    cfg = model.config
    mask_prob = float(getattr(cfg, "mask_time_prob", 0.05))
    mask_length = int(getattr(cfg, "mask_time_length", 10))
    num_negatives = int(getattr(cfg, "num_negatives", 100))
    diversity_w = float(getattr(cfg, "diversity_loss_weight", 0.1))

    trainable = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(
        trainable, lr=LR, betas=(0.9, 0.98), eps=1e-8, weight_decay=0.01
    )

    initial_hash = params_hash(model)

    with torch.no_grad():
        dummy = torch.zeros(1, MAX_SAMPLES, device=device)
        T = int(model.wav2vec2.feature_extractor(dummy).shape[-1])

    sys.stdout.write(
        f"[train] recordings={len(recs)} frames/segment={T} mask_prob={mask_prob} "
        f"mask_length={mask_length} num_negatives={num_negatives} batch={BATCH_SIZE}\n"
    )
    sys.stdout.flush()

    torch.cuda.synchronize()
    train_t0 = time.time()
    losses, cl_losses, dl_losses, grad_norms = [], [], [], []
    total_masked = 0
    steps = 0
    index_order = np.arange(len(wavs))

    for _epoch in range(EPOCHS):
        np.random.shuffle(index_order)
        for bstart in range(0, len(index_order), BATCH_SIZE):
            bidx = index_order[bstart : bstart + BATCH_SIZE]
            B = len(bidx)
            x = np.zeros((B, MAX_SAMPLES), dtype=np.float32)
            for j, i in enumerate(bidx):
                a = wavs[i]
                x[j, : a.shape[0]] = a
            input_values = torch.from_numpy(x).to(device)
            attn = torch.zeros((B, MAX_SAMPLES), dtype=torch.long, device=device)
            for j, i in enumerate(bidx):
                attn[j, : lengths[i]] = 1

            feat_attn = model.wav2vec2._get_feature_vector_attention_mask(T, attn)

            mask_time_indices = compute_mask_time_indices(
                (B, T), mask_prob, mask_length, feat_attn
            ).to(device)

            for j in range(B):
                valid_len = int(feat_attn[j].sum().item())
                if bool(mask_time_indices[j, valid_len:].any()):
                    _fail("mask selected padded time positions")

            if hasattr(model, "_sample_negative_indices"):
                sampled_neg = model._sample_negative_indices((B, T), num_negatives).to(device)
            else:
                sampled_neg = torch.randint(0, T, (B, T, num_negatives), device=device)

            outputs = model(
                input_values,
                attention_mask=attn,
                mask_time_indices=mask_time_indices,
                sampled_negative_indices=sampled_neg,
            )
            loss = outputs.loss
            if loss is None or not torch.isfinite(loss):
                _fail(f"non-finite loss at step {steps}: {loss}")

            optimizer.zero_grad()
            loss.backward()
            gn = torch.nn.utils.clip_grad_norm_(trainable, 1.0)
            if not torch.isfinite(gn):
                _fail(f"non-finite grad norm at step {steps}")
            optimizer.step()

            steps += 1
            losses.append(float(loss.item()))
            cl = getattr(outputs, "contrastive_loss", None)
            dl = getattr(outputs, "diversity_loss", None)
            cl_losses.append(float(cl.item()) if cl is not None else None)
            dl_losses.append(float(dl.item()) if dl is not None else None)
            grad_norms.append(float(gn.item()))
            total_masked += int(mask_time_indices.sum().item())
            sys.stdout.write(
                f"[train] step {steps} loss={losses[-1]:.4f} "
                f"contrastive={cl_losses[-1]} diversity={dl_losses[-1]} "
                f"grad_norm={grad_norms[-1]:.4f}\n"
            )
            sys.stdout.flush()
    torch.cuda.synchronize()
    train_sync_s = time.time() - train_t0

    final_hash = params_hash(model)

    save_t0 = time.time()
    model.config.architectures = ["Wav2Vec2ForPreTraining"]
    model.save_pretrained(ckpt_dir)
    fe = Wav2Vec2FeatureExtractor(
        feature_size=1,
        sampling_rate=SAMPLE_RATE,
        padding_value=0.0,
        do_normalize=False,
        return_attention_mask=False,
    )
    fe.save_pretrained(ckpt_dir)

    torch.save(
        {
            "optimizer": optimizer.state_dict(),
            "step": steps,
            "torch_rng_state": torch.get_rng_state(),
            "cuda_rng_state": torch.cuda.get_rng_state_all(),
            "numpy_rng_state": np.random.get_state(),
            "seed": SEED,
        },
        os.path.join(out, "training_state.pt"),
    )
    save_s = time.time() - save_t0

    import transformers as _tf

    run_json = {
        "task": "GPUv1-A06",
        "variant": "debug",
        "seed": SEED,
        "device": "cuda",
        "gpu_name": torch.cuda.get_device_name(0),
        "torch_version": torch.__version__,
        "transformers_version": _tf.__version__,
        "model_source": MODEL_DIR,
        "source": "LibriSpeech dev-clean subset (hf-internal-testing/librispeech_asr_dummy)",
        "num_train_recordings": len(recs),
        "recording_ids": ids,
        "truncation": {
            "max_seconds": MAX_SECONDS,
            "sample_rate": SAMPLE_RATE,
            "max_samples": MAX_SAMPLES,
            "truncation_wall_s": trunc_total,
        },
        "objective": "wav2vec2 masked latent contrastive + codevector diversity",
        "learning_rate": LR,
        "batch_size": BATCH_SIZE,
        "epochs": EPOCHS,
        "optimizer": "AdamW(betas=(0.9,0.98),eps=1e-8,wd=0.01)",
        "optimizer_steps": steps,
        "masking": {
            "mask_time_prob": mask_prob,
            "mask_length": mask_length,
            "min_masks": 2,
            "feature_frames_per_segment": T,
            "total_masked_positions": total_masked,
            "total_masked_spans_estimate": int(round(total_masked / max(mask_length, 1))),
            "masks_never_select_padding": True,
        },
        "negatives": {
            "num_negatives_per_position": num_negatives,
            "total_negative_samples": total_masked * num_negatives,
        },
        "diversity_loss_weight": diversity_w,
        "loss": {
            "total": losses,
            "contrastive": cl_losses,
            "diversity": dl_losses,
            "initial_total": losses[0] if losses else None,
            "final_total": losses[-1] if losses else None,
            "initial_contrastive": cl_losses[0] if cl_losses else None,
            "final_contrastive": cl_losses[-1] if cl_losses else None,
            "initial_diversity": dl_losses[0] if dl_losses else None,
            "final_diversity": dl_losses[-1] if dl_losses else None,
            "all_finite": all(np.isfinite(x) for x in losses),
        },
        "grad_norm": {
            "values": grad_norms,
            "initial": grad_norms[0] if grad_norms else None,
            "final": grad_norms[-1] if grad_norms else None,
        },
        "weights_changed": initial_hash != final_hash,
        "param_hash_initial": initial_hash,
        "param_hash_final": final_hash,
        "timings_s": {
            "data_load_and_truncate": data_load_s,
            "model_load": model_load_s,
            "train_synchronized": train_sync_s,
            "save": save_s,
            "total": time.time() - t_start,
        },
    }
    with open(os.path.join(out, "run.json"), "w") as f:
        json.dump(run_json, f, indent=2)
    sys.stdout.write(f"[train] saved checkpoint and run.json to {out}\n")


def cmd_encode(args):
    import torch
    from transformers import Wav2Vec2ForPreTraining

    if not torch.cuda.is_available():
        _fail("CUDA is required but not available")
    device = torch.device("cuda")

    ckpt = args.checkpoint
    if not os.path.isdir(ckpt):
        _fail(f"checkpoint dir not found: {ckpt}")

    inp_path = args.input
    if os.path.isdir(inp_path):
        inp_path = os.path.join(inp_path, "validation.jsonl")
    if not os.path.exists(inp_path):
        _fail(f"missing input jsonl: {inp_path}")
    base_dir = os.path.dirname(os.path.abspath(inp_path))
    recs = read_jsonl(inp_path)
    if len(recs) == 0:
        _fail("validation.jsonl is empty")

    model = Wav2Vec2ForPreTraining.from_pretrained(ckpt)
    model.to(device).eval()

    out = args.output
    os.makedirs(out, exist_ok=True)

    feats, feat_ids = [], []
    t0 = time.time()
    with torch.no_grad():
        for r in recs:
            ap = resolve_audio_path(r, base_dir)
            if not os.path.exists(ap):
                _fail(f"missing audio: {ap}")
            a = load_wav(ap)[:MAX_SAMPLES]
            if a.shape[0] == 0:
                _fail(f"empty audio: {ap}")
            iv = torch.from_numpy(a).unsqueeze(0).to(device)
            attn = torch.ones_like(iv, dtype=torch.long)
            enc = model.wav2vec2(iv, attention_mask=attn)
            hidden = enc.last_hidden_state
            feat_attn = model.wav2vec2._get_feature_vector_attention_mask(
                hidden.shape[1], attn
            )
            m = feat_attn.unsqueeze(-1).float()
            pooled = (hidden * m).sum(dim=1) / m.sum(dim=1).clamp(min=1e-6)
            pooled = pooled.squeeze(0)
            pooled = pooled / pooled.norm(p=2).clamp(min=1e-8)
            feats.append(pooled.detach().cpu().numpy().astype(np.float32))
            feat_ids.append(r.get("id") or r.get("audio_id") or os.path.basename(ap))
    torch.cuda.synchronize()
    encode_s = time.time() - t0

    features = np.stack(feats, axis=0)
    np.save(os.path.join(out, "features.npy"), features)

    with open(os.path.join(out, "features_meta.json"), "w") as f:
        json.dump(
            {
                "shape": list(features.shape),
                "dtype": str(features.dtype),
                "ids": feat_ids,
                "pooling": "attention-mask mean",
                "l2_normalized": True,
                "encoder_hidden_size": int(features.shape[-1]),
                "checkpoint": ckpt,
                "input_jsonl": inp_path,
                "encode_synchronized_wall_s": encode_s,
            },
            f,
            indent=2,
        )
    sys.stdout.write(f"[encode] saved {features.shape} to {out}/features.npy\n")


def main():
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="GPUv1-A06 debug: Wav2Vec2 masked latent contrastive pretraining on real audio",
    )
    sub = parser.add_subparsers(dest="cmd")

    pt = sub.add_parser("train", help="Run self-supervised pretraining on input/train.jsonl")
    pt.add_argument("--input", required=True, help="input dir with train.jsonl + audio/")
    pt.add_argument("--output", required=True, help="output dir for checkpoint/ + run.json")

    pe = sub.add_parser("encode", help="Extract mean-pooled features from a checkpoint")
    pe.add_argument("--checkpoint", required=True)
    pe.add_argument("--input", required=True, help="validation.jsonl (or a dir)")
    pe.add_argument("--output", required=True)

    pd = sub.add_parser("doctor", help="Inspect input files and dependencies")
    pd.add_argument("--input", required=True)

    args = parser.parse_args()
    if args.cmd is None:
        parser.print_help()
        return 0
    if args.cmd == "train":
        cmd_train(args)
    elif args.cmd == "encode":
        cmd_encode(args)
    elif args.cmd == "doctor":
        return cmd_doctor(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
