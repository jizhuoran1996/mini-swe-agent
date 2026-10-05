"""Lock official release inputs without compiling target projects on the host."""
from input_storage import link_input
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import time
import requests
from status import ROOT, update

GITHUB = {
 'A01':('madler/zlib','v1.3.1'), 'A02':('facebook/zstd','v1.5.7'),
 'A03':('libarchive/libarchive','v3.8.1'), 'A04':('curl/curl','curl-8_14_1'),
 'A05':('openssl/openssl','openssl-3.5.2'), 'A06':('libuv/libuv','v1.51.0'),
 'A07':('libevent/libevent','release-2.2.2-alpha'), 'A08':('PCRE2Project/pcre2','pcre2-10.46'),
 'A09':('nghttp2/nghttp2','v1.65.0'), 'A10':('libgit2/libgit2','v1.9.1'),
 'B01':('llvm/llvm-project','llvmorg-20.1.8'), 'B04':('python/cpython','v3.12.10'),
 'B05':('nodejs/node','v22.16.0'), 'B06':('ruby/ruby','v3_4_4'),
 'B07':('php/php-src','php-8.4.8'), 'B09':('rust-lang/rust','1.87.0'),
 'B10':('openjdk/jdk21u','jdk-21.0.7+6'), 'C01':('FFmpeg/FFmpeg','n7.1.1'),
 'C02':('GStreamer/gstreamer','1.26.2'), 'C03':('ImageMagick/ImageMagick','7.1.1-47'),
 'C04':('libvips/libvips','v8.16.1'), 'C05':('opencv/opencv','4.11.0'),
 'C06':('blender/blender','v4.4.3'), 'C07':('godotengine/godot','4.4.1-stable'),
 'C09':('OSGeo/gdal','v3.10.3'), 'C10':('Kitware/VTK','v9.4.2'),
 'D02':('MariaDB/server','mariadb-11.4.5'), 'D03':('redis/redis','7.4.5'),
 'D04':('facebook/rocksdb','v10.2.1'), 'D05':('duckdb/duckdb','v1.4.3'),
 'D06':('apache/arrow','apache-arrow-19.0.1'), 'D07':('ClickHouse/ClickHouse','v25.3.3.42-lts'),
 'D08':('etcd-io/etcd','v3.5.21'), 'D09':('nginx/nginx','release-1.28.0'),
 'D10':('envoyproxy/envoy','v1.34.2'), 'E01':('apache/kafka','3.9.1'),
 'E02':('apache/spark','v3.5.7'), 'E03':('apache/flink','release-1.20.1'),
 'E04':('apache/lucene','releases/lucene/9.12.2'), 'E05':('elastic/elasticsearch','v8.17.6'),
 'E06':('microsoft/TypeScript','v5.9.3'), 'E07':('rollup/rollup','v4.40.2'),
 'E08':('babel/babel','v7.27.1'), 'E09':('evanw/esbuild','v0.25.4'),
 'E10':('swc-project/swc','v1.11.24'), 'F01':('pytorch/pytorch','v2.7.1'),
 'F02':('tensorflow/tensorflow','v2.18.0'), 'F03':('jax-ml/jax','jax-v0.5.3'),
 'F08':('dmlc/xgboost','v3.0.2'), 'F09':('lightgbm-org/LightGBM','v4.6.0'),
 'F10':('microsoft/onnxruntime','v1.21.1')
}
ARCHIVES = {
 'B02':('gcc-14.2.0','https://ftp.gnu.org/gnu/gcc/gcc-14.2.0/gcc-14.2.0.tar.xz'),
 'B03':('binutils-2.44','https://ftp.gnu.org/gnu/binutils/binutils-2.44.tar.xz'),
 'B08':('go1.24.4','https://go.dev/dl/go1.24.4.src.tar.gz'),
 'C08':('mesa-25.1.2','https://archive.mesa3d.org/mesa-25.1.2.tar.xz'),
 'D01':('postgresql-17.5','https://ftp.postgresql.org/pub/source/v17.5/postgresql-17.5.tar.bz2')
}
PYPI = {'F04':('scikit-learn','1.6.1'),'F05':('numpy','2.2.6'),
        'F06':('scipy','1.15.3'),'F07':('pandas','2.2.3')}


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(8 << 20), b''):
            h.update(data)
    return h.hexdigest()


def download(url, output):
    temporary = output.with_suffix(output.suffix + '.partial')
    for attempt in range(4):
        position=temporary.stat().st_size if temporary.exists() else 0
        headers={'Range':'bytes='+str(position)+'-'} if position else {}
        try:
            with requests.get(url,headers=headers,stream=True,timeout=(20,120)) as response:
                response.raise_for_status()
                append=response.status_code==206 and position>0
                if append:
                    assert response.headers.get('Content-Range','').startswith('bytes '+str(position)+'-')
                with temporary.open('ab' if append else 'wb') as stream:
                    for data in response.iter_content(1<<20):
                        if shutil.disk_usage(ROOT).free<52*2**30:
                            raise RuntimeError('source download stopped at host disk reserve')
                        stream.write(data)
                        if stream.tell()>1*2**30:
                            raise RuntimeError('source archive exceeds declared download limit')
            temporary.replace(output)
            return
        except requests.RequestException:
            if attempt==3:raise
            time.sleep(1)


