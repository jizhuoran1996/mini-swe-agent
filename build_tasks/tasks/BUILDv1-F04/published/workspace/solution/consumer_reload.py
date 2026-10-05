import pickle
import sys
from pathlib import Path

import numpy as np
import sklearn


d = Path(sys.argv[1])
with (d / 'pipeline.pkl').open('rb') as fh:
    pipe = pickle.load(fh)
X = np.load(d / 'Xtest.npy')
exp_p = np.load(d / 'expected_pred.npy')
exp_pr = np.load(d / 'expected_prob.npy')
got_p = pipe.predict(X)
got_pr = pipe.predict_proba(X)
assert (got_p == exp_p).all(), 'reloaded predictions differ'
assert np.allclose(got_pr, exp_pr, atol=1e-12), 'reloaded probabilities differ'
print('reload OK; sklearn', sklearn.__version__)
