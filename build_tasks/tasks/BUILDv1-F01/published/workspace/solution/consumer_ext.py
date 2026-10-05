#!/usr/bin/env python3
"""Build a tiny C++ tensor-add extension with torch.utils.cpp_extension against
the delivered headers, load it and assert semantics.

Binding mechanism: a SINGLE genuine mechanism. ``load_inline`` with
``functions=['add_two']`` generates the one real PYBIND11_MODULE binding (the
module initializer, ``pybind11_init_<name>`` and ``PyInit_<name>``) from the
function signature. The CPP source therefore must NOT contain its own
``PYBIND11_MODULE``: doing both defines the module def, ``PyInit_ext_add_consumer``
and ``pybind11_init_ext_add_consumer`` twice, which g++ reports as redefinition
errors. We write the raw C++ function only and let PyTorch's loader synthesize
the single binding.
"""
import os
import sys
from pathlib import Path


# Raw C++ function only - NO manual PYBIND11_MODULE. load_inline(functions=...)
# generates exactly one module binding for this signature.
CPP = '\n'.join([
    '#include <torch/extension.h>',
    'torch::Tensor add_two(torch::Tensor a, torch::Tensor b) { return a + b; }',
]) + '\n'


def main():
    build_dir = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path('/workspace/consumer/ext_build')
    build_dir.mkdir(parents=True, exist_ok=True)
    os.environ['TORCH_EXTENSIONS_DIR'] = str(build_dir)
    import torch
    from torch.utils.cpp_extension import load_inline

    assert torch.cuda.is_available() is False
    mod = load_inline(
        name='ext_add_consumer',
        cpp_sources=CPP,
        functions=['add_two'],
        extra_cflags=['-O2'],
        build_directory=str(build_dir),
        verbose=True,
    )
    a = torch.tensor([1.0, 2.0, 3.0])
    b = torch.tensor([4.0, 5.0, 6.0])
    out = mod.add_two(a, b)
    assert torch.allclose(out, a + b), out
    # Exact expected values: [1+4, 2+5, 3+6] = [5, 7, 9].
    expected = torch.tensor([5.0, 7.0, 9.0])
    assert torch.equal(out, expected), out
    mod_path = Path(mod.__file__).resolve()
    print('extension module:', mod_path)
    assert str(build_dir) in str(mod_path), mod_path
    print('consumer_ext: OK')


if __name__ == '__main__':
    main()
