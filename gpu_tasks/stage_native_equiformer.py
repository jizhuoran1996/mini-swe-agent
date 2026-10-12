"""Select genuine OC20 IS2RE initial structures from all four official partitions."""
import hashlib
import json
import pickle
import shutil
from pathlib import Path

import lmdb

from assets import digest
from container import ROOT

storage = Path('/data/data/zrji/gpu60-native-20261012')
destination = storage / 'inputs/GPUv1-F04'
destination.mkdir(exist_ok=True)
shutil.copytree(storage / 'equiformer_v2', destination / 'upstream/equiformer_v2',
                dirs_exist_ok=True, ignore_dangling_symlinks=True, ignore=shutil.ignore_patterns('__pycache__'))
shutil.copy2(storage / 'downloads/equiformer_v2_153M_all_md.pt', destination / 'equiformer_v2_153M_all_md.pt')
target = lmdb.open(str(destination / 'oc20_initial_structures.lmdb'), subdir=False, map_size=16 * 2**20)
records = []
for partition in ('val_id', 'val_ood_ads', 'val_ood_cat', 'val_ood_both'):
    file = storage / 'oc20_validation' / partition / 'data.lmdb'
    original = lmdb.open(str(file), subdir=False, readonly=True, lock=False, readahead=False)
    candidates = []
    with original.begin() as transaction:
        for key, value in transaction.cursor():
            if key == b'length':
                continue
            data = pickle.loads(value).__dict__
            sid = str(data['sid'])
            candidates.append((hashlib.sha256(sid.encode()).hexdigest(), sid, key))
        for sid_hash, sid, key in sorted(candidates)[:2]:
            value = transaction.get(key)
            data = pickle.loads(value).__dict__
            record = {'sid': sid, 'partition': partition}
            for field in ('pos', 'cell', 'atomic_numbers', 'tags', 'fixed'):
                record[field] = data[field].tolist()
            with target.begin(write=True) as output:
                output.put((partition + ':' + sid).encode(), pickle.dumps(record, protocol=4))
            records.append({'partition': partition, 'sid': sid, 'sid_sha256': sid_hash,
                            'source_key': key.decode(), 'raw_record_sha256': hashlib.sha256(value).hexdigest(),
                            'atoms': len(record['atomic_numbers']), 'partition_records': len(candidates)})
    original.close()
target.close()
(destination / 'relaxation.yml').write_text('relaxation:\n  optimizer: LBFGS\n  fmax: 0.03\n  max_steps: 5\n  fixed_tags: [0]\n')
(destination / 'selection.json').write_text(json.dumps(records, indent=2) + '\n')
shutil.copy2(storage / 'oc20_validation/source_lock.json', destination / 'source_lock.json')
manifest = {'task_id': 'GPUv1-F04', 'assets_ready': True, 'scale': 'native_debug',
    'backend': 'OC20 EquiformerV2 153M All+MD official checkpoint / original OCP calculator',
    'files': ['upstream/equiformer_v2/main_oc20.py', 'equiformer_v2_153M_all_md.pt', 'oc20_initial_structures.lmdb', 'relaxation.yml'],
    'requirements': ['ocpmodels', 'e3nn', 'ase', 'lmdb'], 'selection': records,
    'hashes': {'checkpoint': digest(destination / 'equiformer_v2_153M_all_md.pt'),
               'initial_structures': digest(destination / 'oc20_initial_structures.lmdb')},
    'deviations': ['Five initial LBFGS steps per genuine system plus five resumed steps instead of formal 200 step upper bound'],
    'reference_large_tested': False}
(destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
task = ROOT / 'tasks/GPUv1-F04'
history = task / 'asset_history'
history.mkdir(exist_ok=True)
if not (task / 'input').is_symlink():
    shutil.move(str(task / 'input'), str(history / 'input_before_native_20261012'))
    (task / 'input').symlink_to(destination, target_is_directory=True)
print(json.dumps(records, indent=2))
