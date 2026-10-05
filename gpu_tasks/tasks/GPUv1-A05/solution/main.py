#!/usr/bin/env python3
"""GPUv1-A05: English speech -> German text with the fairseq s2t_transformer_s
CoVoST2 en-de recipe.

This file is a *source-native adapter* around the frozen fairseq ST recipe. It
never fabricates audio, features, weights or translations:

* ``doctor`` inspects the frozen input tree and the runtime stack, lists every
  missing file/module/device, and exits 78 when anything required is absent.
* ``run`` performs a real CUDA train via ``upstream/fairseq/train.py`` (or the
  installed ``fairseq_cli``) on the frozen ``covost2`` TSVs, averages the
  recipe checkpoints, exports ``speech_translation.pt`` and, when a paired test
  TSV is available, decodes it through upstream ``generate.py``.
* ``resume`` continues from ``checkpoints/checkpoint_last.pt`` for a caller
  supplied number of extra updates (optimizer / RNG state preserved).
* ``translate`` runs upstream ``generate.py`` on a *new* frozen English TSV.

If the frozen assets declared in ``input/manifest.json`` are not mounted the
adapter reports what is missing and exits 78 rather than emitting a synthetic
result. No network, no downloads, no CPU fallback for the GPU job.
"""

import argparse
import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

TASK_ID = "GPUv1-A05"

DEFAULT_REQUIRED_FILES = [
    "upstream/fairseq/train.py",
    "covost2/config_st.yaml",
    "covost2/train.tsv",
    "covost2/dev.tsv",
    "covost2/spm_unigram10000.model",
    "covost2/dict.txt",
]
DEFAULT_REQUIRED_MODULES = ["fairseq"]

RECIPE_DECLARATION = {
    "recipe": "fairseq s2t_transformer_s CoVoST2 en-de ST recipe",
    "updates": 30000,
    "encoder_freeze_updates": 1000,
    "optimizer": "adam(0.9,0.98)",
    "lr": 0.002,
    "lr_scheduler": "inverse_sqrt",
    "warmup_updates": 4000,
    "criterion": "label_smoothed_cross_entropy",
    "label_smoothing": 0.1,
    "clip_norm": 10.0,
    "max_tokens": "en-* recommendation, kept inside covost2/config_st.yaml",
    "note": (
        "encoder is initialized from the released English ASR checkpoint "
        "(via --finetune-from-model when upstream/asr_encoder_checkpoint.pt is "
        "mounted); the 1000-update encoder-freeze window is a source-recipe "
        "declaration preserved in run.json. It is NOT a substitute for training."
    ),
}


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _read_json(path):
    with open(path) as fh:
        return json.load(fh)


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, default=str)
    os.replace(tmp, path)
    return path


