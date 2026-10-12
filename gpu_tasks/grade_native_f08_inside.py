"""Independent original-checkpoint CorrDiff ensemble and subsequent-request oracle."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from modulus import Module
from modulus.utils.generative import ablation_sampler, StackedRandomGenerator
import numpy as np
import torch


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def reference(condition, seed, regression, diffusion):
    low = torch.tensor(condition[None], device='cuda').to(memory_format=torch.channels_last)
    random = StackedRandomGenerator('cuda', [seed])
    noise = random.randn((1, 4, 448, 448), device='cuda').to(memory_format=torch.channels_last)
    with torch.inference_mode():
        mean = regression(torch.zeros_like(noise, dtype=torch.float64), low, torch.tensor(1., dtype=torch.float64, device='cuda'), None).to(torch.float64)
        residual = ablation_sampler(diffusion, noise, low, None, randn_like=random.randn_like,
                                    num_steps=8, solver='euler', discretization='edm', schedule='linear', scaling='none', S_churn=0)
    return (mean + residual)[0].float().cpu().numpy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('task_id')
    args = parser.parse_args()
    assert args.task_id == 'GPUv1-F08' and torch.cuda.is_available()
    inputs, output = Path('/workspace/input'), Path('/artifacts/output')
    destination = Path('/workspace/evaluation')
    destination.mkdir(exist_ok=True)
    metadata = json.loads((inputs / 'condition_metadata.json').read_text())
    conditions = np.load(inputs / 'conditions.npy', allow_pickle=False)
    target = np.load('/oracle/targets.npy', allow_pickle=False)
    state = json.loads((output / 'state.json').read_text())
    assert [item['seed'] for item in state['members']] == list(range(6))
    for name, value in state['checkpoint_hashes'].items():
        assert digest(inputs / 'corrdiff' / name) == value
    regression = Module.from_checkpoint(str(inputs / 'corrdiff/regression.mdlus')).to('cuda').eval()
    diffusion = Module.from_checkpoint(str(inputs / 'corrdiff/diffusion.mdlus')).to('cuda').eval()
    center = np.array(metadata['output_center'], np.float32)[:, None, None]
    scale = np.array(metadata['output_scale'], np.float32)[:, None, None]
    predictions = []
    for item in state['members']:
        assert item['time_index'] == 0 and item['valid_time'] == metadata['times'][0]
        array = np.load(output / item['prediction'], allow_pickle=False)
        assert array.shape == (4, 448, 448) and array.dtype == np.float32 and np.isfinite(array).all()
        expected = reference(conditions[0], item['seed'], regression, diffusion) * scale + center
        assert np.allclose(array, expected, atol=2e-5, rtol=2e-6), 'complete independent ensemble field mismatch'
        assert item['sha256'] == digest(output / item['prediction'])
        speed = np.hypot(array[2], array[3])
        assert np.isclose(item['wind_speed_mean_m_s'], speed.mean())
        assert np.isclose(item['wind_speed_p95_m_s'], np.percentile(speed, 95))
        predictions.append(array)
    assert np.max(np.std(predictions, axis=0)) > 0, 'copied ensemble members'
    # A new timestamp is evaluated in a fresh solver process using the same weights.
    shutil.copytree('/artifacts/solution', '/workspace/solution')
    continued = destination / 'new_timestamp'
    command = ['python', '/workspace/solution/main.py', 'run', '--input', str(inputs), '--output', str(continued), '--time-index', '1', '--members', '1', '--start-seed', '11']
    result = subprocess.run(command, text=True, capture_output=True, timeout=120)
    (destination / 'new_timestamp_command.json').write_text(json.dumps({'exit_code': result.returncode, 'output': result.stdout + result.stderr}, indent=2) + '\n')
    assert result.returncode == 0, result.stdout[-1000:] + result.stderr[-1000:]
    extra = np.load(continued / 'time001_seed0011.npy', allow_pickle=False)
    expected_extra = reference(conditions[1], 11, regression, diffusion) * scale + center
    assert np.allclose(extra, expected_extra, atol=2e-5, rtol=2e-6), 'subsequent timestamp did not use genuine conditions'
    quality = np.sqrt(np.mean((np.mean(predictions[:5], axis=0) - target[0]) ** 2, axis=(1, 2)))
    report = {
        'passed': True, 'independently_recomputed_members': 6, 'resumed_member_seed': 5,
        'new_timestamp_verified': metadata['times'][1], 'new_seed_verified': 11,
        'native_grid_shape': [448, 448], 'ensemble_mean_rmse_by_channel': quality.tolist(),
        'output_channels': metadata['output_channels'], 'reference_large_tested': False, 'formal_quality_passed': None,
    }
    (destination / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
