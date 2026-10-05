"""Import actual upstream Git objects for the original license-table generator."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
from input_storage import link_input
from prepare_sources import sha
from status import ROOT


def git(directory: Path, *args: str) -> str:
    return subprocess.run(['git','--git-dir='+str(directory),*args],check=True,capture_output=True,text=True,timeout=300).stdout.strip()


def prepare() -> None:
    task=ROOT/'tasks/BUILDv1-D07'
    manifest=json.loads((task/'input/manifest.json').read_text())
    source=manifest['source']
    original=ROOT/'assets/git_metadata'/('github.com_ClickHouse_ClickHouse_'+source['commit'][:12])
    assert git(original,'rev-parse',source['commit']+'^{commit}')==source['commit']
    policy=json.loads((ROOT/'runtime/policy.json').read_text())
    artifact_root=Path(os.environ.get('SBENCH_BUILD_ARTIFACT_ROOT',policy.get('preparation_artifact_root',ROOT/'runs')))
    run=artifact_root/'preparation'/('clickhouse_genuine_git_metadata_'+str(time.time_ns()))
    run.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='clickhouse-real-git-',dir=run) as temporary:
        metadata=Path(temporary)/'.git'
        metadata.mkdir()
        for name in ['objects','refs']:
            shutil.copytree(original/name,metadata/name)
        for name in ['config','shallow','packed-refs']:
            if (original/name).exists():shutil.copy2(original/name,metadata/name)
        (metadata/'HEAD').write_text(source['commit']+'\n')
        git(metadata,'config','core.bare','false')
        git(metadata,'config','core.worktree','..')
        git(metadata,'config','core.logallrefupdates','false')
        git(metadata,'read-tree',source['commit'])
        assert git(metadata,'rev-parse','HEAD')==source['commit']
        assert git(metadata,'rev-parse','HEAD^{tree}')==git(original,'rev-parse',source['commit']+'^{tree}')
        assert git(metadata,'fsck','--connectivity-only','--no-reflogs') is not None
        proof={'task_id':manifest['task_id'],'upstream_repo':source['upstream_repo'],
               'commit':source['commit'],'tree':git(metadata,'rev-parse','HEAD^{tree}'),
               'upstream_commit_object':git(metadata,'cat-file','-p',source['commit']),
               'basis':'Exact original commit/tree objects already fetched from the official upstream for gitlink resolution. Operational HEAD/core.worktree/index bind these authentic objects to the verified source archive; no commit, tree, license or target output fabricated.',
               'target_compiled':False,'target_outputs_exported':False}
        payload=run/'genuine-clickhouse-git.tar.gz'
        with tarfile.open(payload,'w:gz',compresslevel=3) as archive:archive.add(metadata,arcname='.git')
    proof.update(filename=payload.name,bytes=payload.stat().st_size,sha256=sha(payload))
    (run/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    link_input(task/'input'/payload.name,payload)
    manifest['source_metadata_archives']=[{**proof,'preparation_run':str(run)}]
    (task/'input/manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print('GENUINE_CLICKHOUSE_GIT_METADATA_LOCKED',proof['commit'],proof['tree'],proof['bytes'],flush=True)


if __name__=='__main__':prepare()
