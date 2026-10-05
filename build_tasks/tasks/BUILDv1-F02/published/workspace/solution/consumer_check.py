#!/usr/bin/env python3
"""Independent TensorFlow consumer run from outside the source tree.

    python consumer_check.py info
    python consumer_check.py save <dir>
    python consumer_check.py load <dir>

`info` asserts the newly installed wheel is a CPU-only build and that the native
extension actually loads. `save`/`load` run in separate processes to prove the
SavedModel and its variables reload after the producing process has exited.
"""
import json
import sys

import tensorflow as tf


class SoftmaxModule(tf.Module):
    def __init__(self):
        super().__init__()
        self.bias = tf.Variable([0.1, -0.2, 0.3], dtype=tf.float32, name='bias')

    @tf.function
    def __call__(self, x):
        return tf.nn.softmax(x + self.bias)


X = tf.constant([[0.5, -1.0, 2.0], [1.0, 0.0, -1.0]], dtype=tf.float32)


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
    restored = loaded(X)
    print(json.dumps({
        'mode': 'load', 'path': path,
        'restored': restored.numpy().tolist(),
        'variables': [v.name for v in loaded.variables],
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
