"""GPUv1-F10 debug variant: 3D CUDA FNO surrogate for The Well turbulent radiative layer 3D.

Real spectral convolutions implemented with torch.fft.rfftn / torch.fft.irfftn and
trainable truncated Fourier-mode weights (no Conv3D stand-in for the spectral path).

Entry points:
  python solution/main.py train    --input input --output output [--steps N] [--seed S]
  python solution/main.py forecast --checkpoint output/checkpoint.pt \
         --initial input/validation_initial.npy --steps 3 --output output/reloaded.npy
  python solution/main.py forecast --checkpoint output/checkpoint.pt \
         --initial output/state.npz --steps 2 --output output/reloaded.npy
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import time
from typing import Dict, List, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

FIELDS = ("density", "pressure", "velocity_x", "velocity_y", "velocity_z")
SPATIAL_AXES = ("x", "y", "z")
BOUNDARY = {"x": "periodic", "y": "periodic", "z": "open"}

DEFAULT_CONFIG = {
    "width": 32,
    "modes": [8, 8, 12],          # [mx, my, mz] retained Fourier modes (rfftn)
    "n_layers": 4,
    "in_channels": 8,             # 5 normalized fields + 3 coordinate channels
    "out_channels": 5,
    "norm_groups": 8,
    "lr": 1.5e-3,
    "weight_decay": 1e-5,
    "steps": 3000,
    "batch_size": 4,
    "unroll": 2,                  # teacher-forced multi-step training windows
    "unroll_weight": 0.5,
}


# --------------------------------------------------------------------------------------
# utilities
# --------------------------------------------------------------------------------------
def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def rng_state() -> Dict[str, object]:
    st = {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
        "torch": torch.get_rng_state(),
    }
    if torch.cuda.is_available():
        st["cuda"] = torch.cuda.get_rng_state_all()
    return st


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: str) -> dict:
    with open(path, "r") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------------------
# spectral convolution: real 3D FFT + trainable truncated mode weights
# --------------------------------------------------------------------------------------
class SpectralConv3d(nn.Module):
    """3D spectral convolution on a real field.

    forward:  xf = rfftn(x)  ->  truncate to (mx, my, mz) ->  complex einsum with the
              trainable weight tensor -> zero-pad -> irfftn back to the physical grid.

    The weights are stored as a real tensor of shape (in, out, mx, my, mz, 2) and viewed
    as complex so that the standard (real-valued) optimizers work on them directly.
    """

    def __init__(self, in_ch: int, out_ch: int, modes: Tuple[int, int, int]):
        super().__init__()
        self.in_ch = in_ch
        self.out_ch = out_ch
        self.mx, self.my, self.mz = modes
        std = 1.0 / math.sqrt(in_ch * out_ch)
        w = torch.randn(in_ch, out_ch, self.mx, self.my, self.mz, 2) * std
        self.weight = nn.Parameter(w)

    @property
    def complex_weight(self) -> torch.Tensor:
        return torch.view_as_complex(self.weight.contiguous())

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        b, c, d, h, w = x.shape                      # (B, C, x, y, z)
        xf = torch.fft.rfftn(x, dim=(-3, -2, -1))    # (B, C, x, y, z//2+1) complex
        wc = self.complex_weight
        mx = min(self.mx, d)
        my = min(self.my, h)
        mz = min(self.mz, xf.shape[-1])
        patch = xf[:, :, :mx, :my, :mz]
        out = torch.einsum("bixyz,ioxyz->boxyz", patch, wc[:, :, :mx, :my, :mz])
        full = torch.zeros(b, self.out_ch, d, h, xf.shape[-1], dtype=out.dtype, device=out.device)
        full[:, :, :mx, :my, :mz] = out
        return torch.fft.irfftn(full, s=(d, h, w), dim=(-3, -2, -1))


class FNOBlock(nn.Module):
    def __init__(self, width: int, modes: Tuple[int, int, int], groups: int = 8):
        super().__init__()
        self.spec = SpectralConv3d(width, width, modes)
        self.pointwise = nn.Conv3d(width, width, kernel_size=1)
        self.norm = nn.GroupNorm(min(groups, width), width) if groups > 0 else nn.Identity()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return F.gelu(self.norm(self.spec(x) + self.pointwise(x)))


class FNO3D(nn.Module):
    """Residual 3D FNO: predicts the normalized one-step increment of the 5 fields."""

    def __init__(self, cfg: dict):
        super().__init__()
        width = int(cfg["width"])
        modes = tuple(int(m) for m in cfg["modes"])
        n_layers = int(cfg["n_layers"])
        groups = int(cfg.get("norm_groups", 8))
        self.in_channels = int(cfg["in_channels"])
        self.out_channels = int(cfg["out_channels"])
        self.fc0 = nn.Conv3d(self.in_channels, width, kernel_size=1)
        self.blocks = nn.ModuleList([FNOBlock(width, modes, groups) for _ in range(n_layers)])
        self.head = nn.Sequential(
            nn.Conv3d(width, width, kernel_size=1),
            nn.GELU(),
            nn.Conv3d(width, self.out_channels, kernel_size=1),
        )
        # zero-initialised output head -> model starts as identity (persistence)
        nn.init.zeros_(self.head[-1].weight)
        nn.init.zeros_(self.head[-1].bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        z = self.fc0(x)
        for blk in self.blocks:
            z = blk(z)
        return self.head(z)


# --------------------------------------------------------------------------------------
# data helpers
# --------------------------------------------------------------------------------------
def build_coords(coords: dict, shape: Tuple[int, int, int]) -> np.ndarray:
    """(3, x, y, z) coordinate channels bound to the provided metadata grid."""
    axes = []
    for ax, n in zip(SPATIAL_AXES, shape):
        if ax in coords and len(coords[ax]) == n:
            axes.append(np.asarray(coords[ax], dtype=np.float32))
        else:
            axes.append(np.linspace(-0.5, 0.5, n, endpoint=False).astype(np.float32))
    gx, gy, gz = np.meshgrid(axes[0], axes[1], axes[2], indexing="ij")
    return np.stack([gx, gy, gz], axis=0).astype(np.float32)


def compute_stats(fields: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Per-field mean/std over all provided train timesteps (axis=(0,2,3,4))."""
    mean = fields.mean(axis=(0, 2, 3, 4)).astype(np.float32)
    std = fields.std(axis=(0, 2, 3, 4)).astype(np.float32)
    std = np.where(std < 1e-6, 1e-6, std).astype(np.float32)
    return mean, std


