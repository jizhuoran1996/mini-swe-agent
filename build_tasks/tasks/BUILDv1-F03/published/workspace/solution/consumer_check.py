#!/usr/bin/env python3
"""Independent functional consumer for the freshly built jax/jaxlib wheels.

Runs from a fresh venv outside the source tree.  The primary assertions use
float64 arithmetic (the caller exports ``JAX_ENABLE_X64=1``) so that a JIT'd
matmul can be compared to an independent NumPy float64 oracle under the
originally strict ``rtol=1e-5, atol=1e-6`` tolerance.  The same seed, shapes,
and operations as the float32 consumer are preserved by generating float32
samples and casting them to float64 (the cast is exact, so the input values are
unchanged).  A separate float32 diagnostic records the observed rounding error
against a mathematically derived forward bound; it is reported, not smuggled
into the strict tolerance.
"""
import sys
import numpy as np
import jax
import jax.numpy as jnp


def _as_f64(a):
    return np.asarray(a, dtype=np.float64)


def main():
    assert jax.config.jax_enable_x64, 'consumer requires JAX_ENABLE_X64=1'
    assert jax.default_backend() == 'cpu', jax.default_backend()
    devices = jax.devices()
    assert devices and all(d.platform == 'cpu' for d in devices), devices

    key = jax.random.PRNGKey(0)
    # Same seed/shape as before; cast to float64 for exactness-preserving compare.
    x32 = jax.random.normal(key, (64, 16))
    y32 = jax.random.normal(key, (16, 8))
    x = jnp.asarray(x32, dtype=jnp.float64)
    y = jnp.asarray(y32, dtype=jnp.float64)

    @jax.jit
    def f(a, b):
        return jnp.dot(a, b) + jnp.sin(a).sum()

    out = f(x, y)
    out.block_until_ready()
    expected = _as_f64(x) @ _as_f64(y) + np.sin(_as_f64(x)).sum()
    np.testing.assert_allclose(_as_f64(out), expected, rtol=1e-5, atol=1e-6)

    vout = jax.vmap(lambda row: jnp.sum(jnp.sin(row)))(x)
    vout.block_until_ready()
    np.testing.assert_allclose(_as_f64(vout), np.sin(_as_f64(x)).sum(axis=1),
                               rtol=1e-5, atol=1e-6)

    grad = jax.grad(lambda w: jnp.sum(w ** 2))(x)
    grad.block_until_ready()
    np.testing.assert_allclose(_as_f64(grad), 2.0 * _as_f64(x),
                               rtol=1e-5, atol=1e-6)

    # New input shape: exercises recompilation and the delivered native runtime.
    x2_32 = jax.random.normal(key, (128, 32))
    y2_32 = jax.random.normal(key, (32, 4))
    out2 = f(jnp.asarray(x2_32, dtype=jnp.float64),
             jnp.asarray(y2_32, dtype=jnp.float64))
    out2.block_until_ready()
    expected2 = _as_f64(x2_32) @ _as_f64(y2_32) + np.sin(_as_f64(x2_32)).sum()
    np.testing.assert_allclose(_as_f64(out2), expected2, rtol=1e-5, atol=1e-6)

    # ----------------------------------------------------------------
    # Float32 rounding diagnostic: derive a mathematically valid forward
    # error bound for the length-K finite-precision dot product
    #     |fl(x . y) - x . y| <= gamma_K * sum_j |x_j * y_j|,
    #     gamma_K = K * eps / (1 - K * eps),  eps = 2**-24 for float32.
    # Compare against a float64 oracle on the SAME float32 inputs; this is
    # reported separately and does not use the strict float64 tolerance.
    # ----------------------------------------------------------------
    f32_dot = jnp.dot(x32, y32)
    f32_dot.block_until_ready()
    xF = _as_f64(x32)
    yF = _as_f64(y32)
    ref_dot = xF @ yF
    observed = float(np.max(np.abs(_as_f64(f32_dot) - ref_dot)))
    K = float(xF.shape[1])
    eps = 2.0 ** -24
    gamma_K = K * eps / (1.0 - K * eps)
    per_entry = gamma_K * np.abs(xF[:, :, None] * yF[None, :, :]).sum(axis=1)
    bound = float(per_entry.max())
    print(f'float32_dot_max_abs_err={observed:.3e} derived_bound={bound:.3e} '
          f'K={int(K)} eps=2**-24')
    assert observed <= bound, (observed, bound)

    print('CONSUMER_OK')


if __name__ == '__main__':
    sys.exit(main())
