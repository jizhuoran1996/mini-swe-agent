"""Resolve pinned Bazel repositories in a bounded preparation container."""
import argparse
import json
from pathlib import Path
import time

from container import ROOT, Sandbox
from prepare_sources import sha

SCRIPT = r'''
import hashlib,json,os,shutil,sys,tarfile
from pathlib import Path
import buildkit
s=buildkit.Session('/workspace/input','/workspace/output',jobs=2);s.prepare()
task=s.manifest['task_id']
version={'BUILDv1-F02':'6.5.0','BUILDv1-F03':'7.4.1','BUILDv1-D10':'7.6.0'}[task]
bazel='/opt/bazel/'+version+'/bazel'
cache=Path('/workspace/cache');repo=cache/'bazel_repository';base=cache/'bazel_output'
for item in s.manifest.get('dependency_caches',[]):
 if item['filename']!='bazel-dependencies.tar.gz':continue
 path=s.input/item['filename']
 with path.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==item['sha256']
 with tarfile.open(path) as previous:
  for member in previous:
   if Path(member.name).parts[0]=='bazel_repository':previous.extract(member,cache,filter='data')
env={'HERMETIC_PYTHON_VERSION':'3.12','CC':'/usr/bin/clang','CXX':'/usr/bin/clang++','GOPROXY':'https://proxy.golang.org','GOSUMDB':'sum.golang.org','NO_PROXY':'localhost,127.0.0.1,pypi.org,files.pythonhosted.org,repo.maven.apache.org','no_proxy':'localhost,127.0.0.1,pypi.org,files.pythonhosted.org,repo.maven.apache.org'}
if task=='BUILDv1-F02':
 env.update(TF_NEED_CUDA='0',TF_NEED_ROCM='0',TF_NEED_TENSORRT='0',TF_NEED_CLANG='1',CLANG_COMPILER_PATH='/usr/bin/clang',TF_SET_ANDROID_WORKSPACE='0',CC_OPT_FLAGS='-O2',PYTHON_BIN_PATH=sys.executable,PYTHON_LIB_PATH='/usr/local/lib/python3.12/dist-packages')
 s.run([sys.executable,'configure.py'],cwd=s.src,phase='dependency_configuration',name='tf_configure_no_target_build',env={**env,'PATH':'/opt/bazel/'+version+':'+os.environ['PATH']},timeout=180)
 targets=['//tensorflow/tools/pip_package:wheel','//tensorflow/python/kernel_tests/nn_ops:softmax_op_test','//tensorflow/python/saved_model:load_test']
 options=['--repo_env=HERMETIC_PYTHON_VERSION=3.12','--repo_env=WHEEL_NAME=tensorflow_cpu','--repo_env=USE_PYWRAP_RULES=1','--config=opt']
elif task=='BUILDv1-F03':
 s.run([sys.executable,'build/build.py','build','--wheels=jaxlib','--configure_only','--python_version=3.12','--bazel_path='+bazel,'--clang_path=/usr/bin/clang'],cwd=s.src,phase='dependency_configuration',name='jax_configure_no_target_build',env=env,timeout=180)
 targets=['//jaxlib/tools:build_wheel'];options=['--repo_env=HERMETIC_PYTHON_VERSION=3.12']
else:
 targets=['//source/exe:envoy-static','//test/common/http:header_map_impl_test'];options=['--config=clang']
command=[bazel,'--batch','--host_jvm_args=-Xmx3g','--output_base='+str(base),'build','--nobuild','--jobs=2','--local_ram_resources=4096','--repository_cache='+str(repo)]+options+targets
s.run(command,cwd=s.src,phase='dependency_resolution',name='bazel_fetch_no_target_build',env=env,timeout=3000)
assert repo.exists() and any(repo.rglob('file')),'Bazel repository download cache must be nonempty'
# Only repository inputs are exported. Execution root, action cache, compiled
# targets, and test outputs are deliberately excluded.
with tarfile.open(s.output/'bazel-dependencies.tar.gz','w:gz',compresslevel=1) as archive:
 archive.add(repo,arcname='bazel_repository')
 gomod=cache/'go-mod'
 if gomod.exists():archive.add(gomod,arcname='go-mod')
 external=base/'external'
 if external.exists():
  def export_input(member):
   if not member.issym():return member
   original=external/Path(member.name).relative_to('bazel_output/external')
   target=original.resolve(strict=True)
   if target.is_relative_to(external):
    member.linkname=os.path.relpath(target,original.parent)
    return member
   if target.is_file() and target.is_relative_to(s.src):
    member.type=tarfile.REGTYPE;member.size=target.stat().st_size;member.linkname=''
    return member
   return None
  archive.add(external,arcname='bazel_output/external',filter=export_input)
s.write('dependency_resolution.json',{'bazel_version':version,'targets':targets,'target_compiled':False,'target_installation_exported':False,'cache_directories':['bazel_repository','bazel_output/external']})
'''


def prepare(task_id: str) -> None:
    task = ROOT / 'tasks' / task_id
    run = ROOT / 'runs' / ('prepare_bazel_' + task_id + '_' + str(time.time_ns()))
    run.mkdir(parents=True)
    script = run / 'resolve.py'
    script.write_text(SCRIPT)
    with Sandbox(task_id + '-prepare', inputs=task / 'input',
                 report_dir=run / 'isolation', preparation=True) as box:
        box.put(script, '/workspace/resolve.py')
        result = box.exec(['python3', 'resolve.py'], timeout=3500)
        collected = box.collect(run)
    (run / 'result.json').write_text(json.dumps(result, indent=2))
    if result['exit_code'] or not collected['collected']:
        raise RuntimeError(result['output'][-4000:])
    archive = run / 'output/bazel-dependencies.tar.gz'
    target = task / 'input/bazel-dependencies.tar.gz'
    target.unlink(missing_ok=True)
    target.hardlink_to(archive)
    path = task / 'input/manifest.json'
    manifest = json.loads(path.read_text())
    manifest['dependency_caches'] = [item for item in manifest.get('dependency_caches', [])
                                     if item['filename'] != target.name] + [{
        'filename': target.name, 'bytes': target.stat().st_size,
        'sha256': sha(target), 'preparation_run': run.name,
        'target_outputs_exported': False,
    }]
    manifest['offline_dependencies_ready'] = True
    manifest['bazel_dependency_preparation'] = json.loads(
        (run / 'output/dependency_resolution.json').read_text())
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print('BAZEL_DEPENDENCIES_LOCKED', task_id, target.stat().st_size, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('ids', nargs='+')
    args = parser.parse_args()
    for task_id in args.ids:
        try:
            prepare(task_id)
        except Exception as error:
            print('BAZEL_DEPENDENCY_FAILURE', task_id, str(error)[-3500:], flush=True)
