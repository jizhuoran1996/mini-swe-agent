"""Native Cylinder3D training and full-point inference on genuine SemanticKITTI scans."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import torch
import yaml


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 << 20), b''):
            h.update(block)
    return h.hexdigest()


def configuration(inputs, outputs, epochs):
    source = inputs / 'upstream/Cylinder3D'
    config = yaml.safe_load((source / 'config/semantickitti.yaml').read_text())
    config['dataset_params']['label_mapping'] = str(source / 'config/label_mapping/semantic-kitti.yaml')
    for name in ('train_data_loader', 'val_data_loader'):
        config[name].update(data_path=str(inputs / 'SemanticKITTI/sequences'), batch_size=1, num_workers=0)
    config['train_params'].update(max_num_epochs=epochs,
        model_load_path=str(outputs / 'checkpoint_last.pt'),
        model_save_path=str(outputs / 'checkpoint_best_model.pt'), eval_every_n_steps=4)
    return config


def infer(inputs, checkpoint, destination, sequence='08'):
    source = inputs / 'upstream/Cylinder3D'
    sys.path.insert(0, str(source))
    from builder import model_builder
    from dataloader.pc_dataset import SemKITTI_demo
    from dataloader.dataset_semantickitti import cylinder_dataset, collate_fn_BEV
    state = torch.load(checkpoint, map_location='cpu', weights_only=False)
    config = state['config']
    model = model_builder.build(config['model_params']).cuda().eval()
    model.load_state_dict(state['model'], strict=True)
    data_config = config['dataset_params']
    raw = SemKITTI_demo(str(inputs / 'SemanticKITTI/sequences' / sequence / 'velodyne'),
                        imageset='demo', return_ref=True, label_mapping=data_config['label_mapping'])
    dataset = cylinder_dataset(raw, config['model_params']['output_shape'],
        fixed_volume_space=True, max_volume_space=data_config['max_volume_space'],
        min_volume_space=data_config['min_volume_space'], ignore_label=0)
    loader = torch.utils.data.DataLoader(dataset, batch_size=1, num_workers=0, shuffle=False, collate_fn=collate_fn_BEV)
    mapping = yaml.safe_load((source / 'config/label_mapping/semantic-kitti.yaml').read_text())['learning_map_inv']
    lookup = np.array([mapping[i] for i in range(20)], dtype=np.uint32)
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    with torch.inference_mode():
        for index, (_, _, grids, _, features) in enumerate(loader):
            output = model([torch.from_numpy(x).float().cuda() for x in features],
                           [torch.from_numpy(x).cuda() for x in grids], 1)
            logits = output[0, :, grids[0][:, 0], grids[0][:, 1], grids[0][:, 2]]
            classes = logits.argmax(dim=0).cpu().numpy()
            raw_file = Path(raw.im_idx[index])
            target = destination / (raw_file.stem + '.label')
            lookup[classes].tofile(target)
            records.append({'frame': raw_file.stem, 'points': len(classes),
                            'input_sha256': digest(raw_file), 'prediction_sha256': digest(target)})
    return records


def train(inputs, outputs, resume=False):
    source = inputs / 'upstream/Cylinder3D'
    outputs.mkdir(parents=True, exist_ok=True)
    checkpoint = outputs / 'checkpoint_last.pt'
    if resume:
        previous = torch.load(checkpoint, map_location='cpu', weights_only=False)
        epochs = previous['epoch'] + 1
        (outputs / 'before_resume.json').write_text(json.dumps({'updates': previous['global_iter'],
            'epochs': previous['epoch'], 'checkpoint_sha256': digest(checkpoint),
            'optimizer_state_count': len(previous['optimizer']['state'])}, indent=2))
    else:
        if checkpoint.exists():
            raise FileExistsError('Use resume for an existing trained model')
        epochs = 1
    config = configuration(inputs, outputs, epochs)
    config_path = outputs / 'training_config.yaml'
    config_path.write_text(yaml.safe_dump(config))
    command = [sys.executable, str(source / 'train_cylinder_asym.py'), '-y', str(config_path)]
    log = outputs / ('resume.log' if resume else 'train.log')
    with log.open('w') as stream:
        process = subprocess.run(command, cwd=source, stdout=stream, stderr=subprocess.STDOUT)
    if process.returncode:
        raise RuntimeError(log.read_text()[-5000:])
    records = infer(inputs, checkpoint, outputs / 'predictions/sequences/08')
    progress = json.loads((outputs / 'training_progress.json').read_text())
    report = {'task_id': 'GPUv1-B07', 'complete': True, 'scale': 'native_debug',
        'backend': 'Cylinder3D original asymmetric sparse CNN / native cylindrical voxelization',
        'command': command, 'resume': resume, 'updates': progress['updates'], 'epochs': progress['epochs'],
        'checkpoint_sha256': digest(checkpoint), 'input_manifest_sha256': digest(inputs / 'manifest.json'),
        'validation_predictions': records, 'device': torch.cuda.get_device_name(0),
        'torch': torch.__version__, 'reference_large_tested': False}
    (outputs / 'run.json').write_text(json.dumps(report, indent=2) + '\n')
    return report
