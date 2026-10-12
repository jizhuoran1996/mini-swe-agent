"""Use the locked MLPerf preprocessing implementation on a genuine KiTS case."""
import argparse
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import nibabel as nib
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--case', default='case_00000')
    args = parser.parse_args()
    args.source = args.source.resolve()
    args.raw = args.raw.resolve()
    os.chdir(args.source)
    sys.path.insert(0, str(args.source))
    from preprocess import Preprocessor

    destination = Path('/workspace/output')
    destination.mkdir(exist_ok=True)
    processor = Preprocessor(SimpleNamespace(results_dir=str(destination), data_dir=str(args.raw), calibration=False))
    image, label, auxiliary = processor.load_and_resample(args.case)
    resampled_shape = list(image.shape[1:])
    image = processor.normalize_intensity(image)
    image, label = processor.pad_to_min_shape(image, label)
    padded_shape = list(image.shape[1:])
    image, label = processor.adjust_shape_for_sliding_window(image, label)
    np.save(destination / (args.case + '.npy'), image)
    np.save(destination / 'preprocessed_labels.npy', label)
    raw = nib.load(args.raw / args.case / 'imaging.nii.gz')
    original_label = nib.load(args.raw / args.case / 'segmentation.nii.gz')
    np.save(destination / 'original_labels.npy', np.asarray(original_label.dataobj, dtype=np.uint8))
    metadata = {
        'case_id': args.case, 'original_shape': list(raw.shape),
        'preprocessed_shape': list(image.shape), 'spacing': list(map(float, raw.header.get_zooms())),
        'affine': raw.affine.tolist(), 'target_spacing_mm': processor.target_spacing,
        'normalization': {'mean': processor.mean, 'std': processor.std, 'min': processor.min_val, 'max': processor.max_val},
        'zoom_factor': auxiliary['zoom_factor'].tolist(), 'preprocessed_dtype': str(image.dtype),
        'resampled_shape': resampled_shape, 'padded_shape': padded_shape,
        'shape_adjustment': 'MLPerf Preprocess3DUnet.pad_to_min_shape + adjust_shape_for_sliding_window',
    }
    (destination / 'geometry.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    main()
