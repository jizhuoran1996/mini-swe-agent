#!/usr/bin/env python3
"""Load and exercise the freshly compiled NumPy C-API extension module."""
import json
import sys

import numpy as np


def main():
    sys.path.insert(0, sys.argv[1])
    import consumer_cext

    values = np.arange(6.0).reshape(2, 3)
    total = consumer_cext.cext_sum(values)
    assert total == 15.0, total
    result = {"cext_sum": total, "numpy_file": np.__file__,
              "module_file": consumer_cext.__file__}
    assert "/workspace/src" not in np.__file__
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
