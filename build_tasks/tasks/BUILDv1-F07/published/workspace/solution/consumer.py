#!/usr/bin/env python3
"""Independent numerical consumer for the freshly source-built pandas wheel.

"smoke"  : tiny import/groupby probe so a native-extension failure is caught
           with clear evidence before the full workload runs.
"build"  : prove the loaded extensions come from the installed wheel (not the
           source tree), run the tz-aware groupby / missing-value / join
           workload, and persist it plus the expected numbers.
"reload" : a fresh process re-derives every number from the persisted file.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


def _j(v):
    """JSON-safe float (None for NaN)."""
    f = float(v)
    return None if math.isnan(f) else f


def check_origin():
    pd_file = Path(pd.__file__).resolve()
    if '/workspace/src' in str(pd_file):
        raise AssertionError(f'pandas imported from the source tree: {pd_file}')
    import pandas._libs as libs
    libdir = Path(libs.__file__).resolve().parent
    native = sorted(p.name for p in libdir.glob('*.so'))
    if not native:
        raise AssertionError('no compiled extensions found under pandas._libs')
    return {'pandas_file': str(pd_file), 'libdir': str(libdir), 'native_libs': native,
            'pandas_version': pd.__version__, 'numpy_version': np.__version__}


def _parquet():
    try:
        import pyarrow  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def dataset():
    frame = pd.DataFrame({
        'key': ['a', 'b', 'a', 'b', 'a', 'b', 'c'],
        'ts': pd.to_datetime([
            '2020-01-01', '2020-01-02', '2020-01-03', '2020-01-01',
            '2020-01-02', '2020-01-03', '2020-01-05',
        ]).tz_localize('UTC'),
        'val': [1.0, np.nan, 3.0, 4.0, np.nan, 6.0, np.nan],
    })
    return frame.set_index('ts').sort_index()


def _grouped(frame):
    return frame.groupby('key')['val'].agg(['sum', 'count', 'mean']).sort_index()


def _merged(grouped):
    lookup = pd.DataFrame({'key': ['a', 'b', 'c'],
                           'weight': [1.0, 2.0, 3.0]}).set_index('key')
    return grouped.join(lookup, how='left')


def _as_dict(grouped):
    return {col: {str(k): _j(v) for k, v in grouped[col].items()}
            for col in grouped.columns}


def smoke(outdir):
    origin = check_origin()
    grouped = _grouped(dataset())
    assert list(grouped.index) == ['a', 'b', 'c']
    assert abs(grouped.loc['b', 'mean'] - 5.0) < 1e-9
    print(f'consumer smoke ok: pandas={origin["pandas_version"]} '
          f'numpy={origin["numpy_version"]} libs={len(origin["native_libs"])}')


def build(outdir):
    origin = check_origin()
    frame = dataset()
    assert str(frame.index.tz) == 'UTC', 'timezone-aware index lost'
    assert frame.index.is_monotonic_increasing, 'index not sorted'
    grouped = _grouped(frame)
    assert grouped.loc['a', 'sum'] == 4.0 and grouped.loc['a', 'count'] == 2
    assert grouped.loc['b', 'sum'] == 10.0 and grouped.loc['b', 'count'] == 2
    assert grouped.loc['c', 'count'] == 0 and grouped.loc['c', 'sum'] == 0.0
    assert abs(grouped.loc['b', 'mean'] - 5.0) < 1e-9
    assert list(grouped.index) == ['a', 'b', 'c']
    merged = _merged(grouped)
    assert merged.loc['c', 'weight'] == 3.0, 'merge result wrong'
    weighted = float((merged['sum'] * merged['weight']).sum())
    assert abs(weighted - 24.0) < 1e-9, f'weighted sum mismatch: {weighted}'
    payload = {'shape': list(frame.shape), 'tz': str(frame.index.tz),
               'grouped': _as_dict(grouped), 'weighted': weighted,
               'numpy_version': origin['numpy_version'], 'origin': origin}
    flat = frame.reset_index()
    if _parquet():
        flat.to_parquet(outdir / 'table.parquet')
        payload['storage'] = 'parquet'
    else:
        flat.to_csv(outdir / 'table.csv', index=False)
        payload['storage'] = 'csv'
    (outdir / 'expect.json').write_text(json.dumps(payload, indent=2) + '\n')
    print(f'consumer build ok: groups={grouped.shape} weighted={weighted} '
          f'storage={payload["storage"]} libs={len(origin["native_libs"])} '
          f'pandas={origin["pandas_version"]} numpy={origin["numpy_version"]}')


def reload(outdir):
    origin = check_origin()
    expect = json.loads((outdir / 'expect.json').read_text())
    assert origin['numpy_version'] == expect['numpy_version'], (
        f'numpy changed between write and reload: {expect["numpy_version"]} '
        f'vs {origin["numpy_version"]}')
    if expect['storage'] == 'parquet':
        frame = pd.read_parquet(outdir / 'table.parquet')
    else:
        frame = pd.read_csv(outdir / 'table.csv')
    frame['ts'] = pd.to_datetime(frame['ts'], utc=True)
    frame = frame.set_index('ts').sort_index()
    assert list(frame.shape) == expect['shape'], 'reloaded shape mismatch'
    assert str(frame.index.tz) == expect['tz'], 'reloaded index lost timezone'
    assert frame.index.is_monotonic_increasing, 'reloaded index unsorted'
    grouped = _grouped(frame)
    assert list(grouped.index) == ['a', 'b', 'c'], 'reloaded group set changed'
    for key, value in expect['grouped']['sum'].items():
        if value is None:
            continue
        assert abs(grouped.loc[key, 'sum'] - value) < 1e-9, f'sum mismatch for {key}'
    for key, value in expect['grouped']['count'].items():
        if value is None:
            continue
        assert abs(grouped.loc[key, 'count'] - value) < 1e-9, f'count mismatch for {key}'
    assert abs(grouped.loc['b', 'mean'] - 5.0) < 1e-9
    merged = _merged(grouped)
    weighted = float((merged['sum'] * merged['weight']).sum())
    assert abs(weighted - expect['weighted']) < 1e-9, 'weighted merge mismatch'
    assert abs(weighted - 24.0) < 1e-9, 'weighted merge no longer 24'
    print(f'consumer reload ok: tz={frame.index.tz} weighted={weighted} '
          f'libs={len(origin["native_libs"])} numpy={origin["numpy_version"]}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['smoke', 'build', 'reload'])
    parser.add_argument('--outdir', required=True)
    args = parser.parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    {'smoke': smoke, 'build': build, 'reload': reload}[args.phase](outdir)


if __name__ == '__main__':
    main()
