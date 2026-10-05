#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import random
import sys
import time
from pathlib import Path

EX_CONFIG = 78


def _install_huggingface_hub_shim():
    """Patch huggingface_hub so that diffusers.pipelines.pipeline_utils can
    be imported against the installed huggingface_hub version, which may be
    missing newer symbols such as CachedRepoTreeNotFoundError and
    get_cached_repo_tree.  All shims are no-ops when the target symbol is
    already present."""
    try:
        import huggingface_hub as _hf
    except Exception:
        return
    try:
        import huggingface_hub.errors as _hf_errors
    except Exception:
        _hf_errors = None

    # ---- 1) CachedRepoTreeNotFoundError -------------------------------------
    try:
        err_cls = getattr(_hf_errors, 'CachedRepoTreeNotFoundError', None)
    except Exception:
        err_cls = None
    if err_cls is None:
        class CachedRepoTreeNotFoundError(Exception):  # noqa: D401
            """Raised when a repository tree is not found in the local cache."""
            def __init__(self, message=None, *args, **kwargs):
                super().__init__(message if message is not None else 'Repository tree not found in cache')
                self.message = message

        if _hf_errors is not None:
            try:
                _hf_errors.CachedRepoTreeNotFoundError = CachedRepoTreeNotFoundError
            except Exception:
                pass
        try:
            _hf.CachedRepoTreeNotFoundError = CachedRepoTreeNotFoundError
        except Exception:
            pass
        err_cls = CachedRepoTreeNotFoundError

    # Also mirror the error into huggingface_hub.hf_api and _snapshot_download
    # in case those modules are imported directly by diffusers.
    try:
        import importlib as _importlib
        for _mod_name in ('huggingface_hub.hf_api', 'huggingface_hub._snapshot_download'):
            try:
                _m = _importlib.import_module(_mod_name)
                if not hasattr(_m, 'CachedRepoTreeNotFoundError'):
                    try:
                        _m.CachedRepoTreeNotFoundError = err_cls
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        pass

    # ---- 2) get_cached_repo_tree --------------------------------------------
    if hasattr(_hf, 'get_cached_repo_tree'):
        return

    class _CachedEntry(object):
        __slots__ = ('path', 'file_path', 'file_name', 'blob_path', 'size', 'is_dir')

        def __init__(self, path, file_path, blob_path=None, size=None):
            self.path = path
            self.file_path = str(file_path)
            self.file_name = os.path.basename(str(path))
            self.blob_path = blob_path
            self.size = size
            self.is_dir = False

        def __repr__(self):
            return f'<CachedEntry {self.path!r}>'

    def get_cached_repo_tree(repo_id, repo_type=None, cache_dir=None,
                             revision=None, token=None, **kwargs):
        try:
            from huggingface_hub import scan_cache_dir
        except Exception:
            return []
        try:
            cache_info = scan_cache_dir(cache_dir)
        except Exception:
            return []
        target = str(repo_id)
        wants = repo_type or 'model'
        entries = []
        for repo in getattr(cache_info, 'repos', []):
            if getattr(repo, 'repo_id', None) != target:
                continue
            if getattr(repo, 'repo_type', 'model') != wants:
                continue
            for rev in getattr(repo, 'revisions', []):
                if revision and getattr(rev, 'commit_hash', None) != revision and getattr(rev, 'ref', None) != revision:
                    continue
                snapshot = getattr(rev, 'snapshot_path', None)
                for f in getattr(rev, 'files', []):
                    fp = str(getattr(f, 'file_path', ''))
                    if snapshot and fp:
                        try:
                            rel = os.path.relpath(fp, str(snapshot)).replace(os.sep, '/')
                        except Exception:
                            rel = os.path.basename(fp)
                    else:
                        rel = os.path.basename(fp) if fp else ''
                    blob = getattr(f, 'blob_path', None)
                    entries.append(_CachedEntry(rel, fp,
                                                blob_path=str(blob) if blob is not None else None,
                                                size=getattr(f, 'size', None)))
        return entries

    try:
        _hf.get_cached_repo_tree = get_cached_repo_tree
    except Exception:
        pass
    try:
        import importlib as _importlib
        for _mod_name in ('huggingface_hub.hf_api', 'huggingface_hub._snapshot_download'):
            try:
                _m = _importlib.import_module(_mod_name)
                if not hasattr(_m, 'get_cached_repo_tree'):
                    try:
                        _m.get_cached_repo_tree = get_cached_repo_tree
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        pass


# Install the shim as early as possible so any later diffusers import works.
_install_huggingface_hub_shim()


def sha256_file(path, chunk=1024 * 1024):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(chunk), b''):
            h.update(b)
    return h.hexdigest()


