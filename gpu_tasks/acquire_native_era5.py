"""Fetch complete native-grid FCN3 ERA5 fields with the official Earth2Studio source."""
import ast
import hashlib
import json
import resource
from pathlib import Path

resource.setrlimit(resource.RLIMIT_AS, (24 * 2**30, 24 * 2**30))

import earth2studio
import numpy as np
from earth2studio.data import ARCO_ERA5

root = Path('/data/data/zrji/gpu60-native-20261012')
source_file = Path(earth2studio.__file__).parent / 'models/px/fcn3.py'
tree = ast.parse(source_file.read_text())
variables = next(ast.literal_eval(node.value) for node in tree.body
                 if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'VARIABLES' for t in node.targets))
out = root / 'era5_native'
out.mkdir(exist_ok=True)
source = ARCO_ERA5(verbose=False)
records = []
for name, time in [('initial', '2018-01-01T00:00:00'), ('reference_06h', '2018-01-01T06:00:00'),
                   ('reference_12h', '2018-01-01T12:00:00'), ('reference_18h', '2018-01-01T18:00:00'),
                   ('new_initial', '2018-01-02T00:00:00')]:
    target = out / (name + '.nc')
    if not target.exists():
        data = source(np.array([time], dtype='datetime64[ns]'), np.array(variables))
        if data.shape != (1, 72, 721, 1440) or not np.isfinite(data.values).all():
            raise ValueError(f'Incomplete native FCN3 ERA5 fields: {data.shape}')
        data.to_dataset(name='fields').to_netcdf(target)
    sha = hashlib.sha256(target.read_bytes()).hexdigest()
    records.append({'file': target.name, 'time': time, 'bytes': target.stat().st_size, 'sha256': sha})
    print(name, time, target.stat().st_size, flush=True)
(out / 'source_lock.json').write_text(json.dumps({'source': source.ARCO_PATH,
    'api': 'Earth2Studio ARCO_ERA5', 'variables': variables, 'shape': [1, 72, 721, 1440],
    'files': records}, indent=2) + '\n')
