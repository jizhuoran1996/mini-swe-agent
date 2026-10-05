#!/usr/bin/env python3
"""Independent functional consumer for a freshly source-built pandas wheel.

"build"  : prove the loaded native extensions come from the wheel, run the
           grouping / tz-aware index / missing-value workload and persist it.
"reload" : re-derive the same results in a fresh process from the files only.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def check_build_origin():
    pd_file = Path(pd.__file__).resolve()
    if '/workspace/src' in str(pd_file):
        raise AssertionError(f'pandas was imported from the source tree: {pd_file}')
    import pandas._libs as libs
    libdir = Path(libs.__file__).resolve().parent
    native = sorted(p.name for p in libdir.glob('*.so'))
    if not native:
        raise AssertionError('no compiled extensions found under pandas._libs')
    return {'pandas_file': str(pd_file), 'libdir': str(libdir),
            'native_libs': native, 'pandas_version': pd.__version__}


def dataset():
    frame = pd.DataFrame({
        'key': ['a', 'b', 'a', 'b', 'a', 'b', 'c'],
        'ts': pd.to_datetime([
            '2020-01-01', '2020-01-02', '2020-01-03',
            '2020-01-01', '2020-01-02', '2020-01-03', '2020-01-05',
        ]).tz_localize('UTC'),
        'val': [1.0, np.nan, 3.0, 4.0, np.nan, 6.0, np.nan],
    })
    return frame.set_index('ts').sort_index()


def build(outdir):
    origin = check_build_origin()
    frame = dataset()
    assert str(frame.index.tz) == 'UTC', 'timezone-aware index lost'
    grouped = frame.groupby('key')['val'].agg(['sum', 'count', 'mean']).sort_index()
    assert grouped.loc['a', 'sum'] == 4.0 and grouped.loc['a', 'count'] == 2
    assert grouped.loc['b', 'sum'] == 10.0 and grouped.loc['b', 'count'] == 2
    assert grouped.loc['c', 'count'] == 0 and grouped.loc['c', 'sum'] == 0.0
    assert list(grouped.index) == ['a', 'b', 'c']
    frame.to_csv(outdir / 'table.csv')
    grouped.to_csv(outdir / 'grouped.csv')
    (outdir / 'expect.json').write_text(json.dumps({
        'grouped': grouped.to_dict(),
        'shape': list(frame.shape),
        'tz': str(frame.index.tz),
        'origin': origin,
    }, indent=2) + '\n')
    print(f'consumer build ok: groups={grouped.shape} libs={len(origin["native_libs"])}'
          f' pandas={origin["pandas_version"]}')


def reload(outdir):
    origin = check_build_origin()
    expect = json.loads((outdir / 'expect.json').read_text())
    frame = pd.read_csv(outdir / 'table.csv')
    frame['ts'] = pd.to_datetime(frame['ts'], utc=True)
    frame = frame.set_index('ts').sort_index()
    assert list(frame.shape) == expect['shape'], 'reloaded shape mismatch'
    assert str(frame.index.tz) == 'UTC', 'reloaded index lost timezone'
    grouped = frame.groupby('key')['val'].agg(['sum', 'count', 'mean']).sort_index()
    for key, value in expect['grouped']['sum'].items():
        assert abs(grouped.loc[key, 'sum'] - value) < 1e-9, f'sum mismatch for {key}'
    for key, value in expect['grouped']['count'].items():
        assert abs(grouped.loc[key, 'count'] - value) < 1e-9, f'count mismatch for {key}'
    assert abs(grouped.loc['b', 'mean'] - 5.0) < 1e-9
    print(f'consumer reload ok: tz={frame.index.tz} libs={len(origin["native_libs"])}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['build', 'reload'])
    parser.add_argument('--outdir', required=True)
    args = parser.parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    {'build': build, 'reload': reload}[args.phase](outdir)


if __name__ == '__main__':
    main()
