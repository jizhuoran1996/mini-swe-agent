"""CLI for the repaired native global FCN3 ensemble."""
import argparse
import json
from pathlib import Path

import torch
from native_core import forecast


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('doctor', 'run', 'resume'):
        command = commands.add_parser(name)
        command.add_argument('--input', type=Path, required=True)
        if name != 'doctor':
            command.add_argument('--output', type=Path, required=True)
            command.add_argument('--initial', default='era5_initial.nc')
            command.add_argument('--seed', type=int, default=20240211)
    args = parser.parse_args()
    inputs = args.input.resolve()
    if args.command == 'doctor':
        missing = [name for name in ('fcn3_checkpoint/config.json',
            'fcn3_checkpoint/training_checkpoints/best_ckpt_mp0.tar', 'era5_initial.nc', 'forecast_config.json')
            if not (inputs / name).is_file()]
        try:
            from earth2studio.models.px import FCN3
            from makani.models.model_package import LocalPackage
        except ImportError as error:
            missing.append(str(error))
        if not torch.cuda.is_available():
            missing.append('CUDA device')
        print(json.dumps({'ready': not missing, 'missing': missing}, indent=2))
        return 78 if missing else 0
    if not torch.cuda.is_available():
        raise RuntimeError('Native FCN3 prediction requires CUDA')
    print(json.dumps(forecast(inputs, args.output.resolve(), args.command == 'resume', args.initial, args.seed), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
