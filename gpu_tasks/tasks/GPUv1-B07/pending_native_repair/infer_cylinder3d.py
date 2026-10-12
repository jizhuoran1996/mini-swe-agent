#!/usr/bin/env python3
# Convenience copy of the inference helper that `main.py run` emits to
# `output/infer_cylinder3d.py`.  Kept alongside the source for review.
# See solution/main.py INFER_HELPER for the canonical version.
import sys
from pathlib import Path
_here = Path(__file__).resolve()
print("This file is a review copy. The canonical inference helper is written by\n"
      "`python solution/main.py run --input input --output output` into\n"
      f"    output/infer_cylinder3d.py\n"
      "(generated from solution/main.py INFER_HELPER).")
sys.exit(0)
