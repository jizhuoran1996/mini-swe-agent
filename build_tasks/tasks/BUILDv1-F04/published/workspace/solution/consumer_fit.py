import pickle
import sys
from pathlib import Path

import numpy as np
import sklearn
import sklearn.neighbors._kd_tree as kdt


out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
print('sklearn.__file__ =', sklearn.__file__)
print('kd_tree.__file__  =', kdt.__file__)
assert '/workspace/src' not in sklearn.__file__, 'imported from source tree'
assert 'site-packages' in sklearn.__file__ or 'dist-packages' in sklearn.__file__

rng = np.random.RandomState(0)
X = rng.randn(400, 6)
Q = rng.randn(12, 6)
_, idx = kdt.KDTree(X).query(Q, k=5)
brute = np.sqrt(((X[None, :, :] - Q[:, None, :]) ** 2).sum(-1))
ref_idx = np.argsort(brute, axis=1)[:, :5]
# Compare distances selected by the KD-tree's own indices to the brute-force
# sorted distances (permutation-tolerant: identical multisets demanded).
assert np.allclose(np.take_along_axis(brute, idx, 1),
                   np.take_along_axis(brute, ref_idx, 1), atol=1e-9)
print('KDTree indices select the nearest brute-force points: OK')

from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

rng = np.random.RandomState(7)
Xp = rng.randn(300, 6)
yp = (Xp[:, 0] + 0.7 * Xp[:, 1] - 0.5 * Xp[:, 2] > 0.1).astype(int)
Xt = rng.randn(50, 6)
pipe = Pipeline([('scaler', StandardScaler()),
                 ('clf', LogisticRegression(max_iter=1000))]).fit(Xp, yp)
pred = pipe.predict(Xt)
prob = pipe.predict_proba(Xt)
assert pred.shape == (50,) and prob.shape == (50, 2)
print('Pipeline train accuracy = %.3f' % pipe.score(Xp, yp))
with (out / 'pipeline.pkl').open('wb') as fh:
    pickle.dump(pipe, fh)
np.save(out / 'Xtest.npy', Xt)
np.save(out / 'expected_pred.npy', pred)
np.save(out / 'expected_prob.npy', prob)
print('saved pipeline and expectations to', out)
