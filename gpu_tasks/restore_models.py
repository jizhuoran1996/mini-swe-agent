"""Restore immutable model bytes from packaged locks, outside task containers."""
import argparse,json
from pathlib import Path
from assets import ROOT,fetch,digest

def restore(only=None):
    folder=ROOT/'model_locks'
    if not folder.exists():folder=ROOT/'assets/models'
    restored=[]
    for lockfile in sorted(folder.glob('*/asset_lock.json')):
        lock=json.loads(lockfile.read_text());repo=lock.get('repo_id');revision=lock.get('revision')
        if not repo or not revision:continue
        if only and repo not in only:continue
        target=ROOT/'assets/models'/lockfile.parent.name;target.mkdir(parents=True,exist_ok=True)
        for item in lock['files']:
            name=Path(item['name']);assert not name.is_absolute() and '..' not in name.parts
            p=fetch(f'https://huggingface.co/{repo}/resolve/{revision}/{name}',target/name,max_bytes=max(item.get('bytes',0)+1024,8*2**30))
            if digest(p)!=item['sha256']:raise RuntimeError('SHA256 mismatch: '+str(p))
        for alias in lock.get('aliases',[]):
            name=Path(alias['name']);source=Path(alias['target']);assert '..' not in name.parts and '..' not in source.parts and not name.is_absolute() and not source.is_absolute()
            p=target/name
            if not p.exists():p.symlink_to(__import__('os').path.relpath(target/source,p.parent))
        (target/'asset_lock.json').write_text(json.dumps(lock,indent=2)+'\n');restored.append(repo);print('RESTORED',repo,revision,flush=True)
    return restored

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--only',nargs='+');args=parser.parse_args();restore(args.only)