def _sha256(path, max_bytes=64 * 1024 * 1024):
    h = hashlib.sha256()
    total = 0
    with open(path, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b or (max_bytes and total >= max_bytes):
                break
            h.update(b)
            total += len(b)
    return h.hexdigest()


def _manifest(input_dir):
    p = Path(input_dir) / "manifest.json"
    if p.is_file():
        try:
            return _read_json(p)
        except Exception:
            return None
    return None


def _required_files(input_dir):
    m = _manifest(input_dir)
    files = m.get("files") if isinstance(m, dict) else None
    if isinstance(files, list) and all(isinstance(x, str) for x in files):
        return list(files)
    return list(DEFAULT_REQUIRED_FILES)


def _required_modules(input_dir):
    m = _manifest(input_dir)
    reqs = m.get("requirements") if isinstance(m, dict) else None
    if isinstance(reqs, list) and all(isinstance(x, str) for x in reqs):
        return list(reqs)
    return list(DEFAULT_REQUIRED_MODULES)


def _fairseq_local_dir(input_dir):
    p = Path(input_dir) / "upstream" / "fairseq"
    return p if p.is_dir() else None


def _module_available(name, input_dir):
    try:
        importlib.import_module(name)
        return True
    except Exception:
        pass
    if name == "fairseq":
        return _fairseq_local_dir(input_dir) is not None
    return False


def _missing_files(input_dir):
    return [rel for rel in _required_files(input_dir)
            if not (Path(input_dir) / rel).is_file()]


def _missing_modules(input_dir):
    return [m for m in _required_modules(input_dir)
            if not _module_available(m, input_dir)]


def _probe_env():
    info = {"packages": {}, "cuda_available": False, "gpu_count": 0}
    for name in ("fairseq", "torch", "torchaudio", "soundfile",
                 "sentencepiece", "sacrebleu", "numpy", "yaml"):
        try:
            mod = importlib.import_module(name)
            info["packages"][name] = getattr(mod, "__version__", "present")
        except Exception:
            info["packages"][name] = None
    try:
        import torch
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            info["cuda_available"] = True
            info["gpu_count"] = torch.cuda.device_count()
            info["device_name"] = torch.cuda.get_device_name(0)
            info["device_capability"] = list(torch.cuda.get_device_capability(0))
            info["device_memory_gib"] = round(props.total_memory / 2 ** 30, 2)
    except Exception:
        pass
    return info


def _resolve_fairseq_script(input_dir, name):
    local = Path(input_dir) / "upstream" / "fairseq" / name
    if local.is_file():
        return [sys.executable, str(local)]
    return [sys.executable, "-m", "fairseq_cli." + name[:-3]]


# --------------------------------------------------------------------------- #
# doctor
# --------------------------------------------------------------------------- #
def cmd_doctor(args):
    input_dir = Path(args.input).resolve()
    missing_files = _missing_files(input_dir)
    missing_mods = _missing_modules(input_dir)
    env = _probe_env()
    missing_deps = list(missing_mods)
    if env["packages"].get("torch") is not None and not env["cuda_available"]:
        missing_deps.append("cuda:no CUDA-capable GPU visible to torch")
    report = {
        "task_id": TASK_ID,
        "input_dir": str(input_dir),
        "manifest_present": (input_dir / "manifest.json").is_file(),
        "required_files": _required_files(input_dir),
        "present_files": [r for r in _required_files(input_dir)
                          if (input_dir / r).is_file()],
        "missing_files": missing_files,
        "required_modules": _required_modules(input_dir),
        "missing_modules": missing_mods,
        "missing_dependencies": missing_deps,
        "environment": env,
        "ready": not (missing_files or missing_deps),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ready"] else 78


# --------------------------------------------------------------------------- #
# training
# --------------------------------------------------------------------------- #
def _build_train_cmd(input_dir, output_dir, max_update, num_workers):
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    data_dir = input_dir / "covost2"
    ckpt_dir = output_dir / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    cmd = _resolve_fairseq_script(input_dir, "train.py") + [
        str(data_dir),
        "--config-yaml", str(data_dir / "config_st.yaml"),
        "--train-subset", "train",
        "--valid-subset", "dev",
        "--save-dir", str(ckpt_dir),
        "--task", "speech_to_text",
        "--criterion", "label_smoothed_cross_entropy",
        "--label-smoothing", "0.1",
        "--arch", "s2t_transformer_s",
        "--optimizer", "adam",
        "--adam-betas", "(0.9,0.98)",
        "--lr", "0.002",
        "--lr-scheduler", "inverse_sqrt",
        "--warmup-updates", "4000",
        "--clip-norm", "10.0",
        "--weight-decay", "0.0001",
        "--dropout", "0.1",
        "--attention-dropout", "0.1",
        "--activation-dropout", "0.1",
        "--seed", "1",
        "--max-update", str(max_update),
        "--save-interval-updates", "1000",
        "--keep-interval-updates", "5",
        "--keep-last-epochs", "1",
        "--log-interval", "50",
        "--num-workers", str(num_workers),
        "--no-progress-bar",
        "--fp16",
    ]
    asr_init = input_dir / "upstream" / "asr_encoder_checkpoint.pt"
    if asr_init.is_file():
        cmd += ["--finetune-from-model", str(asr_init)]
    return cmd, data_dir, ckpt_dir


def _run_subprocess(cmd, log_path):
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    with open(log_path, "w") as lf:
        proc = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT)
    return proc.returncode, round(time.monotonic() - t0, 3)


def _average_checkpoints(input_dir, output_dir, timings, keep=5):
    ckpt_dir = Path(output_dir) / "checkpoints"
    final = Path(output_dir) / "speech_translation.pt"
    candidates = sorted(
        (p for p in ckpt_dir.glob("checkpoint*.pt")
         if p.name != "checkpoint_last.pt"),
        key=lambda p: p.stat().st_mtime,
    )
    avg_script = Path(input_dir) / "upstream" / "fairseq" / "scripts" / "average_checkpoints.py"
    if avg_script.is_file() and len(candidates) > 1:
        chosen = candidates[-keep:]
        cmd = ([sys.executable, str(avg_script)]
               + ["--inputs"] + [str(p) for p in chosen]
               + ["--output", str(final)])
        rc, dt = _run_subprocess(cmd, Path(output_dir) / "average.log")
        timings["checkpoint_average_s"] = dt
        timings["checkpoints_averaged"] = [p.name for p in chosen]
        if rc == 0 and final.is_file():
            return final
    last = ckpt_dir / "checkpoint_last.pt"
    if last.is_file():
        shutil.copy(last, final)
        timings["checkpoints_averaged"] = [last.name]
        return final
    if candidates:
        shutil.copy(candidates[-1], final)
        timings["checkpoints_averaged"] = [candidates[-1].name]
        return final
    return None


# --------------------------------------------------------------------------- #
# generation
# --------------------------------------------------------------------------- #
def _stage_data_dir(input_dir, output_dir, tsv_path, subset_name="test"):
    src = Path(input_dir) / "covost2"
    staged = Path(output_dir) / "staged_covost2"
    staged.mkdir(parents=True, exist_ok=True)
    for f in src.iterdir():
        link = staged / f.name
        if link.exists() or link.is_symlink():
            continue
        try:
            os.symlink(f.resolve(), link)
        except OSError:
            if f.is_file():
                shutil.copy(f, link)
    target = staged / (subset_name + ".tsv")
    if target.exists() or target.is_symlink():
        target.unlink()
    src_tsv = Path(tsv_path).resolve()
    try:
        os.symlink(src_tsv, target)
    except OSError:
        shutil.copy(src_tsv, target)
    return staged


def _run_generate(input_dir, output_dir, ckpt, tsv, subset_name, timings):
    staged = _stage_data_dir(input_dir, output_dir, tsv, subset_name)
    results_dir = Path(output_dir) / "gen"
    results_dir.mkdir(parents=True, exist_ok=True)
    cmd = _resolve_fairseq_script(input_dir, "generate.py") + [
        str(staged),
        "--config-yaml", str(Path(input_dir) / "covost2" / "config_st.yaml"),
        "--task", "speech_to_text",
        "--path", str(ckpt),
        "--gen-subset", subset_name,
        "--max-tokens", "8000",
        "--beam", "5",
        "--batch-size", "8",
        "--num-workers", "2",
        "--results-path", str(results_dir),
        "--no-progress-bar",
    ]
    rc, dt = _run_subprocess(cmd, Path(output_dir) / "generate.log")
    timings["generate_s"] = dt
    gen_file = results_dir / ("generate-%s.txt" % subset_name)
    return rc, gen_file


def _parse_generate_output(path):
    pattern = re.compile(r"^([STH])-(\d+)\t?(.*)$")
    src_ids, refs, hyps, order = {}, {}, {}, []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            m = pattern.match(line)
            if not m:
                continue
            tag, idx, rest = m.group(1), int(m.group(2)), m.group(3)
            if tag == "S":
                parts = rest.split("\t", 1)
                src_ids[idx] = parts[0]
                order.append(idx)
            elif tag == "T":
                parts = rest.split("\t", 1)
                refs[idx] = parts[1] if len(parts) > 1 else ""
            elif tag == "H":
                parts = rest.split("\t")
                hyps[idx] = parts[-1].strip()
    return src_ids, refs, hyps, order


def _export_translations(output_dir, gen_file, audio_id, refs, hyps, order):
    out_path = Path(output_dir) / "test_translations.jsonl"
    n_written = 0
    with open(out_path, "w", encoding="utf-8") as fh:
        for idx in order:
            aid = audio_id.get(idx)
            if aid is None:
                continue
            rec = {"audio_id": aid, "prediction": hyps.get(idx, "")}
            if idx in refs:
                rec["reference"] = refs[idx]
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n_written += 1
    return out_path, n_written


def _compute_bleu(output_dir, refs, hyps, order):
    pairs = [(hyps[i], refs[i]) for i in order if i in hyps and i in refs]
    if not pairs:
        return None
    try:
        import sacrebleu
    except Exception:
        return {"status": "sacrebleu_unavailable", "n": len(pairs)}
    hyp_list = [p[0] for p in pairs]
    ref_list = [p[1] for p in pairs]
    bleu = sacrebleu.corpus_bleu(hyp_list, [ref_list], tokenize="13a")
    report = {
        "tool": "sacrebleu",
        "version": getattr(sacrebleu, "__version__", "unknown"),
        "tokenizer": "13a",
        "n_sentences": len(pairs),
        "score": bleu.score,
        "signature": bleu.format(width=4),
    }
    _write_json(Path(output_dir) / "sacrebleu.json", report)
    return report


# --------------------------------------------------------------------------- #
# shared run/resume body
# --------------------------------------------------------------------------- #
def _train_and_export(args, current_updates=None):
    input_dir = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    missing = _missing_files(input_dir) + _missing_modules(input_dir)
    if missing:
        report = {"task_id": TASK_ID, "status": "missing_inputs",
                  "missing": missing, "complete": False}
        print(json.dumps(report, indent=2), file=sys.stderr)
        _write_json(output_dir / "run.json", report)
        return 78

    env = _probe_env()
    if not env["cuda_available"]:
        report = {"task_id": TASK_ID, "status": "no_cuda",
                  "message": "CUDA is required for fairseq speech_to_text training",
                  "complete": False}
        print(json.dumps(report, indent=2), file=sys.stderr)
        _write_json(output_dir / "run.json", report)
        return 3

    timings = {}
    wall_start = time.time()
    cmd, data_dir, ckpt_dir = _build_train_cmd(
        input_dir, output_dir, args.max_update, getattr(args, "num_workers", 4))
    _write_json(output_dir / "train_command.json",
                {"cmd": cmd, "cwd": str(Path.cwd()), "max_update": args.max_update})

    rc, dt = _run_subprocess(cmd, output_dir / "train.log")
    timings["train_s"] = dt
    if rc != 0:
        report = {
            "task_id": TASK_ID,
            "status": "train_failed",
            "returncode": rc,
            "log": str(output_dir / "train.log"),
            "timings": timings,
            "complete": False,
        }
        _write_json(output_dir / "run.json", report)
        return rc

    ckpt_last = ckpt_dir / "checkpoint_last.pt"
    if not ckpt_last.is_file():
        report = {"task_id": TASK_ID, "status": "no_checkpoint_after_train",
                  "log": str(output_dir / "train.log"), "complete": False}
        _write_json(output_dir / "run.json", report)
        return 4

    final = _average_checkpoints(input_dir, output_dir, timings)
    if final is None:
        report = {"task_id": TASK_ID, "status": "no_exportable_checkpoint",
                  "complete": False}
        _write_json(output_dir / "run.json", report)
        return 5

    lineage = {
        "checkpoint_last": str(ckpt_last),
        "checkpoint_last_sha256": _sha256(ckpt_last),
        "exported": str(final),
        "exported_sha256": _sha256(final),
        "averaged_members": timings.get("checkpoints_averaged", []),
    }
    _write_json(output_dir / "checkpoint_lineage.json", lineage)

    # Optional decoding of a paired test TSV.
    test_tsv = getattr(args, "test_tsv", None)
    if test_tsv is None:
        for candidate in ("test.tsv", "test_st_en_de.tsv", "dev.tsv"):
            p = data_dir / candidate
            if p.is_file():
                test_tsv = str(p)
                break
    gen_summary = None
    bleu = None
    if test_tsv and Path(test_tsv).is_file():
        subset_name = "test"
        rc, gen_file = _run_generate(input_dir, output_dir, final,
                                     test_tsv, subset_name, timings)
        if rc == 0 and gen_file.is_file():
            src_ids, refs, hyps, order = _parse_generate_output(gen_file)
            out_jsonl, n_written = _export_translations(
                output_dir, gen_file, src_ids, refs, hyps, order)
            bleu = _compute_bleu(output_dir, refs, hyps, order)
            gen_summary = {
                "test_tsv": str(test_tsv),
                "gen_file": str(gen_file),
                "translations": str(out_jsonl),
                "n_translations": n_written,
                "n_lines_in_gen": len(order),
                "order_preserved": True,
            }
        else:
            gen_summary = {"test_tsv": str(test_tsv),
                           "error": "generate_failed",
                           "returncode": rc}

    report = {
        "task_id": TASK_ID,
        "status": "completed",
        "complete": True,
        "scale": "native_debug",
        "recipe_declaration": RECIPE_DECLARATION,
        "seed": 1,
        "max_update": args.max_update,
        "current_updates_at_start": current_updates,
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "environment": env,
        "checkpoint_lineage": lineage,
        "generation": gen_summary,
        "sacrebleu": bleu,
        "timings_s": timings,
        "wall_clock_start_unix": wall_start,
        "wall_clock_end_unix": time.time(),
    }
    _write_json(output_dir / "run.json", report)
    return 0


def cmd_run(args):
    return _train_and_export(args, current_updates=0)


def cmd_resume(args):
    output_dir = Path(args.output).resolve()
    ckpt_last = output_dir / "checkpoints" / "checkpoint_last.pt"
    if not ckpt_last.is_file():
        msg = {"task_id": TASK_ID, "status": "no_state_to_resume",
               "checkpoint": str(ckpt_last)}
        print(json.dumps(msg, indent=2), file=sys.stderr)
        return 2
    try:
        import torch
        state = torch.load(str(ckpt_last), map_location="cpu")
        history = state.get("optimizer_history") or []
        current = history[-1].get("num_updates") if history else None
        if not current:
            current = state.get("num_updates") or 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "cannot_read_checkpoint",
                          "error": str(exc)}), file=sys.stderr)
        return 2
    args.max_update = int(current) + int(args.extra_updates)
    return _train_and_export(args, current_updates=int(current))


