"""Official nuScenes mini converter and format upgrade, using all native sweeps."""
import hashlib
import json
import shutil
import sys
from pathlib import Path

import mmengine

inputs = Path('input').resolve()
source = inputs / 'mmdetection3d'
sys.path.insert(0, str(source))
from tools.dataset_converters.nuscenes_converter import create_nuscenes_infos
from tools.dataset_converters.update_infos_to_v2 import update_nuscenes_infos

destination = Path('output/nuscenes').resolve()
destination.mkdir(parents=True, exist_ok=True)
# Source LiDAR is mounted read-only; only small metadata is staged writable.
for name in ('samples', 'sweeps', 'v1.0-mini', 'maps'):
    (destination / name).symlink_to(inputs / 'nuscenes_mini' / name, target_is_directory=True)
create_nuscenes_infos(str(destination), 'nuscenes', version='v1.0-mini', max_sweeps=10)
Path('data').mkdir(exist_ok=True)
Path('data/nuscenes').symlink_to(destination, target_is_directory=True)
selection = {}
for split, count in [('train', 8), ('val', 4)]:
    file = destination / f'nuscenes_infos_{split}.pkl'
    original = mmengine.load(file)
    ordered = sorted(original['infos'], key=lambda row: hashlib.sha256(row['token'].encode()).hexdigest())
    selection[split] = [{'token': x['token'], 'source_timestamp': x['timestamp']} for x in ordered[:count]]
    original['infos'] = ordered[:count]
    mmengine.dump(original, file)
    update_nuscenes_infos(str(file), str(destination))
    upgraded = mmengine.load(file)
    mmengine.dump(upgraded, file)
(Path('output') / 'selection.json').write_text(json.dumps(selection, indent=2) + '\n')
print(json.dumps({'source_split': 'official v1.0-mini mini_train/mini_val', 'train': 8, 'validation': 4}))
