#!/usr/bin/env python3
"""Independent consumer: train a small CPU tree model, save it, reload in a new process."""
import json
import sys
from pathlib import Path

import numpy as np
import xgboost as xgb


def make_data():
    rng = np.random.RandomState(7)
    x = rng.randn(300, 6).astype(np.float32)
    y = ((x[:, 0] + 0.4 * x[:, 1] - 0.2 * x[:, 2]) > 0.1).astype(np.float32)
    return xgb.DMatrix(x, label=y)


def main():
    model_path = Path(sys.argv[1])
    digest_path = model_path.with_suffix('.json')
    load_only = '--load' in sys.argv[2:]
    dm = make_data()
    if load_only:
        expected = json.loads(digest_path.read_text())['pred_sum']
        booster = xgb.Booster(model_file=str(model_path))
        pred = booster.predict(dm)
        drift = abs(float(pred.sum()) - expected)
        assert drift < 1e-4, f'prediction drift {drift} after model reload'
        report = {'mode': 'load', 'lib': str(xgb.core._LIB),
                  'pred_sum': float(pred.sum()), 'drift': drift}
    else:
        params = {'objective': 'binary:logistic', 'tree_method': 'hist',
                  'max_depth': 3, 'eta': 0.3, 'seed': 7, 'nthread': 2}
        booster = xgb.train(params, dm, num_boost_round=25)
        pred = booster.predict(dm)
        booster.save_model(str(model_path))
        report = {'mode': 'train', 'lib': str(xgb.core._LIB),
                  'model': str(model_path), 'pred_sum': float(pred.sum()),
                  'head': [float(v) for v in pred[:4]]}
        digest_path.write_text(json.dumps(report))
    print(json.dumps(report, sort_keys=True))


main()
