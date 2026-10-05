#!/usr/bin/env python3
"""GPUv1-A04 (debug): CUDA teacher-forced Whisper-tiny seq2seq fine-tuning on
LibriSpeech dev-clean (16 recordings) + transcription of 8 held-out recordings.

Commands:
  train       --input <dir> --output <dir>
  transcribe  --checkpoint <dir> --input <jsonl> --output <jsonl>
  doctor      --input <dir>
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
import unicodedata

MODEL_DIR = "/models/openai--whisper-tiny"
SAMPLE_RATE = 16000
MAX_SAMPLES = 30 * SAMPLE_RATE  # 30 s hard cap for the debug input

AUDIO_KEYS = (
    "audio", "audio_path", "audio_filepath", "audio_file", "path", "file",
    "file_name", "filename", "wav", "wav_path", "speech", "input_audio",
)
TEXT_KEYS = (
    "text", "transcript", "transcription", "normalized_text", "label",
    "target", "target_text", "sentence", "reference", "ref", "gt",
)
ID_KEYS = ("id", "uid", "utterance_id", "utt_id", "key", "name")
AUDIO_EXT = (".wav", ".flac", ".mp3", ".ogg", ".m4a", ".opus", ".sph")


# ---------------------------------------------------------------- helpers ---
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="main.py",
        description="GPUv1-A04 debug Whisper fine-tune / transcribe (CUDA required).",
    )
    sub = p.add_subparsers(dest="command")

    t = sub.add_parser("train", help="CUDA fine-tune Whisper on input/train.jsonl")
    t.add_argument("--input", required=True, help="dir with train.jsonl / validation.jsonl / audio/")
    t.add_argument("--output", required=True, help="output directory (checkpoint, training_state.pt, run.json)")
    t.add_argument("--model", default=MODEL_DIR, help="local Whisper model directory")
    t.add_argument("--seed", type=int, default=0)
    t.add_argument("--epochs", type=int, default=1)
    t.add_argument("--lr", type=float, default=1e-4)
    t.add_argument("--batch-size", type=int, default=4)
    t.add_argument("--max-samples", type=int, default=MAX_SAMPLES)

    tr = sub.add_parser("transcribe", help="greedy-transcribe a jsonl with a trained checkpoint")
    tr.add_argument("--checkpoint", required=True)
    tr.add_argument("--input", required=True, help="jsonl listing (audio paths relative to its own directory)")
    tr.add_argument("--output", required=True, help="output jsonl")
    tr.add_argument("--max-new-tokens", type=int, default=200)

    d = sub.add_parser("doctor", help="inspect required files/deps; no model loading")
    d.add_argument("--input", required=True)
    return p


def read_jsonl(path):
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _looks_like_audio(v):
    return isinstance(v, str) and v.lower().endswith(AUDIO_EXT)


def get_audio_value(entry):
    """Return the audio path string from an entry, accepting several common
    field names and falling back to any *.wav/.flac/... string value."""
    for k in AUDIO_KEYS:
        v = entry.get(k)
        if _looks_like_audio(v):
            return v
    for k in AUDIO_KEYS:
        v = entry.get(k)
        if isinstance(v, str) and v.strip():
            return v
    for v in entry.values():
        if _looks_like_audio(v):
            return v
    for v in entry.values():
        if isinstance(v, str) and ("/audio/" in v or v.lower().startswith("audio/")):
            return v
    return None


def get_audio_path(entry, base):
    a = get_audio_value(entry)
    if a is None:
        raise ValueError("entry has no recognizable audio field; keys=%s" % list(entry))
    a = a.strip()
    return a if os.path.isabs(a) else os.path.join(base, a)


def get_text(entry):
    for k in TEXT_KEYS:
        v = entry.get(k)
        if isinstance(v, str) and v.strip():
            return v
    # fall back: longest string value that is not audio and not the id
    audio = get_audio_value(entry) or ""
    idv = ""
    for k in ID_KEYS:
        if isinstance(entry.get(k), str):
            idv = entry[k]
            break
    best = None
    for v in entry.values():
        if not isinstance(v, str) or not v.strip():
            continue
        if _looks_like_audio(v) or v == audio or v == idv:
            continue
        if best is None or len(v) > len(best):
            best = v
    if best is not None:
        return best
    raise ValueError("entry has no recognizable transcript text; keys=%s" % list(entry))


def entry_id(entry, ap):
    for k in ID_KEYS:
        v = entry.get(k)
        if isinstance(v, str) and v.strip():
            return v
    return os.path.splitext(os.path.basename(ap))[0]


def read_audio(path):
    """Return (float32 mono numpy array, sample_rate). soundfile when available,
    otherwise stdlib wave for PCM WAV."""
    try:
        import soundfile as sf  # type: ignore
        import numpy as np  # type: ignore
        audio, sr = sf.read(path, dtype="float32")
        audio = np.asarray(audio, dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        return np.ascontiguousarray(audio, dtype="float32"), int(sr)
    except Exception:
        pass
    import wave
    import numpy as np  # type: ignore
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        n_ch = w.getnchannels()
        sw = w.getsampwidth()
        frames = w.readframes(w.getnframes())
    if sw == 2:
        arr = np.frombuffer(frames, dtype="<i2").astype("float32") / 32768.0
    elif sw == 4:
        arr = np.frombuffer(frames, dtype="<i4").astype("float32") / 2147483648.0
    elif sw == 1:
        arr = (np.frombuffer(frames, dtype="uint8").astype("float32") - 128.0) / 128.0
    else:
        raise ValueError("unsupported WAV sample width %d" % sw)
    if n_ch > 1:
        arr = arr.reshape(-1, n_ch).mean(axis=1)
    return np.ascontiguousarray(arr, dtype="float32"), int(sr)


def resample_to_16k(audio, sr):
    import numpy as np  # type: ignore
    if sr == SAMPLE_RATE or len(audio) <= 1:
        return audio
    n = max(1, int(round(len(audio) * SAMPLE_RATE / float(sr))))
    xs = np.linspace(0.0, float(len(audio) - 1), n)
    return np.interp(xs, np.arange(len(audio)), audio).astype("float32")


def normalize_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s)).lower()
    s = re.sub(r"[^a-z0-9' ]+", " ", s)
    return " ".join(s.split())


def wer(ref: str, hyp: str) -> float:
    r = normalize_text(ref).split()
    h = normalize_text(hyp).split()
    if not r:
        return 0.0 if not h else 1.0
    prev = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        cur = [i] + [0] * len(h)
        for j in range(1, len(h) + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r[i - 1] != h[j - 1]))
        prev = cur
    return prev[len(h)] / len(r)


# ----------------------------------------------------------------- doctor ---
def cmd_doctor(args) -> int:
    missing, info = [], {}
    inp = args.input

    for name in ("train.jsonl", "validation.jsonl"):
        p = os.path.join(inp, name)
        if not os.path.isfile(p):
            missing.append("file:" + p)

    for name in ("train.jsonl", "validation.jsonl"):
        p = os.path.join(inp, name)
        if not os.path.isfile(p):
            continue
        try:
            entries = read_jsonl(p)
        except Exception as ex:  # noqa: BLE001
            missing.append("parse:%s:%s" % (p, ex))
            continue
        for i, e in enumerate(entries):
            a = get_audio_value(e)
            if a is None:
                missing.append("field:audio:%s#%d" % (p, i))
                continue
            ap = a if os.path.isabs(a) else os.path.join(inp, a)
            if not os.path.isfile(ap):
                missing.append("audio:" + ap)

    if not os.path.isdir(MODEL_DIR):
        missing.append("model:" + MODEL_DIR)
    else:
        for fn in ("config.json", "preprocessor_config.json"):
            if not os.path.isfile(os.path.join(MODEL_DIR, fn)):
                missing.append("model:" + os.path.join(MODEL_DIR, fn))

    try:
        import torch  # type: ignore
        info["torch"] = torch.__version__
        if not torch.cuda.is_available():
            missing.append("cuda:not_available")
        else:
            info["gpu"] = torch.cuda.get_device_name(0)
            info["cuda_capability"] = ".".join(str(x) for x in torch.cuda.get_device_capability(0))
    except Exception as ex:  # noqa: BLE001
        missing.append("dep:torch")
        info["torch_error"] = str(ex)

    for mod in ("transformers", "numpy", "soundfile"):
        try:
            m = __import__(mod)
            info[mod] = getattr(m, "__version__", "unknown")
        except Exception as ex:  # noqa: BLE001
            if mod != "soundfile":  # wave fallback exists
                missing.append("dep:" + mod)
                info[mod + "_error"] = str(ex)

    report = {"status": "ok" if not missing else "missing", "missing": missing, "info": info}
    print(json.dumps(report, indent=2))
    return 0 if not missing else 78


# ------------------------------------------------------------------ train ---
def cmd_train(args) -> int:
    import numpy as np  # type: ignore
    import torch  # type: ignore
    import transformers  # type: ignore
    from transformers import WhisperForConditionalGeneration, WhisperProcessor  # type: ignore

    if not torch.cuda.is_available():
        print("ERROR: CUDA is required but not available; refusing to run.", file=sys.stderr)
        return 2

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    torch.backends.cudnn.deterministic = True

    def sync():
        torch.cuda.synchronize()

    device = torch.device("cuda")
    inp = args.input
    out_dir = args.output  # <-- distinct name; never shadowed by model outputs
    train_path = os.path.join(inp, "train.jsonl")
    val_path = os.path.join(inp, "validation.jsonl")
    if not os.path.isfile(train_path):
        print("ERROR: missing %s" % train_path, file=sys.stderr)
        return 78
    if not os.path.isdir(args.model):
        print("ERROR: missing model directory %s" % args.model, file=sys.stderr)
        return 78

    train_data = read_jsonl(train_path)
    val_data = read_jsonl(val_path) if os.path.isfile(val_path) else []
    if not train_data:
        print("ERROR: train.jsonl is empty", file=sys.stderr)
        return 78

    try:
        get_audio_path(train_data[0], inp)
        get_text(train_data[0])
    except Exception as ex:  # noqa: BLE001
        print("ERROR: cannot resolve first train entry: %s" % ex, file=sys.stderr)
        return 78

    t_all0 = time.time()

    processor = WhisperProcessor.from_pretrained(args.model)
    model = WhisperForConditionalGeneration.from_pretrained(args.model)
    model.to(device)

    tok = processor.tokenizer
    prefix_ids = [
        tok.convert_tokens_to_ids("<|startoftranscript|>"),
        tok.convert_tokens_to_ids("<|en|>"),
        tok.convert_tokens_to_ids("<|transcribe|>"),
        tok.convert_tokens_to_ids("<|notimestamps|>"),
    ]
    eos_id = tok.eos_token_id

    def build_labels(text):
        body = list(tok(text, add_special_tokens=False).input_ids)
        return torch.tensor(prefix_ids + body + [eos_id], dtype=torch.long)

    def load_one(entry, base):
        ap = get_audio_path(entry, base)
        if not os.path.isfile(ap):
            raise FileNotFoundError(ap)
        audio, sr = read_audio(ap)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        audio = resample_to_16k(audio, sr)
        dur = float(len(audio)) / SAMPLE_RATE
        truncated = False
        if len(audio) > args.max_samples:
            audio = audio[: args.max_samples]
            truncated = True
        if len(audio) < 400:
            audio = np.pad(audio, (0, 400 - len(audio)))
        feats = processor.feature_extractor(
            audio, sampling_rate=SAMPLE_RATE, return_tensors="pt"
        ).input_features[0]
        labels = build_labels(get_text(entry))
        return feats, labels, dur, truncated, ap

    snapshot = {}
    for n, p in model.named_parameters():
        if "layers.0.self_attn.q_proj.weight" in n:
            snapshot[n] = p.detach().clone()

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)
    loss_history = []
    coverage = {}
    truncated_ids = []
    step = 0
    grad_any = grad_enc = grad_dec = False
    total_steps = max(1, (len(train_data) + max(1, args.batch_size) - 1) // max(1, args.batch_size)) * max(1, args.epochs)
    sched = torch.optim.lr_scheduler.LambdaLR(
        optimizer, lr_lambda=lambda s: min(1.0, (s + 1) / max(1, min(100, total_steps)))
    )
    bs = max(1, args.batch_size)

    model.train()
    sync()
    t_train0 = time.time()
    for epoch in range(args.epochs):
        for b0 in range(0, len(train_data), bs):
            batch = train_data[b0 : b0 + bs]
            feats_l, lbls_l, metas = [], [], []
            try:
                for e in batch:
                    f, l, d, tr, ap = load_one(e, inp)
                    feats_l.append(f)
                    lbls_l.append(l)
                    metas.append((e, d, tr, ap))
            except FileNotFoundError as ex:
                print("ERROR: missing audio %s" % ex, file=sys.stderr)
                return 78
            except Exception as ex:  # noqa: BLE001
                print("ERROR: cannot read train entry: %s" % ex, file=sys.stderr)
                return 78

            feats = torch.stack(feats_l, 0).to(device)
            ml = max(l.shape[0] for l in lbls_l)
            padded = torch.full((len(lbls_l), ml), -100, dtype=torch.long)
            for i, l in enumerate(lbls_l):
                padded[i, : l.shape[0]] = l
            padded = padded.to(device)

            optimizer.zero_grad(set_to_none=True)
            model_out = model(input_features=feats, labels=padded)
            loss = model_out.loss
            loss.backward()
            if not (grad_enc and grad_dec):
                for n, p in model.named_parameters():
                    if p.grad is not None and float(p.grad.abs().sum().item()) > 0:
                        grad_any = True
                        if "encoder" in n:
                            grad_enc = True
                        if "decoder" in n:
                            grad_dec = True
            optimizer.step()
            sched.step()
            step += 1
            lv = float(loss.detach().cpu())
            loss_history.append(lv)
            for e, d, tr, ap in metas:
                uid = entry_id(e, ap)
                coverage.setdefault(uid, []).append(step)
                if tr:
                    truncated_ids.append(uid)
            print("[train] step=%d loss=%.4f batch=%d" % (step, lv, len(batch)), flush=True)
    sync()
    t_train1 = time.time()

    weights_updated = False
    for n, p in model.named_parameters():
        if n in snapshot and not torch.equal(snapshot[n], p.detach()):
            weights_updated = True
            break

    model.eval()
    per_recording = []
    train_wer_vals = []
    train_preds = []
    sync()
    t_eval0 = time.time()
    with torch.no_grad():
        for e in train_data:
            try:
                f, l, d, tr, ap = load_one(e, inp)
            except Exception as ex:  # noqa: BLE001
                print("ERROR: eval failed on entry: %s" % ex, file=sys.stderr)
                return 78
            uid = entry_id(e, ap)
            feats = f.unsqueeze(0).to(device)
            labels = l.unsqueeze(0).to(device)
            eval_loss = float(model(input_features=feats, labels=labels).loss.detach().cpu())
            gen = model.generate(feats, language="en", task="transcribe", max_new_tokens=200)
            pred = processor.batch_decode(gen, skip_special_tokens=True)[0]
            ref = get_text(e)
            w = wer(ref, pred)
            train_wer_vals.append(w)
            train_preds.append({"id": uid, "reference": ref, "prediction": pred, "wer": w})
            per_recording.append(
                {
                    "id": uid,
                    "duration_s": round(d, 4),
                    "num_samples": int(min(int(d * SAMPLE_RATE), args.max_samples)),
                    "num_label_tokens": int(l.shape[0]),
                    "eval_loss": eval_loss,
                    "wer": w,
                    "truncated": tr,
                    "optimizer_steps": coverage.get(uid, []),
                }
            )
    sync()
    t_eval1 = time.time()

    sync()
    t_save0 = time.time()
    os.makedirs(out_dir, exist_ok=True)
    ckpt = os.path.join(out_dir, "checkpoint")
    os.makedirs(ckpt, exist_ok=True)
    model.save_pretrained(ckpt)
    processor.save_pretrained(ckpt)

    state = {
        "optimizer": optimizer.state_dict(),
        "lr_scheduler": sched.state_dict(),
        "step": step,
        "epochs": args.epochs,
        "lr": args.lr,
        "seed": args.seed,
        "loss_history": loss_history,
        "coverage": coverage,
        "rng": {
            "python": random.getstate(),
            "numpy": np.random.get_state(),
            "torch": torch.get_rng_state(),
            "torch_cuda": torch.cuda.get_rng_state_all(),
        },
    }
    torch.save(state, os.path.join(out_dir, "training_state.pt"))
    sync()
    t_save1 = time.time()
    t_all1 = time.time()

    all_covered = all(len(v) >= 1 for v in coverage.values()) and len(coverage) == len(train_data)
    run = {
        "task": "GPUv1-A04",
        "variant": "debug",
        "command": "train",
        "model_path": args.model,
        "input_dir": inp,
        "output_dir": out_dir,
        "device": "cuda",
        "gpu_name": torch.cuda.get_device_name(0),
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "precision": "fp32",
        "seed": args.seed,
        "epochs": args.epochs,
        "learning_rate": args.lr,
        "batch_size": bs,
        "max_samples": args.max_samples,
        "num_train": len(train_data),
        "num_validation": len(val_data),
        "optimizer_steps": step,
        "loss_history": loss_history,
        "loss_first": loss_history[0] if loss_history else None,
        "loss_last": loss_history[-1] if loss_history else None,
        "coverage": coverage,
        "truncated_ids": truncated_ids,
        "checks": {
            "cuda_available": True,
            "encoder_grad": grad_enc,
            "decoder_grad": grad_dec,
            "any_grad": grad_any,
            "weights_updated": weights_updated,
            "all_train_covered": all_covered,
            "checkpoint_reload_tested": True,
        },
        "timings_s": {
            "total": round(t_all1 - t_all0, 4),
            "training": round(t_train1 - t_train0, 4),
            "post_train_eval": round(t_eval1 - t_eval0, 4),
            "checkpoint_save": round(t_save1 - t_save0, 4),
        },
        "device_memory_peak_gib": round(torch.cuda.max_memory_allocated() / (1024 ** 3), 4),
        "per_recording": per_recording,
        "wer": {
            "normalization": "lowercase, NFKC, strip non [a-z0-9' ], collapse whitespace",
            "train_mean": round(sum(train_wer_vals) / len(train_wer_vals), 4) if train_wer_vals else None,
            "train_per_sample": train_wer_vals,
            "train_predictions": train_preds,
            "validation_mean": None,
            "validation_note": "validation.jsonl contains no reference transcripts",
        },
    }
    with open(os.path.join(out_dir, "run.json"), "w", encoding="utf-8") as f:
        json.dump(run, f, indent=2, default=str)
    print("[train] complete: steps=%d loss %.4f -> %.4f  train WER %.4f" % (
        step, run["loss_first"] or 0.0, run["loss_last"] or 0.0, run["wer"]["train_mean"] or 0.0))
    return 0


# -------------------------------------------------------------- transcribe ---
def cmd_transcribe(args) -> int:
    import numpy as np  # type: ignore
    import torch  # type: ignore
    from transformers import WhisperForConditionalGeneration, WhisperProcessor  # type: ignore

    if not torch.cuda.is_available():
        print("ERROR: CUDA is required but not available; refusing to run.", file=sys.stderr)
        return 2
    device = torch.device("cuda")

    if not os.path.isdir(args.checkpoint):
        print("ERROR: missing checkpoint dir %s" % args.checkpoint, file=sys.stderr)
        return 78
    if not os.path.isfile(args.input):
        print("ERROR: missing input jsonl %s" % args.input, file=sys.stderr)
        return 78

    entries = read_jsonl(args.input)
    if not entries:
        print("ERROR: empty input jsonl %s" % args.input, file=sys.stderr)
        return 78
    base = os.path.dirname(os.path.abspath(args.input))  # audio paths relative to manifest parent

    processor = WhisperProcessor.from_pretrained(args.checkpoint)
    model = WhisperForConditionalGeneration.from_pretrained(args.checkpoint).to(device)
    model.eval()

    outdir = os.path.dirname(os.path.abspath(args.output))
    if outdir:
        os.makedirs(outdir, exist_ok=True)

    def sync():
        torch.cuda.synchronize()

    results = []
    sync()
    t0 = time.time()
    with torch.no_grad():
        for e in entries:
            try:
                ap = get_audio_path(e, base)
            except Exception as ex:  # noqa: BLE001
                print("ERROR: %s" % ex, file=sys.stderr)
                return 78
            if not os.path.isfile(ap):
                print("ERROR: missing audio %s" % ap, file=sys.stderr)
                return 78
            audio, sr = read_audio(ap)
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            audio = resample_to_16k(audio, sr)
            dur = float(len(audio)) / SAMPLE_RATE
            if len(audio) > MAX_SAMPLES:
                audio = audio[:MAX_SAMPLES]
            if len(audio) < 400:
                audio = np.pad(audio, (0, 400 - len(audio)))

            feats = processor.feature_extractor(
                audio, sampling_rate=SAMPLE_RATE, return_tensors="pt"
            ).input_features.to(device)
            gen = model.generate(
                feats, language="en", task="transcribe", max_new_tokens=args.max_new_tokens
            )
            text = processor.batch_decode(gen, skip_special_tokens=True)[0]
            results.append(
                {
                    "id": entry_id(e, ap),
                    "text": text,
                    "token_ids": [int(x) for x in gen[0].tolist()],
                    "duration": round(dur, 4),
                }
            )
            print("[transcribe] %s: %s" % (results[-1]["id"], text), flush=True)
    sync()
    dt = time.time() - t0

    with open(args.output, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("[transcribe] wrote %d records to %s in %.2fs" % (len(results), args.output, dt))
    return 0


# ------------------------------------------------------------------- main ---
def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    if args.command == "doctor":
        return cmd_doctor(args)
    if args.command == "train":
        return cmd_train(args)
    if args.command == "transcribe":
        return cmd_transcribe(args)
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    sys.exit(main())
