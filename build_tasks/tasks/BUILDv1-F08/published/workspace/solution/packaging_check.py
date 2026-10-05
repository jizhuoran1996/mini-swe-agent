#!/usr/bin/env python3
"""Confirm that an installed xgboost resolves its native library to this build."""
import json
import sys

import xgboost as xgb


lib = str(xgb.core._LIB)
info = {'lib': lib, 'version': xgb.__version__}
try:
    info['build_info'] = xgb.build_info()
except Exception as exc:  # pragma: no cover - informational
    info['build_info_error'] = str(exc)
assert sys.argv[1] not in lib, 'loaded a stale preinstalled xgboost'
print(json.dumps(info, sort_keys=True))
