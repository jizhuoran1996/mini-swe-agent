"""Recompute full KiTS inference from the original reference checkpoint."""
import argparse
import csv
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import zoom
from scipy.signal.windows import gaussian
import torch


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def infer(image, model):
    dimensions = image.shape[-3:]
    result = np.zeros((3, *dimensions), np.float32)
    normalization = np.zeros(dimensions, np.float32)
    one = gaussian(128, 16)
    patch_weights = np.cbrt(np.einsum('i,j,k->ijk', one, one, one))
    patch_weights = (patch_weights / patch_weights.max()).astype(np.float32)
    slices = itertools.product(*(range(0, length - 127, 64) for length in dimensions))
    windows = 0
    with torch.inference_mode():
        for indices in slices:
            region = tuple(slice(index, index + 128) for index in indices)
            batch = torch.tensor(image[(slice(None), *region)][None], device='cuda')
            logits = model(batch)[0].float().cpu().numpy()
            assert logits.shape == (3, 128, 128, 128) and np.isfinite(logits).all()
            result[(slice(None), *region)] += logits * patch_weights
            normalization[region] += patch_weights
            windows += 1
    assert np.all(normalization > 0), 'incomplete volume coverage'
    return np.argmax(result / normalization, axis=0).astype(np.uint8), windows


def original_grid(mask, geometry):
    padded = geometry['padded_shape']
    clipped = [n % 64 if n % 64 < 32 else 0 for n in padded]
    clipped_shape = np.array(padded) - clipped
    added = np.array(mask.shape) - clipped_shape
    region = tuple(slice(int(n // 2), int(n // 2 + size)) for n, size in zip(added, clipped_shape))
    mask = np.pad(mask[region], [(n // 2, n - n // 2) for n in clipped])
    added = np.array(padded) - geometry['resampled_shape']
    mask = mask[tuple(slice(int(n // 2), int(n // 2 + size)) for n, size in zip(added, geometry['resampled_shape']))]
    return zoom(mask, np.array(geometry['original_shape']) / np.array(mask.shape), order=0, grid_mode=False)


def checked_mask(path, shape):
    mask = np.load(path, allow_pickle=False)
    assert mask.dtype == np.uint8 and tuple(mask.shape) == tuple(shape), 'wrong output grid or dtype'
    assert set(np.unique(mask)).issubset({0, 1, 2}), 'invalid class ID'
    return mask


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('task_id')
    args = parser.parse_args()
    assert args.task_id == 'GPUv1-B05' and torch.cuda.is_available()
    inputs = Path('/workspace/input')
    output = Path('/artifacts/output')
    destination = Path('/workspace/evaluation')
    destination.mkdir(exist_ok=True)
    geometry = json.loads((inputs / 'cases.json').read_text())['cases'][0]
    assert geometry['case_id'] == 'case_00000'
    image = np.load(inputs / 'preprocessed/case_00000.npy', allow_pickle=False)
    model = torch.jit.load(str(inputs / 'reference_model.pt'), map_location='cuda').eval()
    expected, windows = infer(image, model)
    predicted = checked_mask(output / 'masks/case_00000_preprocessed.npy', expected.shape)
    assert np.array_equal(predicted, expected), 'complete reference inference differs'
    expected_original = original_grid(expected, geometry)
    delivered = checked_mask(output / 'masks/case_00000.npy', geometry['original_shape'])
    assert np.array_equal(delivered, expected_original), 'prediction is on the wrong original grid'
    sidecar = json.loads((output / 'masks/case_00000.json').read_text())
    assert sidecar['model_sha256'] == digest(inputs / 'reference_model.pt')
    assert np.array_equal(sidecar['affine'], geometry['affine'])
    assert np.array_equal(sidecar['spacing_mm'], geometry['spacing'])
    with (output / 'volumes.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1 and int(rows[0]['case_id']) == 0
    for name, identifier in [('kidney', 1), ('tumor', 2)]:
        assert int(rows[0][name + '_voxels']) == int((delivered == identifier).sum())
        volume = np.prod(geometry['spacing']) * (delivered == identifier).sum() / 1000
        assert np.isclose(float(rows[0][name + '_ml']), volume)
    ground_truth = np.load('/oracle/original_labels.npy', allow_pickle=False)
    assert ground_truth.shape == delivered.shape
    dice = {}
    for name, identifier in [('kidney', 1), ('tumor', 2)]:
        a, b = delivered == identifier, ground_truth == identifier
        dice[name] = float(2 * np.count_nonzero(a & b) / max(1, np.count_nonzero(a) + np.count_nonzero(b)))
    run = json.loads((output / 'run.json').read_text())
    assert run['status'] == 'completed' and run['device']['cuda'] is True
    report = {
        'passed': True, 'case_ids': ['case_00000'], 'full_reference_windows': windows,
        'original_shape': geometry['original_shape'], 'reference_model_sha256': sidecar['model_sha256'],
        'original_grid_dice': dice, 'reference_large_tested': False, 'formal_quality_passed': None,
    }
    (destination / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
