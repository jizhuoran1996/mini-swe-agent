"""Prepare two genuinely new source test audios with the frozen native fairseq extractor."""
import csv
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

inputs = Path('input').resolve()
sys.path.insert(0, str(inputs / 'fairseq'))
from examples.speech_to_text.data_utils import extract_fbank_features

torch.set_num_threads(4)
rows = json.loads((inputs / 'covost/new_test.json').read_text())
out = Path('output')
(out / 'features').mkdir(parents=True, exist_ok=True)
manifest, references = [], []
for row in rows:
    waveform, rate = sf.read(inputs / 'covost/audio/new_test' / (row['id'] + '.audio'), dtype='float32', always_2d=True)
    features = extract_fbank_features(torch.from_numpy(waveform.T.copy()), rate)
    np.save(out / 'features' / (row['id'] + '.npy'), features)
    manifest.append({'id': row['id'], 'audio': '/workspace/input/covost2/features/' + row['id'] + '.npy',
                     'n_frames': len(features), 'tgt_text': '', 'speaker': ''})
    references.append({'id': row['id'], 'reference': row['translation'], 'n_frames': len(features)})
with (out / 'new_test.tsv').open('w') as stream:
    writer = csv.DictWriter(stream, delimiter='\t', fieldnames=list(manifest[0]))
    writer.writeheader()
    writer.writerows(manifest)
(out / 'references.json').write_text(json.dumps(references, indent=2, ensure_ascii=False))
print('Two new test recordings preprocessed by the original acoustic path')
