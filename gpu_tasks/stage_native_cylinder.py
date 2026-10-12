"""Freeze genuine scans and an explicit spconv 2 compatibility port of Cylinder3D."""
import json
import re
import shutil
from pathlib import Path

import yaml

from assets import digest
from container import ROOT

STORAGE = Path('/data/data/zrji/gpu60-native-20261012')
destination = STORAGE / 'inputs/GPUv1-B07'
destination.mkdir(exist_ok=True)
source = destination / 'upstream/Cylinder3D'
shutil.copytree(STORAGE / 'Cylinder3D', source, dirs_exist_ok=True,
                ignore_dangling_symlinks=True, ignore=shutil.ignore_patterns('__pycache__'))
changes = []
for file in source.rglob('*.py'):
    before = file.read_text()
    after = before.replace('import spconv\n', 'import spconv.pytorch as spconv\n')
    after = re.sub(r'\bnp\.int\b', 'np.int64', after)
    after = re.sub(r'\bnp\.float\b', 'np.float64', after)
    after = re.sub(r'^(\s*)(\w+)\.features = (.+)$',
        lambda m: f'{m[1]}{m[2]} = {m[2]}.replace_feature({m[3]})', after, flags=re.MULTILINE)
    if after != before:
        file.write_text(after)
        changes.append({'path': str(file.relative_to(source)), 'original_sha256': digest(STORAGE / 'Cylinder3D' / file.relative_to(source)),
                        'adapted_sha256': digest(file), 'reason': 'spconv 2 feature API and NumPy deprecated type aliases'})

trainer = source / 'train_cylinder_asym.py'
text = trainer.read_text().replace('import os\n', 'import os\nimport random\nimport json\n')
text = text.replace("    pytorch_device = torch.device('cuda:0')", "    random.seed(1)\n    np.random.seed(1)\n    torch.manual_seed(1)\n    torch.cuda.manual_seed_all(1)\n    pytorch_device = torch.device('cuda:0')")
text = text.replace("    if os.path.exists(model_load_path):\n        my_model = load_checkpoint(model_load_path, my_model)",
"""    state = None
    if os.path.exists(model_load_path):
        state = torch.load(model_load_path, map_location='cpu', weights_only=False)
        my_model.load_state_dict(state['model'], strict=True)
    else:
        torch.save(my_model.state_dict(), os.path.join(os.path.dirname(model_save_path), 'initial_model.pt'))""")
text = text.replace('    epoch = 0\n', "    epoch = state['epoch'] if state else 0\n")
text = text.replace('    global_iter = 0\n', """    global_iter = state['global_iter'] if state else 0
    if state:
        optimizer.load_state_dict(state['optimizer'])
        random.setstate(state['rng']['python'])
        np.random.set_state(state['rng']['numpy'])
        torch.set_rng_state(state['rng']['torch'])
        torch.cuda.set_rng_state_all(state['rng']['cuda'])
    history = list(state['history']) if state else []
    resume_start = global_iter
""")
text = text.replace('        time.sleep(10)\n', '')
text = text.replace('            loss_list.append(loss.item())',
    "            loss_list.append(loss.item())\n            history.append({'epoch': epoch, 'update': global_iter + 1, 'loss': loss.item()})")
text = text.replace('        epoch += 1\n', """        epoch += 1
        checkpoint = {'model': my_model.state_dict(), 'optimizer': optimizer.state_dict(),
            'epoch': epoch, 'global_iter': global_iter, 'history': history, 'config': configs,
            'rng': {'python': random.getstate(), 'numpy': np.random.get_state(),
                    'torch': torch.get_rng_state(), 'cuda': torch.cuda.get_rng_state_all()}}
        torch.save(checkpoint, model_load_path)
        with open(os.path.join(os.path.dirname(model_save_path), 'training_progress.json'), 'w') as stream:
            json.dump({'epochs': epoch, 'updates': global_iter, 'resume_start': resume_start,
                       'train_scans': len(train_dataset_loader.dataset), 'history': history}, stream, indent=2)
""")
trainer.write_text(text)
changes.append({'path': 'train_cylinder_asym.py', 'reason': 'Persist original optimizer, epoch, updates and RNG state for native restart; remove source progress sleep',
                'adapted_sha256': digest(trainer)})
scans = destination / 'SemanticKITTI/sequences'
scans.mkdir(parents=True, exist_ok=True)
oracle = STORAGE / 'oracles/GPUv1-B07'
oracle.mkdir(exist_ok=True)
for sequence in ('00', '08', '01'):
    original = STORAGE / 'semantickitti_raw/dataset/sequences' / sequence
    if not original.exists():
        original = STORAGE / 'semantickitti_raw/sequences' / sequence
    shutil.copytree(original / 'velodyne', scans / sequence / 'velodyne', dirs_exist_ok=True)
    target = scans / sequence / 'labels' if sequence == '00' else oracle / sequence / 'labels'
    shutil.copytree(original / 'labels', target, dirs_exist_ok=True)

mapping = source / 'config/label_mapping/semantic-kitti.yaml'
original_mapping = yaml.safe_load(mapping.read_text())
original_mapping['split']['train'] = [0]
original_mapping['split']['valid'] = [0]
mapping.write_text(yaml.safe_dump(original_mapping))
shutil.copy2(STORAGE / 'semantickitti_raw/source_lock.json', destination / 'source_lock.json')
(destination / 'compatibility_changes.json').write_text(json.dumps(changes, indent=2) + '\n')
manifest = {'task_id': 'GPUv1-B07', 'assets_ready': True, 'scale': 'native_debug',
    'backend': 'original Cylinder3D asymmetric sparse CNN and cylindrical voxelization',
    'source_revision': '30a0abb2ca4c657a821a5e9a343934b0789b2365',
    'train': {'sequence': '00', 'frames': [0, 1, 2, 3]}, 'validation': {'sequence': '08', 'frames': [0, 1]},
    'new_input': {'sequence': '01', 'frames': [0]},
    'grid_shape': [480, 360, 32], 'batch_size': 1,
    'requirements': ['spconv.pytorch', 'torch_scatter', 'yaml'],
    'deviations': ['Four complete training scans, two complete held-out validation scans and one new scan, instead of formal full sequences',
        'Original training loop gains checkpoint/optimizer/RNG persistence and uses spconv 2 compatible feature access; architecture and losses retained',
        'Training-loop diagnostics use sequence 00; sequence 08 and 01 labels are private independent-evaluation data'],
    'reference_large_tested': False}
(destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
task = ROOT / 'tasks/GPUv1-B07'
history = task / 'asset_history'
history.mkdir(exist_ok=True)
if not (task / 'input').is_symlink():
    shutil.move(str(task / 'input'), str(history / 'input_before_native_20261012'))
    (task / 'input').symlink_to(destination, target_is_directory=True)
if not (task / 'oracle').exists():
    (task / 'oracle').symlink_to(oracle, target_is_directory=True)
print('Cylinder3D native source and genuine complete scans frozen')