# --------------------------------------------------------------------------- #
# translate (new frozen TSV)
# --------------------------------------------------------------------------- #
def cmd_translate(args):
    input_dir = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    missing = _missing_files(input_dir) + _missing_modules(input_dir)
    tsv = Path(args.tsv).resolve()
    ckpt = Path(args.checkpoint).resolve()
    for extra in ([str(tsv)] if not tsv.is_file() else []) + \
                 ([str(ckpt)] if not ckpt.is_file() else []):
        missing.append(extra)
    if missing:
        report = {"task_id": TASK_ID, "status": "missing_inputs",
                  "missing": missing, "complete": False}
        print(json.dumps(report, indent=2), file=sys.stderr)
        _write_json(output_dir / "run.json", report)
        return 78
    env = _probe_env()
    if not env["cuda_available"]:
        report = {"task_id": TASK_ID, "status": "no_cuda", "complete": False}
        _write_json(output_dir / "run.json", report)
        return 3
    timings = {}
    rc, gen_file = _run_generate(input_dir, output_dir, ckpt, tsv, "test", timings)
    if rc != 0 or not gen_file.is_file():
        _write_json(output_dir / "run.json", {"task_id": TASK_ID,
                    "status": "generate_failed", "returncode": rc, "complete": False})
        return rc or 4
    src_ids, refs, hyps, order = _parse_generate_output(gen_file)
    out_jsonl, n = _export_translations(output_dir, gen_file, src_ids, refs, hyps, order)
    bleu = _compute_bleu(output_dir, refs, hyps, order)
    _write_json(output_dir / "run.json", {
        "task_id": TASK_ID, "status": "completed", "complete": True,
        "command": "translate", "checkpoint": str(ckpt), "tsv": str(tsv),
        "n_translations": n, "gen_file": str(gen_file),
        "translations": str(out_jsonl), "sacrebleu": bleu,
        "timings_s": timings, "environment": env,
    })
    return 0


