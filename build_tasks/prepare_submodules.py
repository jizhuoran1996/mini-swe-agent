"""Vendor exact gitlink revisions into separately locked source archives."""
import argparse
import configparser
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import requests
from prepare_sources import download, sha, source_context
from status import ROOT, update

CPU_PYTORCH = {'third_party/pybind11','third_party/eigen','third_party/googletest','third_party/benchmark',
               'third_party/protobuf','third_party/NNPACK','third_party/pthreadpool','third_party/FXdiv',
               'third_party/FP16','third_party/psimd','third_party/cpuinfo','third_party/python-peachpy',
               'third_party/onnx','third_party/sleef','third_party/ideep','third_party/gemmlowp/gemmlowp',
               'third_party/fbgemm','third_party/XNNPACK','third_party/fmt','third_party/tensorpipe',
               'third_party/kineto','third_party/pocketfft','third_party/ittapi','third_party/flatbuffers',
               'third_party/nlohmann','third_party/mimalloc','third_party/opentelemetry-cpp','third_party/cpp-httplib'}


def gitlinks(repo_url, commit, metadata):
    if not metadata.exists():
        subprocess.run(['git','init','--bare',str(metadata)], check=True, capture_output=True)
    subprocess.run(['git','-C',str(metadata),'fetch','--depth=1','--filter=blob:none',repo_url,commit],
                   check=True, capture_output=True, timeout=300)
    result = subprocess.run(['git','-C',str(metadata),'ls-tree','-r',commit], check=True, capture_output=True, text=True)
    return {line.split('\t',1)[1]:line.split()[2] for line in result.stdout.splitlines() if line.startswith('160000 ')}


def resolve_url(parent_url, url):
    if url.startswith('../'):
        return parent_url.rsplit('/',1)[0] + '/' + url.removeprefix('../')
    return url


def module_sources(repo_url, commit, modules_text, prefix='', wanted=None, depth=0):
    config = configparser.ConfigParser()
    config.read_string("\n".join(line.lstrip() for line in modules_text.splitlines()))
    cache = ROOT / 'assets/git_metadata' / (repo_url.removeprefix('https://').replace('/','_') + '_' + commit[:12])
    cache.parent.mkdir(parents=True, exist_ok=True)
    links = gitlinks(repo_url, commit, cache)
    results = []
    for section in config.sections():
        path = config[section]['path']
        if wanted is not None and path not in wanted:
            continue
        if path not in links:
            raise ValueError('missing gitlink: ' + path)
        url = resolve_url(repo_url, config[section]['url'])
        revision = links[path]
        full_path = str(Path(prefix) / path)
        archive = ROOT / 'assets/sources' / ('submodule-' + revision + '.tar.gz')
        if not archive.exists():
            if url.startswith('https://github.com/'):
                repo = url.removeprefix('https://github.com/').removesuffix('.git')
                acquisition = f'https://codeload.github.com/{repo}/tar.gz/{revision}'
                if repo.endswith('.wiki'):
                    wiki_meta = ROOT/'assets/git_metadata'/('wiki_'+revision)
                    gitlinks(url,revision,wiki_meta)
                    subprocess.run(['git','-C',str(wiki_meta),'archive','--format=tar.gz','--output='+str(archive),revision],check=True,capture_output=True,timeout=120)
                    acquisition = None
            elif url.startswith('https://gitlab.com/'):
                repo = url.removeprefix('https://gitlab.com/').removesuffix('.git')
                name = repo.rsplit('/',1)[1]
                acquisition = f'https://gitlab.com/{repo}/-/archive/{revision}/{name}-{revision}.tar.gz'
            else:
                raise ValueError('unsupported exact-source provider: ' + url)
            if acquisition:
                download(acquisition, archive)
        record = {'path': full_path, 'repo': url, 'commit': revision, 'archive_sha256': sha(archive), 'archive': str(archive)}
        results.append(record)
        with tarfile.open(archive) as tree:
            modules = next((m for m in tree.getmembers() if len(Path(m.name).parts)==2 and Path(m.name).name=='.gitmodules'),None)
            if modules and depth < 4:
                text = tree.extractfile(modules).read().decode()
                results.extend(module_sources(url, revision, text, prefix=full_path, depth=depth+1))
        print('SUBMODULE_LOCKED', full_path, revision[:12], flush=True)
    return results


def prepare(task_id):
    task = ROOT / 'tasks' / task_id
    manifest_path = task / 'input/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    context = json.loads((task / 'source_context.json').read_text())
    modules = context['official_build_files'].get('.gitmodules')
    if not modules:
        return
    if manifest['source'].get('submodules_vendored'):
        return
    wanted = None
    if task_id == 'BUILDv1-A09':
        wanted = {'tests/munit'}
    elif task_id == 'BUILDv1-F01':
        wanted = CPU_PYTORCH
    elif task_id == 'BUILDv1-D07':
        config=configparser.ConfigParser();config.read_string('\n'.join(line.lstrip() for line in modules.splitlines()))
        wanted={config[section]['path'] for section in config.sections()}-{'contrib/rust_vendor','contrib/delta-kernel-rs','contrib/corrosion'}
    elif task_id == 'BUILDv1-F08':
        wanted = {'dmlc-core'}
    elif task_id == 'BUILDv1-F09':
        wanted = {'external_libs/eigen','external_libs/fmt','external_libs/fast_double_parser'}
    sources = module_sources(manifest['source']['upstream_repo'], manifest['source']['commit'], modules, wanted=wanted)
    base = task / 'input' / manifest['source']['filename']
    bundle = ROOT / 'assets/sources' / (task_id + '-with-submodules.tar.gz')
    with tarfile.open(bundle, 'w:gz', compresslevel=1) as destination:
        with tarfile.open(base) as source:
            top = Path(source.getmembers()[0].name).parts[0]
            for member in source:
                destination.addfile(member, source.extractfile(member) if member.isfile() else None)
        for record in sources:
            with tarfile.open(record['archive']) as source:
                for member in source:
                    parts = Path(member.name).parts
                    if len(parts) < 2:
                        continue
                    member.name = str(Path(top) / record['path'] / Path(*parts[1:]))
                    destination.addfile(member, source.extractfile(member) if member.isfile() else None)
    original = manifest['source'].copy()
    filename = 'source-with-submodules.tar.gz'
    linked = task / 'input' / filename
    linked.unlink(missing_ok=True)
    linked.hardlink_to(bundle)
    for s in sources:
        s.pop('archive')
    manifest['source'].update(filename=filename, sha256=sha(bundle), bytes=bundle.stat().st_size,
                              submodules_ready=True, submodules_vendored=True, submodules=sources,
                              base_archive=original)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    (task / 'source_lock.json').write_text(json.dumps(manifest['source'], ensure_ascii=False, indent=2)+'\n')
    context['vendored_submodules'] = sources
    (task / 'source_context.json').write_text(json.dumps(context, ensure_ascii=False, indent=2)+'\n')
    update(task_id, source_submodules_ready=True, source_sha256=manifest['source']['sha256'])
    print('BUNDLE_LOCKED',task_id,len(sources),bundle.stat().st_size,flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('ids', nargs='+')
    args = parser.parse_args()
    for task_id in args.ids:
        try:
            prepare(task_id)
        except Exception as error:
            update(task_id, source_submodules_ready=False, preparation_failure=str(error)[-1500:])
            print('SUBMODULE_FAILURE',task_id,type(error).__name__,str(error)[:500],flush=True)
