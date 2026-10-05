#!/usr/bin/env python3
"""Independent functional consumer for the freshly built jax/jaxlib wheels."""
import sys
import numpy as np
import jax
import jax.numpy as jnp


def main():
    assert jax.default_backend() == 'cpu', jax.default_backend()
    devices = jax.devices()
    assert devices and all(d.platform == 'cpu' for d in devices), devices

    key = jax.random.PRNGKey(0)
    x = jax.random.normal(key, (64, 16))
    y = jax.random.normal(key, (16, 8))

    @jax.jit
    def f(a, b):
        return jnp.dot(a, b) + jnp.sin(a).sum()

    out = f(x, y)
    out.block_until_ready()
    expected = np.asarray(x) @ np.asarray(y) + np.sin(np.asarray(x)).sum()
    np.testing.assert_allclose(np.asarray(out), expected, rtol=1e-5, atol=1e-6)

    vout = jax.vmap(lambda row: jnp.sum(jnp.sin(row)))(x)
    vout.block_until_ready()
    np.testing.assert_allclose(np.asarray(vout), np.sin(np.asarray(x)).sum(axis=1),
                               rtol=1e-5, atol=1e-6)

    grad = jax.grad(lambda w: jnp.sum(w ** 2))(x)
    grad.block_until_ready()
    np.testing.assert_allclose(np.asarray(grad), 2.0 * np.asarray(x), rtol=1e-5, atol=1e-6)

    x2 = jax.random.normal(key, (128, 32))
    y2 = jax.random.normal(key, (32, 4))
    out2 = f(x2, y2)
    out2.block_until_ready()
    expected2 = np.asarray(x2) @ np.asarray(y2) + np.sin(np.asarray(x2)).sum()
    np.testing.assert_allclose(np.asarray(out2), expected2, rtol=1e-5, atol=1e-6)

    print('CONSUMER_OK')


if __name__ == '__main__':
    sys.exit(main())