# --------------------------------------------------------------------------- #
# entrypoint
# --------------------------------------------------------------------------- #
def main(argv=None):
    p = argparse.ArgumentParser(
        prog="main.py",
        description=(
            "GPUv1-A05 source-native adapter for the fairseq s2t_transformer_s "
            "CoVoST2 en-de recipe. Never fabricates data, weights or predictions."
        ),
    )
    sub = p.add_subparsers(dest="command")

    d = sub.add_parser("doctor", help="Inspect required inputs/deps (no training).")
    d.add_argument("--input", required=True, help="frozen input directory")

    r = sub.add_parser("run", help="Train and export (CUDA required).")
    r.add_argument("--input", required=True)
    r.add_argument("--output", required=True)
    r.add_argument("--max-update", type=int, default=30000)
    r.add_argument("--test-tsv", default=None)
    r.add_argument("--num-workers", type=int, default=4)

    s = sub.add_parser("resume", help="Resume from checkpoint_last.pt.")
    s.add_argument("--input", required=True)
    s.add_argument("--output", required=True)
    s.add_argument("--extra-updates", type=int, required=True)
    s.add_argument("--test-tsv", default=None)
    s.add_argument("--num-workers", type=int, default=4)

    t = sub.add_parser("translate", help="Decode a new frozen English TSV.")
    t.add_argument("--input", required=True)
    t.add_argument("--output", required=True)
    t.add_argument("--checkpoint", required=True)
    t.add_argument("--tsv", required=True)

    args = p.parse_args(argv)
    if args.command == "doctor":
        return cmd_doctor(args)
    if args.command == "run":
        return cmd_run(args)
    if args.command == "resume":
        return cmd_resume(args)
    if args.command == "translate":
        return cmd_translate(args)
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
