#!/usr/bin/env python3
"""
GPUv1-F03: source-native OpenFold CUDA adapter for CASP14 long-target
structure prediction (model_1_ptm, model_1_ptm config preset).

Subcommands
-----------
  doctor --input INPUT_DIR [--output OUT_DIR]
        Inspect the declared prerequisite files/modules and CUDA availability.
        Exit 0 if everything is present, 78 if anything is missing.
        Nothing is trained or predicted during doctor.

  run    --input INPUT_DIR --output OUT_DIR [--resume] [--gpus N]
        Verify inputs first; refuse to spawn OpenFold unless every declared
        file and module (and CUDA) is available.  Then run native OpenFold
        model_1_ptm inference per target on GPU and write PDBs, per-target
        metadata, run_state.json (resumable) and run.json.

  --help Show this help.  No torch/openfold import happens on --help.

A missing-input report from `doctor`/`run` is NOT a solved task; assets are
never fabricated and CPU substitution is never used for the GPU workload.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REQUIRED_FILES = [
    "upstream/openfold/run_pretrained_openfold.py",
    "model_1_ptm.pt",
    "targets.fasta",
    "alignments",
]
# Import-module names per the frozen contract (Bio, not "biopython").
REQUIRED_MODULES = ["openfold", "Bio"]
TARGETS = ["H1044", "T1050", "T1052", "T1053", "T1061"]
TARGET_LENGTHS = {"H1044": 2180, "T1050": 779, "T1052": 832, "T1053": 580, "T1061": 949}
MAX_TEMPLATE_DATE = "2021-05-01"  # frozen CASP14 template cutoff


# ------------------------- small utilities ---------------------------------
def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def module_found(name):
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def cuda_available():
    try:
        import torch  # noqa: WPS433
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def cuda_describe():
    try:
        import torch  # noqa: WPS433
        if not torch.cuda.is_available():
            return None
        i = torch.cuda.current_device()
        p = torch.cuda.get_device_properties(i)
        return {
            "index": i,
            "name": p.name,
            "total_mem_gib": round(p.total_memory / 2 ** 30, 2),
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
        }
    except Exception as exc:  # pragma: no cover
        return {"error": repr(exc)}


def read_fasta(path):
    seqs, name, buf = {}, None, []
    with open(path) as fh:
        for line in fh:
            line = line.rstrip()
            if line.startswith(">"):
                if name is not None:
                    seqs[name] = "".join(buf)
                name = line[1:].split()[0]
                buf = []
            elif line:
                buf.append(line)
    if name is not None:
        seqs[name] = "".join(buf)
    return seqs


def write_fasta(path, name, seq):
    with open(path, "w") as fh:
        fh.write(">{0}\n".format(name))
        for i in range(0, len(seq), 60):
            fh.write(seq[i:i + 60] + "\n")


# ------------------------------- doctor ------------------------------------
def inspect_input(input_dir: Path) -> dict:
    rep = {
        "input_dir": str(input_dir),
        "present_files": {},
        "missing_files": [],
        "present_modules": [],
        "missing_modules": [],
        "cuda": False,
        "cuda_info": None,
    }
    for rel in REQUIRED_FILES:
        p = input_dir / rel
        if p.exists():
            entry = {"path": str(p), "is_dir": p.is_dir()}
            if p.is_file():
                entry["size_bytes"] = p.stat().st_size
                entry["sha256"] = sha256_file(p)
            rep["present_files"][rel] = entry
        else:
            rep["missing_files"].append(rel)
    for m in REQUIRED_MODULES:
        (rep["present_modules"] if module_found(m) else rep["missing_modules"]).append(m)
    rep["cuda"] = cuda_available()
    rep["cuda_info"] = cuda_describe()
    return rep


def print_report(rep: dict):
    print("input dir       :", rep["input_dir"])
    print("CUDA available  :", rep["cuda"])
    if rep.get("cuda_info"):
        print("CUDA info       :", json.dumps(rep["cuda_info"]))
    print("required files  :")
    for rel in REQUIRED_FILES:
        if rel in rep["present_files"]:
            e = rep["present_files"][rel]
            extra = "dir" if e["is_dir"] else "{0} bytes sha256={1}...".format(e["size_bytes"], e["sha256"][:16])
            print("  [OK]      {0}  ({1})".format(rel, extra))
        else:
            print("  [MISSING] {0}".format(rel))
    print("required modules:")
    for m in REQUIRED_MODULES:
        ok = m in rep["present_modules"]
        print("  [{0}] {1}".format("OK" if ok else "MISSING", m))
    if rep["missing_files"] or rep["missing_modules"]:
        print("RESULT: MISSING PREREQUISITES - task cannot proceed (exit 78).")
    else:
        print("RESULT: all prerequisites present (exit 0).")


def cmd_doctor(args) -> int:
    rep = inspect_input(Path(args.input).resolve())
    rep["command"] = "doctor"
    missing = bool(rep["missing_files"] or rep["missing_modules"])
    rep["exit_code"] = 78 if missing else 0
    print_report(rep)
    if getattr(args, "output", None):
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "doctor_report.json").write_text(json.dumps(rep, indent=2))
        print("wrote", out / "doctor_report.json")
    return rep["exit_code"]


# --------------------------------- run -------------------------------------
def build_openfold_command(input_dir: Path, fasta: Path, out_dir: Path):
    """Full native OpenFold invocation with actual checkpoint + frozen alignments."""
    align = input_dir / "alignments"
    return [
        sys.executable,
        str(input_dir / "upstream" / "openfold" / "run_pretrained_openfold.py"),
        "--fasta_paths", str(fasta),
        "--openfold_checkpoint_path", str(input_dir / "model_1_ptm.pt"),
        "--output_dir", str(out_dir),
        "--model_device", "cuda:0",
        "--config_preset", "model_1_ptm",
        "--use_precomputed_alignments", str(align),
        "--max_template_date", MAX_TEMPLATE_DATE,
    ]


def cmd_run(args) -> int:
    input_dir = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()

    rep = inspect_input(input_dir)
    if rep["missing_files"] or rep["missing_modules"]:
        print("REFUSING TO RUN: declared prerequisites missing:")
        for m in rep["missing_files"]:
            print("  missing file   :", m)
        for m in rep["missing_modules"]:
            print("  missing module :", m)
        print("OpenFold subprocess was NOT spawned.  Missing-input report is NOT a solved task.")
        return 78
    if not rep["cuda"]:
        print("REFUSING TO RUN: torch.cuda.is_available() is False; GPU is required.")
        return 3

    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir = output_dir / "work"
    work_dir.mkdir(exist_ok=True)

    seqs = read_fasta(input_dir / "targets.fasta")
    state_path = output_dir / "run_state.json"
    state = {"targets": {}, "created_utc": time.time()}
    if args.resume and state_path.exists():
        state = json.loads(state_path.read_text())
        print("resume: loaded {0} with {1}".format(state_path, list(state["targets"])))

    results = {
        "task_id": "GPUv1-F03",
        "backend": "openfold.model_1_ptm",
        "template_cutoff": MAX_TEMPLATE_DATE,
        "cuda_info": rep["cuda_info"],
        "targets": {},
        "started_utc": time.time(),
    }
    env = os.environ.copy()
    if getattr(args, "gpus", None):
        env["CUDA_VISIBLE_DEVICES"] = str(args.gpus)

    for target in TARGETS:
        if target not in seqs:
            print("WARN: target {0} not found in targets.fasta".format(target))
            continue
        seq = seqs[target]
        exp_len = TARGET_LENGTHS.get(target)
        if exp_len is not None and len(seq) != exp_len:
            print("ERROR: target {0} length {1} != expected {2}".format(target, len(seq), exp_len))
            return 4

        tdir = output_dir / target
        tdir.mkdir(exist_ok=True)
        tfa = work_dir / "{0}.fasta".format(target)
        write_fasta(tfa, target, seq)

        prev = state["targets"].get(target)
        if args.resume and prev and prev.get("status") == "ok" and prev.get("pdb") and Path(prev["pdb"]).exists():
            print("resume: skipping completed target", target)
            results["targets"][target] = prev
            continue

        cmd = build_openfold_command(input_dir, tfa, tdir)
        print("running:", " ".join(cmd))
        t0 = time.time()
        proc = subprocess.run(cmd, env=env)
        dt = time.time() - t0
        entry = {
            "status": "ok" if proc.returncode == 0 else "failed",
            "returncode": proc.returncode,
            "wall_s": round(dt, 3),
            "n_residues": len(seq),
            "pdb": None,
            "pdb_sha256": None,
        }
        if proc.returncode != 0:
            print("OpenFold failed for {0} (rc={1})".format(target, proc.returncode))
            state["targets"][target] = entry
            state_path.write_text(json.dumps(state, indent=2))
            results["targets"][target] = entry
            results["finished_utc"] = time.time()
            (output_dir / "run.json").write_text(json.dumps(results, indent=2))
            return 5

        pdbs = sorted(tdir.glob("*.pdb"))
        if not pdbs:
            print("no PDB produced for", target)
            entry["status"] = "missing_output"
            state["targets"][target] = entry
            state_path.write_text(json.dumps(state, indent=2))
            results["targets"][target] = entry
            results["finished_utc"] = time.time()
            (output_dir / "run.json").write_text(json.dumps(results, indent=2))
            return 5

        entry["pdb"] = str(pdbs[0])
        entry["pdb_sha256"] = sha256_file(pdbs[0])
        state["targets"][target] = entry
        state_path.write_text(json.dumps(state, indent=2))
        results["targets"][target] = entry
        print("target {0} done in {1:.1f}s -> {2}".format(target, dt, pdbs[0]))

    results["finished_utc"] = time.time()
    results["wall_s"] = round(results["finished_utc"] - results["started_utc"], 3)
    (output_dir / "run.json").write_text(json.dumps(results, indent=2))
    print("all targets completed; run.json written to", output_dir / "run.json")
    return 0


# ------------------------------- argparse ----------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="main.py",
        description="GPUv1-F03 OpenFold model_1_ptm CUDA structure-prediction adapter",
    )
    sub = p.add_subparsers(dest="command")

    d = sub.add_parser("doctor", help="inspect declared inputs without running inference")
    d.add_argument("--input", required=True)
    d.add_argument("--output", default=None)
    d.set_defaults(func=cmd_doctor)

    r = sub.add_parser("run", help="run native OpenFold CUDA inference")
    r.add_argument("--input", required=True)
    r.add_argument("--output", required=True)
    r.add_argument("--resume", action="store_true")
    r.add_argument("--gpus", default=None)
    r.set_defaults(func=cmd_run)
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
