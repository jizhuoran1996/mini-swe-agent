"""Trusted CPU preprocessing with fairseq's original acoustic feature extractor."""
import csv
import io
import json
import sys
import tarfile
from pathlib import Path

import numpy as np
import sentencepiece as sp
import soundfile as sf
import torch
import yaml

source = Path('input/fairseq').resolve()
sys.path.insert(0, str(source))
from examples.speech_to_text.data_utils import extract_fbank_features

raw = Path('input/covost').resolve()
out = Path('output/covost2').resolve()
out.mkdir(parents=True, exist_ok=True)
features = out / 'features'
features.mkdir(exist_ok=True)
torch.set_num_threads(4)

# Only original train translations train the tokenizer, including the full source
# train text corpus. Test strings are retained solely for the evaluator.
with tarfile.open(raw / 'translations.tar.gz') as archive:
    stream = io.TextIOWrapper(archive.extractfile(archive.getmembers()[0]))
    rows = csv.DictReader(stream, delimiter='\t', quoting=csv.QUOTE_NONE)
    with (out / 'vocab_train_text.txt').open('w') as text:
        for row in rows:
            if row['split'] in ('train', 'train_covost'):
                text.write(row['translation'].replace('\n', ' ') + '\n')
prefix = out / 'spm_unigram10000'
sp.SentencePieceTrainer.train(input=str(out / 'vocab_train_text.txt'), model_prefix=str(prefix),
    model_type='unigram', vocab_size=10000, character_coverage=1.0,
    unk_id=3, bos_id=0, eos_id=2, pad_id=1, num_threads=4, shuffle_input_sentence=False)
tokenizer = sp.SentencePieceProcessor(model_file=str(prefix) + '.model')
with (out / 'dict.txt').open('w') as dictionary:
    for i in range(4, tokenizer.get_piece_size()):
        dictionary.write(tokenizer.id_to_piece(i) + ' 1\n')
(out / 'vocab_train_text.txt').unlink()

evidence = []
references = []
for split in ('train', 'test'):
    raw_rows = json.loads((raw / f'{split}.json').read_text())
    manifest = []
    for row in raw_rows:
        audio = raw / 'audio' / split / (row['id'] + '.audio')
        waveform, rate = sf.read(audio, dtype='float32', always_2d=True)
        bank = extract_fbank_features(torch.from_numpy(waveform.T.copy()), rate)
        if bank.ndim != 2 or bank.shape[1] != 80 or not np.isfinite(bank).all():
            raise ValueError('Invalid original acoustic features: ' + row['id'])
        np.save(features / (row['id'] + '.npy'), bank)
        target = row['translation'] if split == 'train' else ''
        manifest.append({'id': row['id'], 'audio': '/workspace/input/covost2/features/' + row['id'] + '.npy',
                         'n_frames': len(bank), 'tgt_text': target, 'speaker': ''})
        evidence.append({'id': row['id'], 'sample_rate': rate, 'samples': len(waveform),
                         'frames': len(bank), 'source_split': split, 'source_audio_sha256': row['sha256']})
        if split == 'test':
            references.append({'id': row['id'], 'reference': row['translation'], 'n_frames': len(bank)})
    with (out / f'{split}.tsv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=['id', 'audio', 'n_frames', 'tgt_text', 'speaker'],
                                delimiter='\t', quoting=csv.QUOTE_NONE, escapechar='\\')
        writer.writeheader()
        writer.writerows(manifest)
    if split == 'train':
        # Source training validation is disjoint from the held-out test split.
        with (out / 'dev.tsv').open('w') as stream:
            writer = csv.DictWriter(stream, fieldnames=['id', 'audio', 'n_frames', 'tgt_text', 'speaker'],
                                    delimiter='\t', quoting=csv.QUOTE_NONE, escapechar='\\')
            writer.writeheader()
            writer.writerows(manifest[:5])

config = {'vocab_filename': 'dict.txt', 'input_feat_per_channel': 80, 'input_channels': 1,
          'bpe_tokenizer': {'bpe': 'sentencepiece', 'sentencepiece_model': '/workspace/input/covost2/spm_unigram10000.model'},
          'transforms': {'_train': ['utterance_cmvn', 'specaugment'], '*': ['utterance_cmvn']},
          'specaugment': {'freq_mask_F': 27, 'freq_mask_N': 2, 'time_mask_N': 2, 'time_mask_T': 100, 'time_mask_p': 1.0}}
(out / 'config_st.yaml').write_text(yaml.safe_dump(config))
(Path('output') / 'feature_evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
(Path('output') / 'private_test_references.json').write_text(json.dumps(references, indent=2, ensure_ascii=False) + '\n')
print(json.dumps({'train': 200, 'test': 20, 'vocabulary': tokenizer.get_piece_size(),
                  'feature_extractor': 'fairseq examples.speech_to_text.data_utils.extract_fbank_features'}))