def read_jsonl(path):
    reqs = []
    with open(path, 'r', encoding='utf-8') as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception as e:
                raise ValueError(f'Invalid JSON at {path}:{line_no}: {e}')
            if not isinstance(obj, dict):
                raise ValueError(f'Request at {path}:{line_no} is not an object')
            reqs.append(obj)
    return reqs


def get_first(d, keys, default=None):
    for k in keys:
        if k in d and d[k] not in (None, ''):
            return d[k]
    return default


def resolve_path(base, p):
    if os.path.isabs(p):
        return p
    return os.path.join(base, p)


def resolve_input_path(base, rel, subdir):
    p = Path(resolve_path(str(base), str(rel)))
    if p.exists():
        return p
    if not os.path.isabs(str(rel)):
        for cand in [Path(base) / subdir / str(rel), Path(base) / subdir / f'{rel}.png', Path(base) / f'{rel}.png']:
            if cand.exists():
                return cand
    return p


def safe_id(s):
    return str(s).replace('/', '_').replace(chr(92), '_').replace(':', '_')


def cmd_doctor(args):
    missing = []
    base = Path(args.input)
    report = {'input': str(base), 'missing': missing}
    if not base.is_dir():
        missing.append(f'input directory missing: {base}')
    for name in ['manifest.json', 'requests.jsonl']:
        p = base / name
        if not p.exists():
            missing.append(f'missing input file: {p}')
    manifest = None
    if (base / 'manifest.json').exists():
        try:
            manifest = json.loads((base / 'manifest.json').read_text(encoding='utf-8'))
            report['manifest'] = manifest
            req_hash = manifest.get('files', {}).get('requests.jsonl')
            if req_hash:
                actual = sha256_file(base / 'requests.jsonl')
                if actual != req_hash:
                    missing.append(f'requests.jsonl sha256 mismatch: {actual} != {req_hash}')
        except Exception as e:
            missing.append(f'cannot parse manifest.json: {e}')
    reqs = []
    if (base / 'requests.jsonl').exists():
        try:
            reqs = read_jsonl(base / 'requests.jsonl')
            report['request_count'] = len(reqs)
        except Exception as e:
            missing.append(f'cannot parse requests.jsonl: {e}')
    for i, req in enumerate(reqs):
        rid = get_first(req, ['id', 'image_id', 'name', 'key'], str(i))
        img = get_first(req, ['image', 'input_image', 'image_path', 'image_file', 'corrupted_image', 'file'], f'images/{rid}.png')
        msk = get_first(req, ['mask', 'mask_image', 'mask_path', 'inpainting_mask'], f'masks/{rid}.png')
        for label, rel, sub in [('image', img, 'images'), ('mask', msk, 'masks')]:
            fp = resolve_input_path(base, rel, sub)
            if not fp.exists():
                missing.append(f'request {rid}: missing {label} file: {fp}')
    import importlib.util
    for dep in ['torch', 'diffusers', 'transformers', 'numpy', 'PIL', 'safetensors']:
        if importlib.util.find_spec(dep) is None:
            missing.append(f'missing Python dependency: {dep}')
    report['dependencies'] = {}
    if importlib.util.find_spec('torch') is not None:
        try:
            import torch
            report['dependencies']['torch'] = torch.__version__
            if not torch.cuda.is_available():
                missing.append('CUDA is not available (torch.cuda.is_available() is False)')
            else:
                report['dependencies']['cuda'] = torch.version.cuda
                report['dependencies']['gpu'] = torch.cuda.get_device_name(0)
        except Exception as e:
            missing.append(f'torch import failed: {e}')
    if importlib.util.find_spec('huggingface_hub') is not None:
        try:
            import huggingface_hub as hf_hub
            report['dependencies']['huggingface_hub'] = getattr(hf_hub, '__version__', 'unknown')
            report['dependencies']['get_cached_repo_tree'] = hasattr(hf_hub, 'get_cached_repo_tree')
            try:
                import huggingface_hub.errors as hf_err
                report['dependencies']['CachedRepoTreeNotFoundError'] = hasattr(hf_err, 'CachedRepoTreeNotFoundError')
            except Exception:
                report['dependencies']['CachedRepoTreeNotFoundError'] = False
        except Exception as e:
            missing.append(f'huggingface_hub import failed: {e}')
    model_path = '/models/stable-diffusion-v1-5--stable-diffusion-inpainting'
    if manifest and manifest.get('model_container_path'):
        model_path = manifest['model_container_path']
    report['model_path'] = model_path
    if not Path(model_path).is_dir():
        missing.append(f'model directory missing: {model_path}')
    else:
        for rel in ['model_index.json', 'unet/config.json', 'vae/config.json', 'scheduler/scheduler_config.json', 'text_encoder/config.json', 'tokenizer/tokenizer_config.json']:
            p = Path(model_path) / rel
            if not p.exists():
                missing.append(f'model file missing: {p}')
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return EX_CONFIG if missing else 0


