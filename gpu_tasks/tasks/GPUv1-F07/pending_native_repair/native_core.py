"""Native Earth2Studio FCN3 ensemble, including the model's correlated noise restart state."""
import hashlib
import json
from collections import OrderedDict
from pathlib import Path

import numpy as np
import torch
import xarray as xr

OUTPUTS = ['u10m', 'v10m', 't2m', 'msl', 'tcwv']


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 << 20), b''):
            h.update(block)
    return h.hexdigest()


def device_tree(value, device):
    if isinstance(value, torch.Tensor):
        return value.to(device)
    if isinstance(value, list):
        return [device_tree(x, device) for x in value]
    if isinstance(value, tuple):
        return tuple(device_tree(x, device) for x in value)
    return value


def model_from_inputs(inputs):
    from earth2studio.models.px import FCN3
    from makani.models.model_package import LocalPackage
    return FCN3.load_model(LocalPackage(str(inputs / 'fcn3_checkpoint'))).cuda().eval()


def forecast(inputs, output, resume=False, initial='era5_initial.nc', seed=20240211):
    output.mkdir(parents=True, exist_ok=True)
    config = json.loads((inputs / 'forecast_config.json').read_text())
    model = model_from_inputs(inputs)
    channels = list(model.input_coords()['variable'])
    selected = [channels.index(name) for name in OUTPUTS]
    frames, states = [], []
    for member in range(config['members']):
        checkpoint = output / f'member_{member}_state.pt'
        if resume:
            state = torch.load(checkpoint, map_location='cpu', weights_only=False)
            if state['package_sha256'] != digest(inputs / 'fcn3_checkpoint/training_checkpoints/best_ckpt_mp0.tar'):
                raise ValueError('Original model package changed')
            x = state['x'].cuda()
            coordinates = state['coordinates']
            model.set_rng(seed=state['seed'], reset=False)
            preprocessor = model.model.model.preprocessor
            for gpu, name in ((True, 'gpu_rng'), (False, 'cpu_rng')):
                preprocessor.get_internal_rng(gpu=gpu).set_state(state[name])
            model._internal_noise_states = device_tree(state['noise_states'], 'cuda')
            torch.set_rng_state(state['torch_rng'])
            torch.cuda.set_rng_state_all(state['cuda_rng'])
            member_frames = list(np.load(output / f'member_{member}_forecast.npy'))
            steps = state['steps'] + 1
            completed = state['steps']
        else:
            if checkpoint.exists():
                raise FileExistsError('Use resume for existing forecast state')
            with xr.open_dataset(inputs / initial) as data:
                fields = data['fields'].sel(variable=channels).transpose('time', 'variable', 'lat', 'lon')
                values = fields.values.astype('float32')
                initial_time = fields.time.values.copy()
            if values.shape != (1, 72, 721, 1440):
                raise ValueError('Original FCN3 grid and all prognostic channels are required')
            x = torch.from_numpy(values).cuda()[None, :, None]
            coordinates = OrderedDict(batch=np.array([member]), time=initial_time,
                lead_time=np.array([np.timedelta64(0, 'h')]), variable=np.array(channels),
                lat=np.linspace(90, -90, 721), lon=np.arange(1440) * 0.25)
            model.set_rng(seed=seed + member, reset=True)
            model._reset_internal_state(1, 1)
            member_frames = []
            completed, steps = 0, config['steps']
        with torch.inference_mode():
            for _ in range(completed, steps):
                x, coordinates = model._forward(x, coordinates)
                torch.cuda.synchronize()
                member_frames.append(x[0, 0, 0, selected].float().cpu().numpy())
        preprocessor = model.model.model.preprocessor
        state = {'x': x.cpu(), 'coordinates': coordinates, 'steps': steps,
            'seed': seed + member, 'noise_states': device_tree(model._internal_noise_states, 'cpu'),
            'gpu_rng': preprocessor.get_internal_rng(gpu=True).get_state(),
            'cpu_rng': preprocessor.get_internal_rng(gpu=False).get_state(),
            'torch_rng': torch.get_rng_state(), 'cuda_rng': torch.cuda.get_rng_state_all(),
            'package_sha256': digest(inputs / 'fcn3_checkpoint/training_checkpoints/best_ckpt_mp0.tar')}
        torch.save(state, checkpoint)
        np.save(output / f'member_{member}_forecast.npy', np.stack(member_frames))
        frames.append(np.stack(member_frames))
        states.append({'member': member, 'seed': state['seed'], 'steps': steps,
                       'state_sha256': digest(checkpoint)})
    array = np.stack(frames)
    if not np.isfinite(array).all():
        raise ValueError('Non-finite native model forecast')
    result = xr.DataArray(array, dims=('member', 'lead', 'variable', 'lat', 'lon'),
        coords={'member': np.arange(config['members']), 'lead': np.arange(1, steps + 1) * 6,
                'variable': OUTPUTS, 'lat': np.linspace(90, -90, 721), 'lon': np.arange(1440) * 0.25})
    result.to_dataset(name='forecast').to_netcdf(output / 'forecast.nc')
    report = {'task_id': 'GPUv1-F07', 'complete': True, 'scale': 'native_debug',
        'backend': 'Official Earth2Studio FCN3 / Makani original package',
        'grid': [721, 1440], 'input_channels': channels, 'output_channels': OUTPUTS,
        'members': states, 'resume': resume, 'initial': initial,
        'ensemble_variance': array.var(axis=0).mean(axis=(0, 2, 3)).tolist(),
        'device': torch.cuda.get_device_name(0), 'reference_large_tested': False}
    (output / 'run.json').write_text(json.dumps(report, indent=2) + '\n')
    return report
