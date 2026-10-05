# GPUv1-F04 - Catalytic adsorption relaxation with EquiformerV2 153M All+MD

Source-native adapter for the OC20 IS2RE validation initial structures relaxed with
the official EquiformerV2 153M All+MD checkpoint along the upstream
`main_oc20.py` relaxation path from
`atomicarchitects/equiformer_v2@d5ad4be729b56f74012ebb7f097f77c5b00a1004`.

That upstream tree imports `ocpmodels.common` and registers the `nets` / `oc20.trainer`
modules. The only calculator used here is the original

    ocpmodels.common.relaxation.ase_utils.OCPCalculator

bound to the provided `equiformer_v2_153M_all_md.pt`. There is **no** newer
fairchem UMA / `pretrained_mlip` fallback, and no mock or CPU substitute.

## Commands

```bash
python solution/main.py --help                      # no model is loaded
python solution/main.py doctor --input input        # 0 if complete, 78 if anything missing
python solution/main.py run    --input input --output output
python solution/main.py resume --input input --output output
```

`doctor` inspects the read-only input tree for every file declared in
`input/manifest.json` (with a basename fallback), imports each required and auxiliary
Python module, verifies that
`ocpmodels.common.relaxation.ase_utils.OCPCalculator` is importable, and probes
`torch.cuda.is_available()`. It prints a JSON report listing **every** missing item
and returns 78 when anything is unavailable, 0 otherwise.

`run` exits 2 when CUDA is unavailable (no CPU fallback) and returns 78 before loading
any model when required inputs are absent. Only when every gate passes does it build
the OC20 `OCPCalculator` on the provided EquiformerV2 checkpoint and relax structures.

## Relaxation protocol

* Structure source: `oc20_initial_structures.lmdb` (read-only OC20 IS2RE LMDB).
* Selection: for each of `val_id`, `val_ood_ads`, `val_ood_cat`, `val_ood_both` the two
  sids with the smallest `SHA256(sid)` are chosen (matches the reference-large
  ordering rule). If the LMDB carries no `dataset`/`split` metadata that is recorded in
  `run.json` (`partition_metadata: "absent"`) and the top 8 sids by hash are used
  instead - nothing is fabricated silently.
* Fixed atoms: the record's own `fixed` mask when present; otherwise atoms whose OC20
  tag is in `fixed_tags` (default `[0]`, subsurface / bulk) are held fixed via ASE
  `FixAtoms`.
* Optimiser, force threshold and step budget come from `input/relaxation.yml`
  (`optimizer`, `fmax`, `max_steps`/`maxstep`); defaults LBFGS / 0.03 eV/A / 200 steps.
* Energies and forces always come from the loaded potential; label/reference energies
  are never substituted for the model output.
* After relaxation the code records `fixed_atom_max_displacement_A`,
  `cell_max_delta_A` and `atomic_numbers_unchanged` so the oracle can confirm that
  composition, cell and fixed atoms are preserved.

## Outputs (written only under `output/`)

| file | content |
|---|---|
| `relaxed_structures.extxyz` | final geometry of every system; sid/partition/converged in `info` |
| `energies.parquet` | sid / partition / step / convergence / initial+final energy / max free force |
| `ranking.json` | energies ranked inside each declared partition |
| `config.json` | input file paths + SHA256, relax config, calculator kind, device |
| `resume_state.json` | per-sid step count and the list of non-converged systems |
| `run.json` | device, seed, real timings (model load / selection / relaxation / total), peak device memory, per-system results |
| `work/<sid>/` | final structure, ASE trajectory, optimiser log and `optimizer.restart` |

`resume` reloads the saved geometry and the ASE optimiser restart file, then continues
only the non-converged systems up to the declared `max_steps` total - converged
structures are never re-randomised or re-inserted.

## Honest limitations

* This container is the **debug** workload (2 sids per validation partition). The input
  manifest declares `assets_ready: false`, so the required checkpoint / LMDB are not
  mounted; `doctor` and `run` therefore exit 78 here. That is a missing-asset report
  and is **not** a solved task and must not be reported as completion.
* Partitions are only as good as the LMDB metadata; if the `dataset`/`split` field is
  absent grouping is reported as unavailable rather than invented.
* `main.py` accepts no shell strings, performs no downloads and does not touch the host.
* An ML potential approximates DFT; the energy ranking is a model ranking, not an
  experimental conclusion.