def cmd_run(args):
    # Ensure huggingface_hub shims are installed before importing diffusers.
    _install_huggingface_hub_shim()
    import numpy as np
    import torch
    from PIL import Image
    try:
        from diffusers import StableDiffusionInpaintPipeline
    except (ImportError, RuntimeError) as e:
        msg = str(e)
        if 'CachedRepoTreeNotFoundError' in msg or 'get_cached_repo_tree' in msg:
            _install_huggingface_hub_shim()
            try:
                import importlib
                import diffusers as _diffusers
                _m = importlib.import_module('diffusers.pipelines.stable_diffusion.pipeline_stable_diffusion_inpaint')
                StableDiffusionInpaintPipeline = getattr(_m, 'StableDiffusionInpaintPipeline')
                if hasattr(_diffusers, 'StableDiffusionInpaintPipeline') is False:
                    try:
                        _diffusers.StableDiffusionInpaintPipeline = StableDiffusionInpaintPipeline
                    except Exception:
                        pass
            except Exception as e2:
                print(f'ERROR: cannot import diffusers StableDiffusionInpaintPipeline: {e2}', file=sys.stderr)
                return 2
        else:
            print(f'ERROR: cannot import diffusers StableDiffusionInpaintPipeline: {e}', file=sys.stderr)
            return 2
    if not torch.cuda.is_available():
        print('ERROR: CUDA is not available. This task requires a CUDA GPU.', file=sys.stderr)
        return 2
    base = Path(args.input)
    out_dir = Path(args.output)
    images_dir = out_dir / 'images'
    images_dir.mkdir(parents=True, exist_ok=True)
    req_path = base / 'requests.jsonl'
    if not req_path.exists():
        print(f'ERROR: missing {req_path}', file=sys.stderr)
        return 2
    reqs = read_jsonl(req_path)
    if not reqs:
        print('ERROR: requests.jsonl is empty', file=sys.stderr)
        return 2
    model_path = args.model
    revision = args.revision
    kwargs = dict(torch_dtype=torch.float16, local_files_only=True)
    if not os.path.isdir(model_path):
        kwargs['revision'] = revision
    try:
        pipe = StableDiffusionInpaintPipeline.from_pretrained(model_path, **kwargs)
        pipe = pipe.to('cuda')
    except Exception as e:
        print(f'ERROR: failed to load model {model_path}: {e}', file=sys.stderr)
        return 2
    pipe.set_progress_bar_config(disable=True)
    if not str(pipe.unet.device).startswith('cuda'):
        print('ERROR: denoiser is not on CUDA', file=sys.stderr)
        return 2
    pipe.unet.eval()
    pipe.vae.eval()
    wall_start = time.time()
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    t0 = time.perf_counter()
    index_records = []
    total_elapsed = 0.0
    LANCZOS = getattr(Image, 'Resampling', Image).LANCZOS
    NEAREST = getattr(Image, 'Resampling', Image).NEAREST
    for i, req in enumerate(reqs):
        rid = get_first(req, ['id', 'image_id', 'name', 'key'], str(i))
        sid = safe_id(rid)
        img_rel = get_first(req, ['image', 'input_image', 'image_path', 'image_file', 'corrupted_image', 'file'], f'images/{rid}.png')
        mask_rel = get_first(req, ['mask', 'mask_image', 'mask_path', 'inpainting_mask'], f'masks/{rid}.png')
        prompt = str(get_first(req, ['prompt', 'caption', 'text', 'source_caption', 'description'], ''))
        try:
            seed = int(get_first(req, ['seed', 'random_seed'], args.seed))
        except Exception:
            seed = int(args.seed)
        img_path = resolve_input_path(base, img_rel, 'images')
        mask_path = resolve_input_path(base, mask_rel, 'masks')
        if not img_path.exists() or not mask_path.exists():
            print(f'ERROR: missing input for request {rid}: image={img_path} mask={mask_path}', file=sys.stderr)
            return 2
        orig = Image.open(img_path).convert('RGB')
        mask_img = Image.open(mask_path).convert('L').point(lambda p: 255 if p > 127 else 0)
        orig_size = orig.size
        img_512 = orig.resize((512, 512), LANCZOS)
        mask_512 = mask_img.resize((512, 512), NEAREST)
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        gen = torch.Generator(device='cuda').manual_seed(seed)
        torch.cuda.synchronize()
        t_start = time.perf_counter()
        with torch.inference_mode():
            result = pipe(
                prompt=prompt,
                image=img_512,
                mask_image=mask_512,
                height=512,
                width=512,
                num_inference_steps=args.steps,
                guidance_scale=args.guidance,
                generator=gen,
            ).images[0]
        torch.cuda.synchronize()
        t_end = time.perf_counter()
        elapsed = t_end - t_start
        total_elapsed += elapsed
        result_full = result.resize(orig_size, LANCZOS)
        out_img = orig.copy()
        out_img.paste(result_full, (0, 0), mask_img)
        out_path = images_dir / f'{sid}.png'
        out_img.save(out_path)
        out_np = np.asarray(out_img.convert('RGB'))
        orig_np = np.asarray(orig.convert('RGB'))
        mask_np = np.asarray(mask_img)
        protected_equal = bool(np.array_equal(out_np[mask_np == 0], orig_np[mask_np == 0]))
        coverage = float((mask_np > 127).mean())
        try:
            with Image.open(out_path) as im:
                im.verify()
            image_ok = True
        except Exception:
            image_ok = False
        rec = {
            'id': str(rid),
            'request_index': i,
            'total_requests': len(reqs),
            'input_image': str(img_rel),
            'input_image_sha256': sha256_file(img_path),
            'mask': str(mask_rel),
            'mask_sha256': sha256_file(mask_path),
            'prompt': prompt,
            'output': f'images/{sid}.png',
            'output_sha256': sha256_file(out_path),
            'seed': seed,
            'steps': args.steps,
            'guidance_scale': args.guidance,
            'device': f'cuda:{torch.cuda.current_device()}',
            'height': 512,
            'width': 512,
            'original_size': list(orig_size),
            'mask_coverage': coverage,
            'protected_pixels_equal': protected_equal,
            'image_ok': image_ok,
            'elapsed_s': elapsed,
            'denoiser_device': str(pipe.unet.device),
            'denoiser_dtype': str(pipe.unet.dtype),
        }
        index_records.append(rec)
        print(f'[{i+1}/{len(reqs)}] {rid}: {elapsed:.2f}s coverage={coverage:.3f} protected_equal={protected_equal}')
    t1 = time.perf_counter()
    wall_end = time.time()
    index_path = out_dir / 'index.jsonl'
    with index_path.open('w', encoding='utf-8') as f:
        for rec in index_records:
            f.write(json.dumps(rec, ensure_ascii=False) + chr(10))
    peak_gib = torch.cuda.max_memory_allocated() / (1024 ** 3)
    config = {
        'task_id': 'GPUv1-C02',
        'scale': 'debug_only',
        'input': str(base),
        'output': str(out_dir),
        'model_path': model_path,
        'model_revision': revision,
        'steps': args.steps,
        'guidance_scale': args.guidance,
        'height': 512,
        'width': 512,
        'dtype': 'float16',
        'seed_default': args.seed,
    }
    (out_dir / 'config.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
    run = {
        'task_id': 'GPUv1-C02',
        'scale': 'debug_only',
        'start_time': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(wall_start)),
        'end_time': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(wall_end)),
        'total_wall_s': t1 - t0,
        'total_generation_s': total_elapsed,
        'device': {
            'cuda_available': True,
            'device_count': torch.cuda.device_count(),
            'device_name': torch.cuda.get_device_name(0),
            'current_device': torch.cuda.current_device(),
        },
        'versions': {
            'torch': torch.__version__,
            'diffusers': __import__('diffusers').__version__,
            'transformers': __import__('transformers').__version__,
            'numpy': np.__version__,
            'PIL': __import__('PIL').__version__,
            'huggingface_hub': getattr(__import__('huggingface_hub'), '__version__', 'unknown'),
        },
        'peak_cuda_memory_gib': peak_gib,
        'num_requests': len(reqs),
        'config': config,
        'index_path': 'index.jsonl',
        'index': index_records,
    }
    run_json_path = out_dir / 'run.json'
    run_json_path.write_text(json.dumps(run, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Wrote {index_path} and {run_json_path}')
    return 0


def main():
    p = argparse.ArgumentParser(description='GPUv1-C02 masked image completion with StableDiffusionInpaintPipeline')
    sub = p.add_subparsers(dest='cmd', required=True)
    dr = sub.add_parser('doctor', help='inspect inputs and dependencies without loading the model')
    dr.add_argument('--input', default='input')
    dr.set_defaults(func=cmd_doctor)
    rn = sub.add_parser('run', help='run CUDA fp16 inpainting on requests.jsonl')
    rn.add_argument('--input', default='input')
    rn.add_argument('--output', default='output')
    rn.add_argument('--model', default='/models/stable-diffusion-v1-5--stable-diffusion-inpainting')
    rn.add_argument('--revision', default='8a4288a76071f7280aedbdb3253bdb9e9d5d84bb')
    rn.add_argument('--steps', type=int, default=12)
    rn.add_argument('--guidance', type=float, default=7.5)
    rn.add_argument('--seed', type=int, default=0)
    rn.set_defaults(func=cmd_run)
    args = p.parse_args()
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
