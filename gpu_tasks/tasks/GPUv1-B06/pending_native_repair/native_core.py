"""Current source MMDetection3D CenterPoint configuration and native entrypoints."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import torch
from mmengine.config import Config

CONFIG = 'configs/centerpoint/centerpoint_voxel0075_second_secfpn_head-circlenms_8xb4-cyclic-20e_nus-3d.py'


def build_configuration(inputs, output, resume=False):
    source = inputs / 'upstream/mmdetection3d'
    config = Config.fromfile(source / CONFIG)
    dataset = config.train_dataloader.dataset
    while 'dataset' in dataset:
        dataset = dataset.dataset
    dataset = dict(dataset)
    dataset.update(data_root=str(inputs / 'nuscenes'), ann_file='nuscenes_infos_train.pkl',
                   data_prefix=dict(pts='samples/LIDAR_TOP', img='', sweeps='sweeps/LIDAR_TOP'))
    dataset['pipeline'] = [item for item in dataset['pipeline'] if item['type'] != 'ObjectSample']
    config.train_dataloader.update(batch_size=1, num_workers=0, persistent_workers=False)
    config.train_dataloader.dataset = dataset
    for name in ('test_dataloader',):
        loader = config[name]
        loader.update(batch_size=1, num_workers=0, persistent_workers=False)
        loader.dataset.update(data_root=str(inputs / 'nuscenes'), ann_file='nuscenes_infos_val.pkl',
                              data_prefix=dict(pts='samples/LIDAR_TOP', img='', sweeps='sweeps/LIDAR_TOP'))
    epoch = 0
    checkpoint = output / 'model_checkpoint.pth'
    if resume:
        state = torch.load(checkpoint, map_location='cpu', weights_only=False)
        epoch = state['meta']['epoch']
        shutil.copy2(checkpoint, output / 'checkpoint_before_resume.pth')
    config.train_cfg.update(max_epochs=epoch + 1, val_interval=100)
    config.val_cfg = config.val_dataloader = config.val_evaluator = None
    config.work_dir = str(output)
    config.randomness = dict(seed=1, deterministic=False)
    config.resume = resume
    config.load_from = str(checkpoint) if resume else None
    config.default_hooks.checkpoint.update(interval=1, save_last=True, max_keep_ckpts=2)
    config.test_evaluator.update(data_root=str(inputs / 'nuscenes'),
        ann_file=str(inputs / 'nuscenes/nuscenes_infos_val.pkl'),
        format_only=True, jsonfile_prefix=str(output / 'native_predictions'))
    return config, source, epoch + 1


def run(inputs, output, resume=False):
    output.mkdir(parents=True, exist_ok=True)
    config, source, epoch = build_configuration(inputs, output, resume)
    frozen = output / 'native_debug_config.py'
    config.dump(frozen)
    env = os.environ.copy()
    env['TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD'] = '1'
    commands = []
    for phase, tool in [('train', 'train.py'), ('test', 'test.py')]:
        command = [sys.executable, str(source / 'tools' / tool), str(frozen)]
        if phase == 'test':
            checkpoint = output / f'epoch_{epoch}.pth'
            if not checkpoint.is_file():
                raise FileNotFoundError('Native trainer did not export its real epoch checkpoint')
            shutil.copy2(checkpoint, output / 'model_checkpoint.pth')
            command.append(str(output / 'model_checkpoint.pth'))
        with (output / f'{phase}_{epoch}.log').open('w') as stream:
            result = subprocess.run(command, cwd=source, env=env, stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError((output / f'{phase}_{epoch}.log').read_text()[-5000:])
        commands.append(command)
    predictions = list((output / 'native_predictions').rglob('results_nusc.json'))
    if len(predictions) != 1:
        raise RuntimeError('Native NuScenes result export is missing or ambiguous')
    shutil.copy2(predictions[0], output / 'nuscenes_predictions.json')
    results = json.loads(predictions[0].read_text())['results']
    selection = json.loads((inputs / 'selection.json').read_text())
    if set(results) != {row['token'] for row in selection['val']}:
        raise ValueError('Native test pipeline skipped requested source scans')
    report = {'task_id': 'GPUv1-B06', 'complete': True, 'scale': 'native_debug',
        'backend': 'MMDetection3D original CenterPoint 0.075m voxel / circle NMS',
        'epoch': epoch, 'resume': resume, 'commands': commands, 'training_samples': len(selection['train']),
        'validation_tokens': sorted(results), 'detections': sum(len(x) for x in results.values()),
        'device': torch.cuda.get_device_name(0), 'reference_large_tested': False}
    (output / 'run.json').write_text(json.dumps(report, indent=2) + '\n')
    return report