def augment(batch: torch.Tensor, gen: torch.Generator) -> torch.Tensor:
    """Random x/y periodic rolls + flips; z is an open boundary, left untouched."""
    out = batch
    for i in range(out.shape[0]):
        sx = int(torch.randint(0, out.shape[-3], (1,), generator=gen).item())
        sy = int(torch.randint(0, out.shape[-2], (1,), generator=gen).item())
        out[i] = torch.roll(out[i], shifts=(sx, sy), dims=(-3, -2))
        if torch.rand(1, generator=gen).item() < 0.5:
            out[i] = torch.flip(out[i], dims=(-3,))
        if torch.rand(1, generator=gen).item() < 0.5:
            out[i] = torch.flip(out[i], dims=(-2,))
    return out


# --------------------------------------------------------------------------------------
# model I/O wrappers
# --------------------------------------------------------------------------------------
def make_input(norm_fields: torch.Tensor, coords: torch.Tensor) -> torch.Tensor:
    """norm_fields (B,5,x,y,z) -> (B,8,x,y,z) with broadcast coordinate channels."""
    b = norm_fields.shape[0]
    c = coords.unsqueeze(0).expand(b, -1, -1, -1, -1)
    return torch.cat([norm_fields, c], dim=1)


def normalize(fields: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    return ((fields - mean.reshape(1, -1, 1, 1, 1)) / std.reshape(1, -1, 1, 1, 1)).astype(np.float32)


def denormalize(norm: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    return (norm * std.reshape(1, -1, 1, 1, 1) + mean.reshape(1, -1, 1, 1, 1)).astype(np.float32)


# --------------------------------------------------------------------------------------
# training
# --------------------------------------------------------------------------------------
def train(args) -> None:
    cfg = dict(DEFAULT_CONFIG)
    if args.steps is not None:
        cfg["steps"] = int(args.steps)
    if args.width is not None:
        cfg["width"] = int(args.width)
    if args.modes is not None:
        cfg["modes"] = [int(v) for v in args.modes]
    if args.layers is not None:
        cfg["n_layers"] = int(args.layers)
    if args.lr is not None:
        cfg["lr"] = float(args.lr)
    if args.unroll is not None:
        cfg["unroll"] = int(args.unroll)
    if args.batch_size is not None:
        cfg["batch_size"] = int(args.batch_size)
    if args.no_norm:
        cfg["norm_groups"] = 0
    seed = int(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    os.makedirs(args.output, exist_ok=True)

    t_start = time.time()
    set_seed(seed)

    train_fields = np.load(os.path.join(args.input, "train_fields.npy")).astype(np.float32)
    valid_init = np.load(os.path.join(args.input, "validation_initial.npy")).astype(np.float32)
    train_times = np.load(os.path.join(args.input, "train_times.npy")).astype(np.float64)
    valid_times = np.load(os.path.join(args.input, "validation_times.npy")).astype(np.float64)
    coords_json = load_json(os.path.join(args.input, "coordinates.json"))
    manifest = load_json(os.path.join(args.input, "manifest.json"))
    coords_np = build_coords(coords_json, train_fields.shape[2:])

    mean, std = compute_stats(train_fields)
    norm = normalize(train_fields, mean, std)                      # (T,5,x,y,z)
    coords = torch.from_numpy(coords_np).to(device)                # (3,x,y,z)

    # held-out target: last provided train timestep (t=6 -> t=7) is never trained on.
    n_t = norm.shape[0]
    holdout_src = n_t - 2
    train_starts = list(range(0, holdout_src))                     # starts 0..5 for unroll=2
    norm_t = torch.from_numpy(norm).to(device)

    model = FNO3D(cfg).to(device)
    n_params = sum(p.numel() for p in model.parameters())
    opt = torch.optim.AdamW(model.parameters(), lr=float(cfg["lr"]),
                            weight_decay=float(cfg["weight_decay"]))
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=int(cfg["steps"]), eta_min=1e-4)
    gen = torch.Generator(device="cpu")
    gen.manual_seed(seed + 1234)

    def window_loss(start: int, unroll: int) -> torch.Tensor:
        """Teacher-forced unrolled loss in normalized space."""
        cur = norm_t[start:start + 1]
        loss = torch.zeros((), device=device)
        wsum = 0.0
        for k in range(unroll):
            inp = make_input(cur.detach(), coords)
            delta = model(inp)
            pred = cur + delta
            tgt = norm_t[start + k + 1:start + k + 2]
            loss = loss + (pred - tgt).pow(2).mean()
            wsum += 1.0
        return loss / wsum

    batch_size = int(cfg["batch_size"])
    unroll = int(cfg["unroll"])
    history: List[float] = []
    model.train()
    step = 0
    for step in range(1, int(cfg["steps"]) + 1):
        idx = [train_starts[i] for i in torch.randint(0, len(train_starts), (batch_size,),
                                                      generator=gen).tolist()]
        loss = torch.zeros((), device=device)
        for s in idx:
            loss = loss + window_loss(int(s), unroll)
        loss = loss / batch_size
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        sched.step()
        history.append(float(loss.detach().cpu()))
    model.eval()
    train_wall = time.time() - t_start

    # ---------------- evaluation on held-out train timestep -------------------------
    @torch.no_grad()
    def predict_next(norm_state: torch.Tensor) -> torch.Tensor:
        return norm_state + model(make_input(norm_state, coords))

    @torch.no_grad()
    def rollout_norm(norm_state: torch.Tensor, steps: int) -> List[torch.Tensor]:
        outs = []
        cur = norm_state
        for _ in range(steps):
            cur = predict_next(cur)
            outs.append(cur)
        return outs

    def field_metrics(pred_np: np.ndarray, tgt_np: np.ndarray) -> Dict[str, object]:
        """pred/tgt in normalized units, shape (T,5,x,y,z)."""
        e = pred_np - tgt_np
        per_field = np.sqrt((e ** 2).mean(axis=(0, 2, 3, 4)))
        return {"rmse_normalized_per_field": {f: float(v) for f, v in zip(FIELDS, per_field)},
                "rmse_normalized_per_field_mean": float(per_field.mean()),
                "rmse_normalized_global": float(np.sqrt((e ** 2).mean()))}

    def phys_metrics(pred_np: np.ndarray, tgt_np: np.ndarray) -> Dict[str, object]:
        e = pred_np - tgt_np
        per_field = np.sqrt((e ** 2).mean(axis=(0, 2, 3, 4)))
        return {"rmse_physical_per_field": {f: float(v) for f, v in zip(FIELDS, per_field)},
                "rmse_physical_per_field_mean": float(per_field.mean()),
                "rmse_physical_global": float(np.sqrt((e ** 2).mean()))}

    eval_out: Dict[str, object] = {
        "held_out": ("train trajectory transition t6->t7 (t=15.970 -> 18.632); pair 6 is excluded "
                     "from optimisation (training uses starts 0..5)"),
        "normalization": "per-field z-score over all provided train timesteps",
        "one_step": {}, "rollout_3step_from_t4": {}, }

    src_state = norm_t[holdout_src:holdout_src + 1]
    tgt_state = norm_t[holdout_src + 1:holdout_src + 2]
    with torch.no_grad():
        one_pred = predict_next(src_state)
    true_phys = train_fields[holdout_src + 1:holdout_src + 2]
    preds = {"model": one_pred, "persistence": src_state}
    for name, pred in preds.items():
        pn = pred.cpu().numpy()
        pp = denormalize(pn, mean, std)
        entry = field_metrics(pn, tgt_state.cpu().numpy())
        entry.update(phys_metrics(pp, true_phys))
        eval_out["one_step"][name] = entry

    roll_start = holdout_src - 2                                   # t=4 -> 3 steps -> t=7
    with torch.no_grad():
        rolled = rollout_norm(norm_t[roll_start:roll_start + 1], 3)
    rolled_n = torch.cat(rolled, 0).cpu().numpy()                  # (3,5,x,y,z) normalized
    rolled_p = denormalize(rolled_n, mean, std)
    truth_p = train_fields[roll_start + 1:roll_start + 4]
    persist_n = np.repeat(norm_t[roll_start:roll_start + 1].cpu().numpy(), 3, axis=0)
    persist_p = np.repeat(train_fields[roll_start][None], 3, axis=0)
    for name, (rp, rn) in (("model", (rolled_p, rolled_n)), ("persistence", (persist_p, persist_n))):
        e = rp - truth_p
        e_n = rn - norm_t[roll_start + 1:roll_start + 4].cpu().numpy()
        per_step_phys = np.sqrt((e ** 2).mean(axis=(1, 2, 3, 4)))
        per_step_norm = np.sqrt((e_n ** 2).mean(axis=(1, 2, 3, 4)))
        eval_out["rollout_3step_from_t4"][name] = {
            "rmse_physical_per_step": [float(v) for v in per_step_phys],
            "rmse_physical_mean": float(per_step_phys.mean()),
            "rmse_normalized_per_step": [float(v) for v in per_step_norm],
            "rmse_normalized_mean": float(per_step_norm.mean()),
            "rmse_physical_global_at_step3": float(np.sqrt((e[-1] ** 2).mean())),
            "rmse_normalized_global_at_step3": float(np.sqrt((e_n[-1] ** 2).mean())),
        }

    # ---------------- validation rollout (autoregressive, initial only) -------------
    sync_times = {}
    if device.type == "cuda":
        torch.cuda.synchronize()
    t0 = time.time()
    vnorm = normalize(valid_init[None], mean, std)
    with torch.no_grad():
        vrolled = rollout_norm(torch.from_numpy(vnorm).to(device), 3)
    vrolled_np = denormalize(torch.cat(vrolled, 0).cpu().numpy(), mean, std)   # (3,5,x,y,z)
    if device.type == "cuda":
        torch.cuda.synchronize()
    sync_times["rollout_seconds"] = time.time() - t0
    valid_times_used = valid_times[:4]
    assert vrolled_np.shape == (3, 5) + tuple(train_fields.shape[2:]), vrolled_np.shape

    np.save(os.path.join(args.output, "rollout.npy"), vrolled_np.astype(np.float32))
    np.savez(os.path.join(args.output, "state.npz"),
             fields=vrolled_np[-1].astype(np.float32),
             time=np.float64(valid_times_used[-1]),
             times=valid_times_used.astype(np.float64),
             boundary=np.array([BOUNDARY[a] for a in SPATIAL_AXES]),
             spatial_axes=np.array(SPATIAL_AXES),
             fields_order=np.array(FIELDS))

    ckpt = {
        "model_state": model.state_dict(),
        "config": cfg,
        "optimizer_state": opt.state_dict(),
        "scheduler_state": sched.state_dict(),
        "step": step,
        "training_stats": {"loss_history": history,
                           "initial_loss": history[0] if history else None,
                           "final_loss": history[-1] if history else None,
                           "loss_mean_last_100": float(np.mean(history[-100:])) if history else None},
        "normalization": {"mean": mean.tolist(), "std": std.tolist(), "fields": list(FIELDS),
                          "scheme": "per-field z-score over all provided train timesteps"},
        "rng": rng_state(),
        "seed": seed,
        "n_params": int(n_params),
        "coords": {"x": coords_json.get("x"), "y": coords_json.get("y"), "z": coords_json.get("z")},
        "meta": {"train_shape": list(train_fields.shape),
                 "train_times": train_times.tolist(),
                 "valid_times": valid_times.tolist(),
                 "device": str(device),
                 "config_overrides": {"residual_forecast": True}},
        "source": {"dataset": manifest.get("dataset"),
                   "revision": manifest.get("dataset_revision"),
                   "task_id": manifest.get("task_id"),
                   "scale": manifest.get("scale")},
    }
    torch.save(ckpt, os.path.join(args.output, "checkpoint.pt"))

    run = {
        "task_id": manifest.get("task_id"),
        "scale": manifest.get("scale", "debug_only"),
        "device": str(device),
        "gpu": torch.cuda.get_device_name(0) if device.type == "cuda" else None,
        "seed": seed,
        "n_params": int(n_params),
        "config": cfg,
        "normalization": ckpt["normalization"],
        "train": {"steps": step, "wall_seconds": train_wall,
                  "initial_loss": ckpt["training_stats"]["initial_loss"],
                  "final_loss": ckpt["training_stats"]["final_loss"],
                  "loss_mean_last_100": ckpt["training_stats"]["loss_mean_last_100"],
                  "loss_history": history},
        "evaluation_on_train": eval_out,
        "valid_future_note": ("validation_initial.npy has valid future frames withheld by the input pack "
                              "(only the initial field is provided), so future error cannot be scored "
                              "against valid ground truth here; rollout.npy is produced and error vs a "
                              "persistence baseline is reported on the held-out train timestep instead. "
                              "This debug variant does not claim full source-FNO quality."),
        "rollout": {"shape": list(vrolled_np.shape), "steps": 3,
                    "times": valid_times_used.tolist(),
                    "initial_source": "input/validation_initial.npy",
                    "synchronized_timing_seconds": sync_times},
        "coordinates": {"axes": list(SPATIAL_AXES), "shape_xyz": list(train_fields.shape[2:]),
                        "x_range": [float(coords_json["x"][0]), float(coords_json["x"][-1])],
                        "y_range": [float(coords_json["y"][0]), float(coords_json["y"][-1])],
                        "z_range": [float(coords_json["z"][0]), float(coords_json["z"][-1])],
                        "boundary_conditions": BOUNDARY,
                        "note": "stride-4 downsampled full physical domain, not random voxels"},
        "source_binding": {"manifest": manifest,
                           "input_sha256": {f: sha256_file(os.path.join(args.input, f))
                                            for f in sorted(os.listdir(args.input))
                                            if f.endswith((".npy", ".json"))}},
        "state_npz": {"keys": ["fields", "time", "times", "boundary", "spatial_axes", "fields_order"],
                      "fields_shape": list(vrolled_np[-1].shape)},
        "total_wall_seconds": time.time() - t_start,
    }
    with open(os.path.join(args.output, "run.json"), "w") as fh:
        json.dump(run, fh, indent=2)
    print(json.dumps({"train_loss_final": run["train"]["final_loss"],
                      "one_step": eval_out["one_step"],
                      "rollout": eval_out["rollout_3step_from_t4"],
                      "rollout_seconds": sync_times["rollout_seconds"]}, indent=2))


# --------------------------------------------------------------------------------------
# forecast
# --------------------------------------------------------------------------------------
def load_initial(path: str) -> Tuple[np.ndarray, np.ndarray, float]:
    """Returns (fields (5,x,y,z), preceding times array, last time)."""
    if path.endswith(".npz"):
        with np.load(path, allow_pickle=False) as d:
            fields = np.asarray(d["fields"], dtype=np.float32)
            times = np.asarray(d["times"], dtype=np.float64) if "times" in d.files else \
                np.asarray([float(d["time"])], dtype=np.float64)
            t_last = float(d["time"]) if "time" in d.files else float(times[-1])
        return fields, times, t_last
    fields = np.load(path).astype(np.float32)
    if fields.ndim == 4:
        pass
    elif fields.ndim == 5 and fields.shape[0] == 1:
        fields = fields[0]
    else:
        raise ValueError(f"unexpected initial shape {fields.shape}")
    return fields, np.asarray([], dtype=np.float64), float("nan")


def forecast(args) -> None:
    ckpt = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    cfg = ckpt["config"]
    seed = int(ckpt.get("seed", 0))
    set_seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    mean = np.asarray(ckpt["normalization"]["mean"], dtype=np.float32)
    std = np.asarray(ckpt["normalization"]["std"], dtype=np.float32)
    coords_np = build_coords(ckpt["coords"], tuple(ckpt["meta"]["train_shape"][2:]))
    coords = torch.from_numpy(coords_np).to(device)

    model = FNO3D(cfg).to(device)
    model.load_state_dict(ckpt["model_state"])
    model.eval()

    init, times_in, t_last = load_initial(args.initial)
    print(f"initial shape={init.shape} last_time={t_last}")

    cur = torch.from_numpy(normalize(init[None], mean, std)).to(device)
    steps = int(args.steps)
    outs = []
    if device.type == "cuda":
        torch.cuda.synchronize()
    t0 = time.time()
    with torch.no_grad():
        for _ in range(steps):
            cur = cur + model(make_input(cur, coords))
            outs.append(cur)
    pred = denormalize(torch.cat(outs, 0).cpu().numpy(), mean, std).astype(np.float32)
    if device.type == "cuda":
        torch.cuda.synchronize()
    dt_wall = time.time() - t0
    assert pred.shape == (steps, 5) + tuple(init.shape[1:]), pred.shape
    out_path = args.output if args.output.endswith((".npy", ".npz")) else os.path.join(args.output, "reloaded.npy")
    if out_path.endswith(".npz"):
        np.savez(out_path, fields=pred[-1], rollout=pred,
                 times=(times_in.tolist() if times_in.size else []))
    else:
        np.save(out_path, pred)
    print(json.dumps({"saved": out_path, "shape": list(pred.shape), "steps": steps,
                      "initial": args.initial, "synchronized_seconds": dt_wall}, indent=2))


def main() -> None:
    p = argparse.ArgumentParser(description="GPUv1-F10 3D FNO surrogate")
    sub = p.add_subparsers(dest="cmd", required=True)

    pt = sub.add_parser("train")
    pt.add_argument("--input", default="input")
    pt.add_argument("--output", default="output")
    pt.add_argument("--steps", type=int, default=None)
    pt.add_argument("--seed", type=int, default=0)
    pt.add_argument("--width", type=int, default=None)
    pt.add_argument("--modes", type=int, nargs=3, default=None)
    pt.add_argument("--layers", type=int, default=None)
    pt.add_argument("--lr", type=float, default=None)
    pt.add_argument("--unroll", type=int, default=None)
    pt.add_argument("--batch-size", type=int, default=None)
    pt.add_argument("--no-norm", action="store_true")
    pt.set_defaults(func=train)

    pf = sub.add_parser("forecast")
    pf.add_argument("--checkpoint", required=True)
    pf.add_argument("--initial", required=True)
    pf.add_argument("--steps", type=int, default=3)
    pf.add_argument("--output", default="output/reloaded.npy")
    pf.set_defaults(func=forecast)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