def source_context(archive):
    names = []
    files = {}
    wanted = ['CMakeLists.txt','Makefile','Makefile.in','README.md','README','INSTALL.md',
              'pyproject.toml','setup.py','package.json','meson.build','configure.ac',
              'build.gradle','build.gradle.kts','pom.xml','.gitmodules','Cargo.toml',
              'build/build.py','tools/build_defs/repo/README.md','tests/Makefile']
    with tarfile.open(archive) as tree:
        for member in tree:
            parts = Path(member.name).parts
            if len(parts) < 2:
                continue
            name = str(Path(*parts[1:]))
            if name.count('/') <= 1:
                names.append(name)
            if member.isfile() and name in wanted and member.size < 60000:
                stream = tree.extractfile(member)
                files[name] = stream.read().decode(errors='replace')
    return {'top_level_paths': names[:160], 'official_build_files': files}


def prepare(task_id):
    task = ROOT / 'tasks' / task_id
    spec = json.loads((task / 'source_spec.json').read_text())
    short = task_id.removeprefix('BUILDv1-')
    inputs = task / 'input'
    inputs.mkdir(exist_ok=True)
    if (inputs / 'manifest.json').exists():
        old = json.loads((inputs / 'manifest.json').read_text())
        asset = inputs / old['source']['filename']
        selected_ref = GITHUB[short][1] if short in GITHUB else ARCHIVES[short][0] if short in ARCHIVES else PYPI[short][1]
        if old['source']['release_ref'] == selected_ref and asset.exists() and sha(asset) == old['source']['sha256']:
            return old
    commit = None
    expected_sha = None
    if short in GITHUB:
        repo, ref = GITHUB[short]
        result = subprocess.run(['git','ls-remote','https://github.com/' + repo + '.git',
                                 'refs/tags/' + ref, 'refs/tags/' + ref + '^{}'],
                                capture_output=True, text=True, timeout=120, check=True)
        lines = result.stdout.strip().splitlines()
        if not lines:
            raise ValueError('release ref not found: ' + repo + ' ' + ref)
        peeled = [s for s in lines if s.endswith('^{}')]
        commit = (peeled or lines)[0].split()[0]
        url = 'https://codeload.github.com/' + repo + '/tar.gz/' + commit
        filename = 'source.tar.gz'
    elif short in ARCHIVES:
        ref, url = ARCHIVES[short]
        filename = 'source.tar.' + ('xz' if url.endswith('.xz') else 'bz2' if url.endswith('.bz2') else 'gz')
    else:
        package, ref = PYPI[short]
        response = requests.get(f'https://pypi.org/pypi/{package}/{ref}/json', timeout=30)
        response.raise_for_status()
        source = next(x for x in response.json()['urls'] if x['packagetype'] == 'sdist')
        url, expected_sha = source['url'], source['digests']['sha256']
        filename = 'source.tar.gz'
    binding = commit[:12] if commit else ref.replace('/', '_').replace('+', '_')
    asset = ROOT / 'assets/sources' / (task_id + '-' + binding + '-' + filename)
    if not asset.exists():
        download(url, asset)
    checksum = sha(asset)
    if expected_sha and checksum != expected_sha:
        raise ValueError('official sdist checksum mismatch')
    linked = inputs / filename
    linked.unlink(missing_ok=True)
    link_input(linked,asset)
    context = source_context(asset)
    source = {'upstream_repo': spec['upstream_repo'], 'acquisition_url': url, 'release_ref': ref,
              'commit': commit, 'filename': filename, 'bytes': asset.stat().st_size,
              'sha256': checksum, 'submodules_ready': '.gitmodules' not in context['official_build_files']}
    manifest = {'task_id': task_id, 'project': spec['project'], 'profile': 'core', 'source': source,
                'scope': spec['scale_plan']['core'], 'build_jobs': 4, 'test_jobs': 2,
                'source_archive_ready': True, 'offline_dependencies_ready': False,
                'target_build_outputs_preloaded': False, 'optional_incremental_enabled': False}
    (inputs / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    (task / 'source_context.json').write_text(json.dumps(context, ensure_ascii=False, indent=2) + '\n')
    (task / 'source_lock.json').write_text(json.dumps(source, ensure_ascii=False, indent=2) + '\n')
    update(task_id, stage='source_archive_locked', source_locked=True, release_ref=ref, source_sha256=checksum)
    print('SOURCE_LOCKED', task_id, ref, asset.stat().st_size, flush=True)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('ids', nargs='*')
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    ids = args.ids or [t['id'] for t in json.loads((ROOT / 'progress.json').read_text())['tasks']]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(prepare, tid): tid for tid in ids}
        for future in concurrent.futures.as_completed(futures):
            tid = futures[future]
            try:
                future.result()
            except Exception as error:
                update(tid, stage='source_acquisition_failed', source_locked=False, failure=str(error)[-1500:])
                print('SOURCE_FAILED', tid, type(error).__name__, str(error)[:300], flush=True)
