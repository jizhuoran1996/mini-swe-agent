#!/usr/bin/env python3
"""Independent TensorFlow consumer run from outside the source tree.

    python consumer_check.py info
    python consumer_check.py save <dir>
    python consumer_check.py load <dir>

`info` asserts the newly installed wheel is a CPU-only build and that the native
extension actually loads. `save`/`load` run in separate processes to prove the
SavedModel and its variables reload after the producing process has exited.

Reload semantics (exact upstream behavior this tool relies on):
  `tensorflow/python/saved_model/load.py::_recreate_base_user_object` recreates
  a plain `tf.Module` as an `AutoTrackable` `_UserObject` (it is deliberately NOT
  a `tf.Module`), and `AutoTrackable._trackable_children` only re-exports tracked
  dependencies/functions. That is why the plain `SoftmaxModule` above exports
  exactly its tracked `bias` Variable and its `__call__` function - and does not
  surface a `.variables` collection. The `.variables` property documented for
  `load()` belongs to Keras / TF1 exports, so the load path here reads the
  genuinely restored public tracked child `loaded.bias` instead. Before any
  output is computed we assert that child is a real `tf.Variable` and that its
  full three-element value matches [0.1, -0.2, 0.3] within float32 tolerance.
  No fallback, no synthesized variable, no skipped assertion.
"""
import json
import sys

import numpy as np
import tensorflow as tf


class SoftmaxModule(tf.Module):
    def __init__(self):
        super().__init__()
        self.bias = tf.Variable([0.1, -0.2, 0.3], dtype=tf.float32, name='bias')

    @tf.function
    def __call__(self, x):
        return tf.nn.softmax(x + self.bias)


X = tf.constant([[0.5, -1.0, 2.0], [1.0, 0.0, -1.0]], dtype=tf.float32)
EXPECTED_BIAS = np.array([0.1, -0.2, 0.3], dtype=np.float32)
BIAS_ATOL = 1e-6


def info():
    build = tf.sysconfig.get_build_info()
    payload = {
        'tensorflow_version': tf.__version__,
        'module_path': tf.__file__,
        'has_raw_ops': hasattr(tf, 'raw_ops'),
        'build_info': build,
        'cuda_build': bool(build.get('is_cuda_build')),
        'rocm_build': bool(build.get('is_rocm_build')),
        'devices': [d.device_type for d in tf.config.list_physical_devices()],
    }
    assert not payload['cuda_build'], 'unexpected CUDA build'
    assert not payload['rocm_build'], 'unexpected ROCm build'
    assert 'CPU' in payload['devices'], payload['devices']
    print(json.dumps(payload))


def save(path):
    module = SoftmaxModule()
    direct = module(X).numpy()
    tf.saved_model.save(module, path)
    x = tf.Variable(X)
    with tf.GradientTape() as tape:
        y = tf.nn.softmax(x, axis=-1)
        loss = tf.reduce_sum(y * y)
    grad = tape.gradient(loss, x)
    print(json.dumps({
        'mode': 'save', 'path': path,
        'direct': direct.tolist(),
        'softmax': y.numpy().tolist(),
        'grad': grad.numpy().tolist(),
    }))


def load(path):
    loaded = tf.saved_model.load(path)
    # The restored plain tf.Module is an AutoTrackable that re-exports its
    # tracked children. `loaded.bias` is the genuinely restored public
    # Variable child; a plain tf.Module SavedModel has no `.variables`
    # collection (that is a Keras / TF1 export property).
    bias = loaded.bias
    assert isinstance(bias, tf.Variable), \
        'restored bias is not a tf.Variable: %r' % type(bias)
    values = bias.numpy()
    assert values.shape == EXPECTED_BIAS.shape, \
        'restored bias shape %r != %r' % (values.shape, EXPECTED_BIAS.shape)
    assert np.allclose(values, EXPECTED_BIAS, rtol=0, atol=BIAS_ATOL), \
        'restored bias %r does not match %r within atol=%g' \
        % (values.tolist(), EXPECTED_BIAS.tolist(), BIAS_ATOL)
    restored = loaded(X)
    print(json.dumps({
        'mode': 'load', 'path': path,
        'restored': restored.numpy().tolist(),
        'bias': values.tolist(),
        'variables': [bias.name],
    }))


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise SystemExit('usage: consumer_check.py {info|save|load} [dir]')
    action = sys.argv[1]
    if action == 'info':
        info()
    elif action == 'save':
        save(sys.argv[2])
    elif action == 'load':
        load(sys.argv[2])
    else:
        raise SystemExit('unknown action: %s' % action)
