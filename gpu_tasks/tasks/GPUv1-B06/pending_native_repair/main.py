"""CLI for native current MMDetection3D CenterPoint training and resume."""
import argparse
import json
from pathlib import Path

import torch
from native_core import run


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('doctor', 'run', 'resume'):
        command = commands.add_parser(name)
        command.add_argument('--input', type=Path, required=True)
        if name != 'doctor':
            command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    inputs = args.input.resolve()
    if args.command == 'doctor':
        missing = [name for name in ('upstream/mmdetection3d/tools/train.py',
            'nuscenes/nuscenes_infos_train.pkl', 'nuscenes/nuscenes_infos_val.pkl', 'nuscenes/v1.0-mini/scene.json')
            if not (inputs / name).is_file()]
        try:
            import mmdet3d
            from mmcv.ops import Voxelization
        except ImportError as error:
            missing.append(str(error))
        if not torch.cuda.is_available():
            missing.append('CUDA device')
        print(json.dumps({'ready': not missing, 'missing': missing}, indent=2))
        return 78 if missing else 0
    if not torch.cuda.is_available():
        raise RuntimeError('Native CenterPoint training requires CUDA')
    print(json.dumps(run(inputs, args.output.resolve(), args.command == 'resume'), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
