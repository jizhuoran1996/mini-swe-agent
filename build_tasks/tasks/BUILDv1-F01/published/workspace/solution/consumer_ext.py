#!/usr/bin/env python3
"""Build a tiny C++ tensor-add extension with torch.utils.cpp_extension
against the delivered headers, load it and assert semantics."""
import os
import sys
from pathlib import Path


CPP = '\n'.join([
    '#include <torch/extension.h>',
    'torch::Tensor add_two(torch::Tensor a, torch::Tensor b) { return a + b; }',
    'PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) { m.def("add_two", &add_two); }',
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
    mod_path = Path(mod.__file__).resolve()
    print('extension module:', mod_path)
    assert str(build_dir) in str(mod_path), mod_path
    print('consumer_ext: OK')


if __name__ == '__main__':
    main()
