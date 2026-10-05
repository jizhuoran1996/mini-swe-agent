# GPUv1-F03 — OpenFold model_1_ptm long-target structure prediction adapter

Source-native adapter that drives the official OpenFold
`run_pretrained_openfold.py` with the `model_1_ptm` config preset and
`model_1_ptm.pt` weights on CUDA for the CASP14 long targets
`H1044 (2180 aa), T1050 (779), T1052 (832), T1053 (580), T1061 (949)`.

## Entry points

```
python solution/main.py --help
python solution/main.py doctor --input input [--output output]
python solution/main.py run    --input input --output output [--resume] [--gpus 0]
```

- `--help` never imports torch/openfold; it is a pure CLI availability check.
- `doctor` inspects the readonly `input/` for the exact set of declared
  prerequisite files, module imports and CUDA availability.  It performs no
  training and no inference.  It exits `78` if any required file or module is
  missing (or CUDA is unavailable) and `0` if everything is present.  When
  `--output` is supplied it writes `output/doctor_report.json`.
- `run` re-verifies prerequisites first and **refuses to spawn OpenFold** if
  anything is missing or if CUDA is unavailable.  It then runs the native
  checkpoint per target, writing `output/<TARGET>/<TARGET>.pdb`, `run_state.json`
  (resumable) and `output/run.json`.

## Required inputs (per `input/manifest.json`, read-only)

- `upstream/openfold/run_pretrained_openfold.py`
- `model_1_ptm.pt`
- `targets.fasta` (five CASP14 targets)
- `alignments/` (frozen MSA / template hits, template cutoff `2021-05-01`)

Python import modules (per the frozen contract/manifest): `openfold`, `Bio`
(provided by the Biopython distribution; the import name is `Bio`, not
`biopython`).

## GPU invocation

For each target the adapter writes a per-target FASTA and invokes:

```
python input/upstream/openfold/run_pretrained_openfold.py \
    --fasta_paths output/work/<TARGET>.fasta \
    --openfold_checkpoint_path input/model_1_ptm.pt \
    --output_dir output/<TARGET> \
    --model_device cuda:0 \
    --config_preset model_1_ptm \
    --use_precomputed_alignments input/alignments \
    --max_template_date 2021-05-01
```

`CUDA_VISIBLE_DEVICES` is set from `--gpus` when provided.  Per-target return
code, wall-clock time and PDB SHA256 are recorded in `run_state.json` and
`run.json`; the sequence length is validated against the declared length before
the subprocess runs, so shorter substitutes cannot silently stand in for the
full chain.

## Resume

`run --resume` reloads `output/run_state.json` and skips any target already
recorded with `status == ok` whose PDB still exists and is unchanged.

## Honest limitations / readiness of this container

This container's readonly `input/` currently contains only `manifest.json`.
The declared assets (`model_1_ptm.pt`, `targets.fasta`, `alignments/`,
`upstream/openfold/...`) and modules (`openfold`, `Bio`) are **not mounted**,
so `doctor` reports them as missing and exits `78`, and `run` refuses to spawn
the OpenFold job.  That missing-input report is explicitly NOT a solved task:

- No fake sequences, fake alignments or fake structures are produced.
- No CPU substitution or copied experimental PDB is used.
- No download or installation is attempted.

Once the declared assets are admitted (native datasets / checkpoint mounted,
`openfold` and `Bio` importable, CUDA device usable), running
`python solution/main.py run --input input --output output` will execute real
OpenFold model_1_ptm GPU inference for each of the five full-length targets and
produce the deliverables:

- `output/<TARGET>/<TARGET>.pdb` — full-length structure with pLDDT in the
  B-factor column and per-residue identifiers as emitted by OpenFold.
- `output/<TARGET>/*.json` — per-target confidence arrays.
- `output/run_state.json`, `output/run.json` — provenance, timings, device info,
  PDB SHA256, template cutoff.

The reference-large scale (five full-length CASP14 targets, incl. H1044 at 2180
residues) is not exercised by this debug container; passing debug does not
constitute passing the reference-large scale.
