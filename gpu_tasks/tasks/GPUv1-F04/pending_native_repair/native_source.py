"""Bind exact upstream model registrations and original OC20 partition identities."""
import hashlib
import os
import pickle
import sys
from pathlib import Path

import lmdb


def setup(inputs):
    sys.path.insert(0, str(Path(inputs) / 'upstream/equiformer_v2'))
    sys.path.insert(0, str(Path(inputs) / 'upstream/ocp'))
    # Restore the old upstream torch.load behavior only for the explicitly frozen
    # official checkpoint. Modern PyTorch otherwise changes pickle admission.
    os.environ['TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD'] = '1'
    import nets
    import oc20.trainer


def select(path, per_partition=2):
    environment = lmdb.open(str(path), subdir=False, readonly=True, lock=False, readahead=False)
    buckets = {p: [] for p in ('val_id', 'val_ood_ads', 'val_ood_cat', 'val_ood_both')}
    with environment.begin() as transaction:
        for _, value in transaction.cursor():
            record = pickle.loads(value)
            partition, sid = record['partition'], str(record['sid'])
            if partition not in buckets:
                raise ValueError('Unknown original OC20 validation partition')
            buckets[partition].append((hashlib.sha256(sid.encode()).hexdigest(), sid, record))
    environment.close()
    selected = []
    for partition, rows in buckets.items():
        if len(rows) < per_partition:
            raise ValueError('Incomplete original partition: ' + partition)
        selected.extend((partition, sid, record) for _, sid, record in sorted(rows)[:per_partition])
    return selected, {'total_records': sum(map(len, buckets.values())), 'partition_metadata': 'present',
                      'selection': 'SHA256 of original sid within each original validation partition'}
