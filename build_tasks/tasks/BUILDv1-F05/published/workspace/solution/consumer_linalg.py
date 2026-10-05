#!/usr/bin/env python3
"""Independent functional consumer for the freshly built NumPy wheel.
Run with the consumer virtualenv interpreter, outside the source tree."""
import json
import os
import subprocess
import sys
import tempfile

import numpy as np


def main():
    info = {}
    np_file = os.path.abspath(np.__file__)
    assert "/workspace/src" not in np_file, "imported from the source tree: %s" % np_file
    info["numpy_version"] = np.__version__
    info["numpy_file"] = np_file
    info["numpy_include"] = np.get_include()
    assert os.path.isfile(os.path.join(np.get_include(), "numpy", "arrayobject.h"))

    import numpy._core._multiarray_umath as multiarray
    info["multiarray_umath"] = os.path.abspath(multiarray.__file__)

    try:
        config = np.show_config(mode="dicts")
        blas = config.get("Build Dependencies", {}).get("blas", {})
    except Exception as exc:  # noqa: BLE001
        raise SystemExit("cannot confirm BLAS binding: %r" % (exc,))
    assert blas, "no BLAS recorded in the build configuration"
    info["blas"] = blas

    rng = np.random.default_rng(12345)
    a = rng.standard_normal((200, 200))
    b = rng.standard_normal(200)
    x = np.linalg.solve(a, b)
    residual = float(np.linalg.norm(a @ x - b))
    assert residual < 1e-8, residual
    info["solve_residual"] = residual

    y = rng.standard_normal(4096)
    fft_err = float(np.max(np.abs(np.fft.irfft(np.fft.rfft(y), n=y.size) - y)))
    assert fft_err < 1e-10, fft_err
    info["fft_roundtrip_max_err"] = fft_err

    first = np.random.default_rng(7).standard_normal(5).tolist()
    second = np.random.default_rng(7).standard_normal(5).tolist()
    assert first == second
    info["rng_seed7"] = first

    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "sample.npy")
    np.save(path, a[:3, :3])
    reloaded = subprocess.check_output(
        [sys.executable, "-c",
         "import numpy as np, sys; x = np.load(sys.argv[1]); print(x.shape, float(x.sum()))",
         path], text=True).strip()
    info["npy_reload"] = reloaded
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
