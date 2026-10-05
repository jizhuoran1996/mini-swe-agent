"""Materialize the exact NCCL source pin required even by upstream CPU setup."""
from pathlib import Path
import json
import tarfile
from prepare_sources import download,sha
from status import ROOT,write_json

COMMIT='f44ac759fee12ecb3cc6891e9e739a000f66fd70'
RELEASE='v2.26.2-1'

def prepare() -> None:
    task=ROOT/'tasks/BUILDv1-F01'
    upstream=task/'input/nccl-official-source.tar.gz'
    url='https://codeload.github.com/NVIDIA/nccl/tar.gz/'+COMMIT
    if not upstream.exists():download(url,upstream)
    archive=task/'input/torch-nccl-source.tar.gz'
    with tarfile.open(upstream) as source,tarfile.open(archive,'w:gz') as target:
        for member in source:
            parts=Path(member.name).parts
            assert parts and not Path(member.name).is_absolute() and '..' not in parts
            member.name=str(Path('torch_nccl',*parts[1:]))
            stream=source.extractfile(member) if member.isfile() else None
            target.addfile(member,stream)
    manifest=json.loads((task/'input/manifest.json').read_text())
    record={'filename':archive.name,'sha256':sha(archive),'bytes':archive.stat().st_size,
            'destination':'/workspace/cache/torch_nccl','target_outputs_exported':False,
            'repository':'NVIDIA/nccl','release_ref':RELEASE,'commit':COMMIT,
            'official_source_url':url,'official_source_sha256':sha(upstream),
            'reason':'Unmodified tools/build_pytorch_libs.py calls checkout_nccl unconditionally even with USE_CUDA=0; no NCCL target compilation requested'}
    manifest['dependency_caches']=[x for x in manifest.get('dependency_caches',[]) if x['filename']!=archive.name]+[record]
    write_json(task/'input/manifest.json',manifest)
    write_json(task/'input/nccl-source-lock.json',record)
    print('GENUINE_CPU_SETUP_SOURCE_PIN_READY',record,flush=True)

if __name__=='__main__':prepare()
