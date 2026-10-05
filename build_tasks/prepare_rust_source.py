"""Acquire the official complete Rust source distribution, including vendored crates."""
from input_storage import link_input
import json
from pathlib import Path
import requests
import tarfile
from prepare_sources import ROOT,download,sha,source_context
r=ROOT;task=r/'tasks/BUILDv1-B09';url='https://static.rust-lang.org/dist/rustc-1.87.0-src.tar.xz';archive=r/'assets/sources/rustc-1.87.0-src.tar.xz'
if not archive.exists():download(url,archive)
check=requests.get(url+'.sha256',timeout=30);check.raise_for_status();assert sha(archive)==check.text.split()[0]
with tarfile.open(archive) as t:
 names=[m.name for m in t if len(Path(m.name).parts)<4];assert any('/vendor/' in n for n in names),'official source lacks vendor closure'
print('official full Rust source contains vendor tree',archive.stat().st_size,flush=True)
p=task/'input/manifest.json';old=json.loads(p.read_text());history=task/'instances/core_github_archive_initial';history.mkdir(parents=True,exist_ok=True)
if not (history/'manifest.json').exists():(history/'manifest.json').write_text(p.read_text())
filename='source-full.tar.xz';linked=task/'input'/filename;linked.unlink(missing_ok=True);link_input(linked,archive)
source={**old['source'],'filename':filename,'sha256':sha(archive),'bytes':archive.stat().st_size,'acquisition_url':url,'submodules_ready':True,'vendor_ready':True,'official_full_source_release':True,'base_archive':old['source']}
old['source']=source;p.write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n');(task/'source_lock.json').write_text(json.dumps(source,indent=2)+'\n');(task/'source_context.json').write_text(json.dumps(source_context(archive),ensure_ascii=False,indent=2)+'\n')
