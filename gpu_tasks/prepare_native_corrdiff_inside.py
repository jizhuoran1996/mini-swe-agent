"""Freeze native CorrDiff conditions; high resolution fields stay in the oracle."""
import json
from pathlib import Path
import sys

import numpy as np


source = Path('/workspace/input/upstream/modulus/examples/generative/corrdiff')
sys.path.insert(0, str(source))
from datasets.cwb import get_zarr_dataset

dataset = get_zarr_dataset(
    data_path='/workspace/input/cwa.zarr', normalization='v1', all_times=True,
    train=False, crop_size_x=448, crop_size_y=448, n_history=0,
    in_channels=[0, 1, 2, 3, 4, 9, 10, 11, 12, 17, 18, 19], out_channels=[0, 17, 18, 19],
    img_shape_x=448, img_shape_y=448, roll=False, add_grid=True, ds_factor=4,
    min_path=None, max_path=None, global_means_path=None, global_stds_path=None,
    gridtype='sinusoidal', N_grid_channels=4,
)
conditions, targets = [], []
for index in range(len(dataset)):
    target, condition, _ = dataset[index]
    conditions.append(condition)
    targets.append(dataset.denormalize_output(target[None])[0])
destination = Path('/workspace/output')
destination.mkdir(exist_ok=True)
np.save(destination / 'conditions.npy', np.array(conditions, dtype=np.float32))
np.save(destination / 'targets.npy', np.array(targets, dtype=np.float32))
np.save(destination / 'latitude.npy', np.asarray(dataset.latitude()))
np.save(destination / 'longitude.npy', np.asarray(dataset.longitude()))
normalized_zero = np.zeros((1, 4, 448, 448), np.float32)
normalized_one = np.ones_like(normalized_zero)
center = dataset.denormalize_output(normalized_zero)[0, :, 0, 0]
scale = (dataset.denormalize_output(normalized_one) - dataset.denormalize_output(normalized_zero))[0, :, 0, 0]
metadata = {
    'times': [str(t) for t in dataset.time()],
    'input_channels': [str(c) for c in dataset.input_channels()],
    'output_channels': [str(c) for c in dataset.output_channels()],
    'shape': list(np.array(conditions).shape), 'output_center': center.tolist(), 'output_scale': scale.tolist(),
    'source_preprocessing': 'locked modulus.examples.generative.corrdiff.datasets.cwb.get_zarr_dataset',
}
(destination / 'condition_metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
print(json.dumps(metadata, indent=2))
