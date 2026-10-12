"""CLI for the repaired native Cylinder3D adapter."""
import argparse
import importlib
import json
from pathlib import Path

import torch

from native_core import infer, train


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('doctor', 'run', 'resume', 'infer'):
        command = commands.add_parser(name)
        command.add_argument('--input', type=Path, required=True)
        if name != 'doctor':
            command.add_argument('--output', type=Path, required=True)
        if name == 'infer':
            command.add_argument('--checkpoint', type=Path, required=True)
            command.add_argument('--sequence', default='01')
    args = parser.parse_args()
    inputs = args.input.resolve()
    if args.command == 'doctor':
        missing = [str(p) for p in (inputs / 'manifest.json', inputs / 'upstream/Cylinder3D/train_cylinder_asym.py',
                                   inputs / 'SemanticKITTI/sequences/00/velodyne') if not p.exists()]
        for name in ('spconv.pytorch', 'torch_scatter', 'numba', 'yaml'):
            try:
                importlib.import_module(name)
            except ImportError as error:
                missing.append(f'{name}: {error}')
        if not torch.cuda.is_available():
            missing.append('CUDA device')
        print(json.dumps({'ready': not missing, 'missing': missing}, indent=2))
        return 78 if missing else 0
    if not torch.cuda.is_available():
        raise RuntimeError('Native numerical work requires CUDA')
    if args.command == 'infer':
        print(json.dumps(infer(inputs, args.checkpoint.resolve(), args.output.resolve(), args.sequence), indent=2))
    else:
        print(json.dumps(train(inputs, args.output.resolve(), args.command == 'resume'), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
