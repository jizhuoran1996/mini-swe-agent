"""Thin interface to the locked NVIDIA CorrDiff generator and checkpoints."""
import hashlib
import ast
import json
from pathlib import Path
import sys
from types import SimpleNamespace


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def source_generator(inputs):
    import nvtx
    import torch
    import tqdm
    from modulus.distributed import DistributedManager
    from modulus.utils.generative import ablation_sampler, StackedRandomGenerator
    source = inputs / 'upstream/modulus/examples/generative/corrdiff'
    path = source / 'generate.py'
    tree = ast.parse(path.read_text(), filename=str(path))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in ('generate', 'unet_regression')]
    assert len(nodes) == 2, 'locked upstream generator interface changed'
    namespace = {'torch': torch, 'tqdm': tqdm, 'nvtx': nvtx, 'DistributedManager': DistributedManager,
                 'StackedRandomGenerator': StackedRandomGenerator, 'ablation_sampler': ablation_sampler}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return SimpleNamespace(generate=namespace['generate'], unet_regression=namespace['unet_regression'])


def models(inputs):
    from modulus import Module
    from modulus.distributed import DistributedManager
    import torch
    assert torch.cuda.is_available(), 'genuine CUDA execution required'
    if not DistributedManager.is_initialized():
        DistributedManager.initialize()
    regression = Module.from_checkpoint(str(inputs / 'corrdiff/regression.mdlus')).to('cuda').eval()
    diffusion = Module.from_checkpoint(str(inputs / 'corrdiff/diffusion.mdlus')).to('cuda').eval()
    return regression, diffusion


def predict(inputs, condition, seed, regression, diffusion, generator):
    import torch
    low_resolution = torch.tensor(condition[None], dtype=torch.float32, device='cuda')
    mean = generator.generate(regression, [0], None, 1, img_lr=low_resolution, pretext='reg', num_steps=2)
    residual = generator.generate(
        diffusion, [seed], None, 1, sampling_method='deterministic', img_lr=low_resolution,
        pretext='gen', num_steps=8, solver='euler', discretization='edm', schedule='linear', scaling='none', S_churn=0,
    )
    result = (mean + residual)[0].float().cpu().numpy()
    torch.cuda.synchronize()
    return result


def physical(normalized, metadata):
    import numpy as np
    return normalized * np.array(metadata['output_scale'], np.float32)[:, None, None] + np.array(metadata['output_center'], np.float32)[:, None, None]
