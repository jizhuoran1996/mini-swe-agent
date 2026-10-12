"""Native CorrDiff v1 with genuine CWA conditions and original checkpoints."""
import argparse
import importlib.util
import json
from pathlib import Path
import time

from native_core import digest, models, physical, predict, source_generator


def doctor(inputs):
    files = ['conditions.npy', 'condition_metadata.json', 'latitude.npy', 'longitude.npy',
             'corrdiff/regression.mdlus', 'corrdiff/diffusion.mdlus',
             'upstream/modulus/examples/generative/corrdiff/generate.py']
    missing = [name for name in files if not (inputs / name).is_file()]
    missing += ['module:' + name for name in ('modulus', 'torch', 'numpy', 'nvtx', 'hydra', 'zarr', 'netCDF4') if importlib.util.find_spec(name) is None]
    return {'ready': not missing, 'missing': missing}


def execute(args):
    import numpy as np
    import torch
    report = doctor(args.input)
    if not report['ready']:
        print(json.dumps(report, indent=2))
        return 78
    started = time.time()
    conditions = np.load(args.input / 'conditions.npy', allow_pickle=False)
    metadata = json.loads((args.input / 'condition_metadata.json').read_text())
    assert conditions.shape == (5, 16, 448, 448) and 0 <= args.time_index < len(conditions)
    args.output.mkdir(parents=True, exist_ok=True)
    state_path = args.output / 'state.json'
    state = json.loads(state_path.read_text()) if args.command == 'resume' and state_path.exists() else {'members': []}
    bound = {name: digest(args.input / 'corrdiff' / name) for name in ('regression.mdlus', 'diffusion.mdlus')}
    if state.get('checkpoint_hashes'):
        assert state['checkpoint_hashes'] == bound, 'checkpoint changed between requests'
        assert state['condition_hash'] == digest(args.input / 'conditions.npy'), 'input instance changed'
    start_seed = args.start_seed if args.start_seed is not None else max((item['seed'] for item in state['members']), default=-1) + 1
    generator = source_generator(args.input)
    regression, diffusion = models(args.input)
    for seed in range(start_seed, start_seed + args.members):
        name = f'time{args.time_index:03d}_seed{seed:04d}.npy'
        assert not (args.output / name).exists(), 'refusing to overwrite an existing member'
        normalized = predict(args.input, conditions[args.time_index], seed, regression, diffusion, generator)
        assert normalized.shape == (4, 448, 448) and np.isfinite(normalized).all()
        prediction = physical(normalized, metadata)
        np.save(args.output / name, prediction)
        np.save(args.output / ('normalized_' + name), normalized)
        wind_speed = np.hypot(prediction[2], prediction[3])
        member = {
            'seed': seed, 'time_index': args.time_index, 'valid_time': metadata['times'][args.time_index],
            'prediction': name, 'sha256': digest(args.output / name),
            'wind_speed_mean_m_s': float(wind_speed.mean()), 'wind_speed_p95_m_s': float(np.percentile(wind_speed, 95)),
            'temperature_mean_k': float(prediction[1].mean()),
        }
        state['members'].append(member)
        state.update({'checkpoint_hashes': bound, 'condition_hash': digest(args.input / 'conditions.npy'),
                      'output_channels': metadata['output_channels'], 'sampling': 'upstream 8-step deterministic EDM Euler, per-member seed'})
        state_path.write_text(json.dumps(state, indent=2) + '\n')
        print(json.dumps(member), flush=True)
    report = {
        'task_id': 'GPUv1-F08', 'status': 'completed', 'command': args.command,
        'backend': 'NVIDIA Modulus 0.6.0a0 native CorrDiff inference v1',
        'device': torch.cuda.get_device_name(0), 'cuda': True, 'reference_large_tested': False,
        'members_in_request': args.members, 'members_total': len(state['members']),
        'checkpoint_hashes': bound, 'elapsed_seconds': time.time() - started,
        'latitude_hash': digest(args.input / 'latitude.npy'), 'longitude_hash': digest(args.input / 'longitude.npy'),
    }
    (args.output / ('run_resume.json' if args.command == 'resume' else 'run.json')).write_text(json.dumps(report, indent=2) + '\n')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    diagnostic = sub.add_parser('doctor')
    diagnostic.add_argument('--input', type=Path, required=True)
    for command in ('run', 'resume'):
        child = sub.add_parser(command)
        child.add_argument('--input', type=Path, required=True)
        child.add_argument('--output', type=Path, required=True)
        child.add_argument('--time-index', type=int, default=0)
        child.add_argument('--members', type=int, default=5 if command == 'run' else 1)
        child.add_argument('--start-seed', type=int)
    args = parser.parse_args()
    args.input = args.input.resolve()
    if args.command == 'doctor':
        report = doctor(args.input)
        print(json.dumps(report, indent=2))
        return 0 if report['ready'] else 78
    args.output = args.output.resolve()
    return execute(args)


if __name__ == '__main__':
    raise SystemExit(main())
