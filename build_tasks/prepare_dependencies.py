"""Bounded online resolution, followed by separately frozen offline build inputs."""
import argparse
import json
from pathlib import Path
import time
from container import ROOT,Sandbox
from prepare_sources import sha

SCRIPT=r'''
import json,os,subprocess,tarfile
from pathlib import Path
import buildkit
s=buildkit.Session('/workspace/input','/workspace/output',jobs=2);s.prepare()
import urllib.parse
proxy=urllib.parse.urlsplit(os.environ.get('HTTPS_PROXY',''))
if proxy.hostname:
 java_proxy=' -Dhttp.proxyHost='+proxy.hostname+' -Dhttp.proxyPort='+str(proxy.port)+' -Dhttps.proxyHost='+proxy.hostname+' -Dhttps.proxyPort='+str(proxy.port)+' -Dhttp.nonProxyHosts=localhost|127.*|repo.maven.apache.org|repo.maven.org|repo.gradle.org'
 for n in ['MAVEN_OPTS','GRADLE_OPTS','JAVA_OPTS']:os.environ[n]=os.environ.get(n,'')+java_proxy
id=s.manifest['task_id'];env=os.environ.copy();env.update(GOPROXY='https://proxy.golang.org',GOSUMDB='sum.golang.org',GOTOOLCHAIN='local',PATH='/opt/bootstrap/go/bin:'+env['PATH'])
if id in ['BUILDv1-D08']:
 for p in sorted(s.src.rglob('go.mod')):
  if 'vendor' in p.parts:continue
  s.run(['go','mod','download'],cwd=p.parent,phase='dependency_resolution',name='gomod_'+str(p.parent.relative_to(s.src)).replace('/','_'),env=env,timeout=1800)
 kind='go-mod'
elif id in ['BUILDv1-E06','BUILDv1-E07','BUILDv1-E08','BUILDv1-E10']:
 env.update(npm_config_cache='/workspace/cache/npm',npm_config_audit='false',npm_config_fund='false')
 if (s.src/'package-lock.json').exists():
  s.run(['npm','ci','--ignore-scripts','--no-audit','--no-fund','--loglevel','verbose'],cwd=s.src,phase='dependency_resolution',name='npm_ci_no_target_build',env=env,timeout=1800)
 elif (s.src/'yarn.lock').exists():
  env.update(YARN_ENABLE_SCRIPTS='false',YARN_ENABLE_GLOBAL_CACHE='false',YARN_CACHE_FOLDER='/workspace/cache/yarn')
  s.run(['yarn','install','--immutable'],cwd=s.src,phase='dependency_resolution',name='yarn_resolution_no_target_build',env=env,timeout=1800)
 else:raise RuntimeError('no pinned npm/yarn lockfile')
 for cargo_manifest in [s.src/'Cargo.toml',s.src/'rust/Cargo.toml']:
  if cargo_manifest.is_file():
   cargo_env=env.copy();cargo_env.update(CARGO_HTTP_MULTIPLEXING='false',CARGO_NET_RETRY='3',CARGO_ENCODED_RUSTFLAGS='')
   s.run(['cargo','fetch','--locked','--manifest-path',str(cargo_manifest)],cwd=cargo_manifest.parent,phase='dependency_resolution',name='cargo_fetch_no_target_build',env=cargo_env,timeout=1800)
 kind='node'
 assert any(Path('/workspace/cache/npm/_cacache').rglob('*')) if (Path('/workspace/cache/npm/_cacache').exists()) else any(Path('/workspace/cache/yarn').glob('*.zip')), 'dependency package cache must be nonempty'
elif id in ['BUILDv1-E02','BUILDv1-E03']:
 selected='core' if id=='BUILDv1-E02' else 'flink-core'
 s.run(['mvn','-B','-Dmaven.repo.local=/workspace/cache/maven','-DskipTests','-Dcheckstyle.skip','-Drat.skip=true','-pl',selected,'-am','dependency:go-offline'],cwd=s.src,phase='dependency_resolution',name='maven_dependencies_only',env=env,timeout=3000)
 kind='maven'
elif id in ['BUILDv1-E01','BUILDv1-E04','BUILDv1-E05']:
 selected={ 'BUILDv1-E01':':clients','BUILDv1-E04':':lucene:core','BUILDv1-E05':':server'}[id]
 init=Path('/workspace/resolve.gradle');init.write_text('allprojects { p -> afterEvaluate { if (p.path == "'+selected+'") { tasks.register("resolveFrozenDependencies") { doLast { p.configurations.findAll { it.canBeResolved }.each { it.resolve() } } } } } }')
 s.run(['bash',str(s.src/'gradlew'),'--no-daemon','--max-workers=2','-I',str(init),selected+':resolveFrozenDependencies'],cwd=s.src,phase='dependency_resolution',name='gradle_dependency_resolution_only',env=env,timeout=3000)
 kind='gradle'
else:raise RuntimeError('resolver not implemented: '+id)
cache=Path('/workspace/cache')
selected={'go-mod':['go-mod'],'node':['npm','yarn','cargo'],'maven':['maven'],'gradle':['gradle']}[kind]
with tarfile.open(s.output/'dependencies.tar.gz','w:gz',compresslevel=1) as a:
 for key in selected:
  p=cache/key
  if p.exists():a.add(p,arcname=key)
if id=='BUILDv1-E04':
 wrapper=s.src/'gradle/wrapper/gradle-wrapper.jar'
 assert wrapper.is_file()
 import shutil
 shutil.copy2(wrapper,s.output/'gradle-wrapper.jar')
s.write('dependency_resolution.json',{'kind':kind,'target_compiled':False,'target_installation_exported':False,'cache_directories':selected})
'''


def prepare(task_id):
    task=ROOT/'tasks'/task_id;run=ROOT/'runs'/('prepare_'+task_id+'_'+str(time.time_ns()))
    run.mkdir(parents=True)
    script=run/'resolve.py';script.write_text(SCRIPT)
    with Sandbox(task_id+'-prepare',inputs=task/'input',report_dir=run/'isolation',preparation=True) as box:
        box.put(script,'/workspace/resolve.py');result=box.exec(['python3','resolve.py'],timeout=3500)
        collected=box.collect(run)
    (run/'result.json').write_text(json.dumps(result,indent=2))
    if result['exit_code'] or not collected['collected']:raise RuntimeError(result['output'][-3000:])
    archive=run/'output/dependencies.tar.gz';target=task/'input/dependencies.tar.gz';target.unlink(missing_ok=True);target.hardlink_to(archive)
    manifest=json.loads((task/'input/manifest.json').read_text());manifest['dependency_caches']=[{'filename':target.name,'bytes':target.stat().st_size,'sha256':sha(target),'preparation_run':run.name,'target_outputs_exported':False}]
    wrapper=run/'output/gradle-wrapper.jar'
    if wrapper.exists():
        import shutil
        destination=task/'input/gradle-wrapper.jar';shutil.copy2(wrapper,destination)
        manifest['dependency_source_overlays']=[{'filename':destination.name,'sha256':sha(destination),'bytes':destination.stat().st_size,'source_relative_destination':'gradle/wrapper/gradle-wrapper.jar','upstream_validation':'WrapperDownloader verifies official SHA256'}]
    manifest['offline_dependencies_ready']=True
    (task/'input/manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print('DEPENDENCIES_LOCKED',task_id,target.stat().st_size,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('ids',nargs='+');a=p.parse_args()
    for id in a.ids:
        try:prepare(id)
        except Exception as e:print('DEPENDENCY_FAILURE',id,str(e)[-2500:],flush=True)
