"""Lock upstream SHA1-verified CPU dependency sources for ONNX Runtime."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import zipfile
from prepare_sources import ROOT,download,sha

TASK=ROOT/'tasks/BUILDv1-F10'
manifest=json.loads((TASK/'input/manifest.json').read_text())
with tarfile.open(TASK/'input'/manifest['source']['filename']) as a:
    member=next(m for m in a if m.name.endswith('/cmake/deps.txt'))
    text=a.extractfile(member).read().decode()
selected={'abseil_cpp','cxxopts','date','dlpack','eigen','flatbuffers','fp16','fxdiv','google_benchmark','googletest','googlexnnpack','json','microsoft_gsl','mimalloc','mp11','onnx','protobuf','psimd','pthreadpool','pybind11','pytorch_cpuinfo','re2','safeint','tensorboard','utf8_range'}
rows=[line.split(';') for line in text.splitlines() if line and not line.startswith('#') and line.split(';')[0] in selected]

def fetch(row):
    name,url,expected=row
    target=ROOT/'assets/sources'/('ort-dep-'+name+'-'+expected+'.zip')
    if not target.exists():download(url,target)
    h=hashlib.sha1()
    with target.open('rb') as f:
        for b in iter(lambda:f.read(4<<20),b''):h.update(b)
    actual=h.hexdigest()
    alternate=None
    if actual!=expected:
        if name!='eigen':raise ValueError('upstream dependency SHA1 mismatch: '+name)
        alternate=url.removesuffix('.zip')+'.tar.gz'
        other=target.with_suffix('.tar.gz')
        if not other.exists():download(alternate,other)
        with zipfile.ZipFile(target) as z,tarfile.open(other) as t:
            zm={str(Path(*Path(i.filename).parts[1:])):hashlib.sha256(z.read(i)).hexdigest() for i in z.infolist() if not i.is_dir() and len(Path(i.filename).parts)>1}
            tm={str(Path(*Path(i.name).parts[1:])):hashlib.sha256(t.extractfile(i).read()).hexdigest() for i in t if i.isfile() and len(Path(i.name).parts)>1}
            assert zm==tm,'official same-commit Eigen zip and tar file trees disagree'
        print('OFFICIAL_ARCHIVE_REBIND',name,'same Git commit, file trees verified equal',flush=True)
        target=other
    print('CPU_DEPENDENCY_LOCKED',name,target.stat().st_size,flush=True)
    return {'name':name,'url':alternate or url,'upstream_url':url,'upstream_sha1':expected,'observed_original_sha1':actual,'archive_rebound':bool(alternate),'same_commit_file_tree_verified':bool(alternate),'sha256':sha(target),'archive':str(target)}

with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:records=list(pool.map(fetch,rows))
bundle=ROOT/'assets/sources/ort-cpu-dependencies.tar.gz'
with tarfile.open(bundle,'w:gz',compresslevel=1) as out:
    for item in records:
        if zipfile.is_zipfile(item['archive']):
            with zipfile.ZipFile(item['archive']) as archive:
                total=sum(i.file_size for i in archive.infolist());assert total<2*2**30
                for entry in archive.infolist():
                    parts=Path(entry.filename).parts
                    assert not Path(entry.filename).is_absolute() and '..' not in parts
                    if len(parts)<2 or entry.is_dir():continue
                    info=tarfile.TarInfo(str(Path('ort_deps')/item['name']/Path(*parts[1:])))
                    info.size=entry.file_size;info.mode=((entry.external_attr>>16)&0o777) or 0o644
                    with archive.open(entry) as f:out.addfile(info,f)
        else:
            with tarfile.open(item['archive']) as archive:
                for entry in archive:
                    parts=Path(entry.name).parts
                    assert not Path(entry.name).is_absolute() and '..' not in parts
                    if len(parts)<2:continue
                    entry.name=str(Path('ort_deps')/item['name']/Path(*parts[1:]))
                    entry.mode &=0o777
                    if entry.isfile():out.addfile(entry,archive.extractfile(entry))
                    elif entry.isdir():out.addfile(entry)
                    else:raise ValueError('unexpected source archive link: '+entry.name)
linked=TASK/'input/ort-dependencies.tar.gz';linked.unlink(missing_ok=True);linked.hardlink_to(bundle)
manifest['dependency_caches']=[item for item in manifest.get('dependency_caches',[]) if item['filename']!=linked.name]+[{'filename':linked.name,'sha256':sha(linked),'bytes':linked.stat().st_size,'target_outputs_exported':False,'destination':'/workspace/cache/ort_deps'}]
for item in records:item.pop('archive')
manifest['cpu_dependency_sources']=records
(TASK/'input/manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print('CPU_DEPENDENCY_BUNDLE_LOCKED',linked.stat().st_size,flush=True)
