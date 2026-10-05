#!/usr/bin/env python3
"""Independent functional consumer: tensor math, analytic gradient,
torch.nn.Linear, state_dict round-trip, and CPU-only assertion. Runs outside
the source tree against the freshly built wheel."""
import sys
import tempfile
from pathlib import Path


def main():
    venv = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
    import torch

    print('torch.__version__ =', torch.__version__)
    print('torch.__file__    =', torch.__file__)
    print(torch.__config__.show())
    if venv is not None:
        assert str(venv) in str(Path(torch.__file__).resolve()), (
            'torch not loaded from the new consumer venv', torch.__file__)
    assert torch.__version__.startswith('2.7'), torch.__version__
    assert torch.cuda.is_available() is False, 'CPU-only build expected'

    a = torch.tensor([[1.0, 2.0], [3.0, 4.0]], requires_grad=True)
    b = torch.tensor([[5.0, 6.0], [7.0, 8.0]])
    c = a @ b
    assert c.grad_fn is not None
    c.sum().backward()
    expected = b.sum(dim=1, keepdim=True).expand_as(a)
    assert torch.allclose(a.grad, expected), (a.grad, expected)
    print('gradient check ok')

    lin = torch.nn.Linear(4, 3)
    x = torch.randn(2, 4)
    y = lin(x)
    assert tuple(y.shape) == (2, 3), y.shape
    y.sum().backward()
    assert lin.weight.grad is not None
    print('nn.Linear check ok')

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / 'sd.pt'
        torch.save(lin.state_dict(), p)
        sd = torch.load(p, weights_only=True)
        lin2 = torch.nn.Linear(4, 3)
        lin2.load_state_dict(sd)
        assert torch.allclose(lin2.weight, lin.weight)
        assert torch.allclose(lin2.bias, lin.bias)
    print('serialization check ok')
    print('consumer_verify: OK')


if __name__ == '__main__':
    main()
