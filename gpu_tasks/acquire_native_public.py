"""Restore public native-task assets outside the solver container."""
import argparse
import json
import shutil
import tarfile
from pathlib import Path

import requests

from assets import digest, fetch


def oc20(root):
    url = 'https://dl.fbaipublicfiles.com/opencatalystproject/data/is2res_train_val_test_lmdbs.tar.gz'
    archive = fetch(url, root / 'downloads/oc20_is2res.tar.gz', max_bytes=10 * 2**30)
    destination = root / 'oc20_validation'
    destination.mkdir(exist_ok=True)
    records = []
    with tarfile.open(archive, mode='r|gz') as source:
        for member in source:
            if not member.isfile() or not member.name.endswith('.lmdb') or '/val_' not in member.name:
                continue
            if member.size > 8 * 2**30 or shutil.disk_usage(destination).free - member.size < 50 * 2**30:
                raise RuntimeError('validation member exceeds disk budget')
            target = destination / Path(member.name).parent.name / Path(member.name).name
            target.parent.mkdir(exist_ok=True)
            if not target.exists():
                with source.extractfile(member) as incoming, target.open('wb') as out:
                    shutil.copyfileobj(incoming, out, length=8 << 20)
            records.append({'archive_member': member.name, 'path': str(target.relative_to(destination)),
                            'bytes': target.stat().st_size, 'sha256': digest(target)})
            print('OC20 validation member:', member.name, member.size, flush=True)
    if len(records) != 4:
        raise RuntimeError(f'Expected four genuine validation partitions, got {len(records)}')
    lock = {'source': url, 'archive_sha256': digest(archive), 'files': records,
            'selection': 'all four original OC20 IS2RE validation LMDB partitions; initial positions only'}
    (destination / 'source_lock.json').write_text(json.dumps(lock, indent=2) + '\n')


def fcn3(root):
    revision = 'df5d8d005f2334c16502581abf0a510c634c295a'
    info = requests.get(f'https://huggingface.co/api/models/nvidia/fourcastnet3/revision/{revision}', timeout=30)
    info.raise_for_status()
    destination = root / 'fcn3_package'
    records = []
    for item in info.json()['siblings']:
        name = item['rfilename']
        if name == '.gitattributes' or name == 'README.md':
            continue
        target = fetch(f'https://huggingface.co/nvidia/fourcastnet3/resolve/{revision}/{name}',
                       destination / name, max_bytes=4 * 2**30)
        records.append({'path': name, 'bytes': target.stat().st_size, 'sha256': digest(target)})
        print('FCN3 package file:', name, target.stat().st_size, flush=True)
    (destination / 'source_lock.json').write_text(json.dumps({'repo': 'nvidia/fourcastnet3',
        'revision': revision, 'files': records}, indent=2) + '\n')


def speech_and_folding(root):
    records = []
    for name, url in [
        ('covost2_en_asr_transformer_s.pt', 'https://dl.fbaipublicfiles.com/fairseq/s2t/covost2_en_asr_transformer_s.pt'),
        ('openfold_finetuning_ptm_1.pt', 'https://openfold.s3.amazonaws.com/openfold_params/finetuning_ptm_1.pt')]:
        target = fetch(url, root / 'downloads' / name, max_bytes=1024**3)
        records.append({'path': name, 'source': url, 'bytes': target.stat().st_size, 'sha256': digest(target)})
        print('Native model:', name, target.stat().st_size, flush=True)
    (root / 'downloads/speech_folding_lock.json').write_text(json.dumps(records, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('asset', choices=['oc20', 'fcn3', 'speech_and_folding'])
    parser.add_argument('--storage', type=Path, required=True)
    args = parser.parse_args()
    globals()[args.asset](args.storage)
