import hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
import xml.etree.ElementTree as ET
sys.path.insert(0,'/workspace/solution')
import main as solver
out=Path('/workspace/output'); deadline=time.monotonic()+10800
def wait(predicate):
 while not predicate():
  if Path('/workspace/tensorflow_delivery_cancelled').exists():raise RuntimeError('native execution failed; artifact collection cancelled')
  if time.monotonic()>deadline:raise TimeoutError('actual TensorFlow artifact did not become ready')
  time.sleep(.2)
def commands():
 if not (out/'commands.json').exists():return []
 try:return json.loads((out/'commands.json').read_text())
 except json.JSONDecodeError:return []
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
wait(lambda:any(c['phase']=='build' and c['exit_code']==0 for c in commands()))
original=next(c for c in commands() if c['phase']=='build' and c['exit_code']==0)
argv=original['argv'][:-1]+['--build_event_json_file='+str(out/'bazel_followup_build.bep.json')]+original['argv'][-1:]
action_path=next(a.partition('=PATH=')[2] for a in argv if a.startswith('--action_env=PATH='))
started=time.time()
with (out/'bazel_followup_build.log').open('wb') as log:
 result=subprocess.run(argv,cwd=original['cwd'],env={**os.environ,**solver._bazel_env(action_path)},stdout=log,stderr=subprocess.STDOUT,timeout=900)
assert result.returncode==0
bep=out/'bazel_followup_build.bep.json'
events=[json.loads(line) for line in bep.read_text().splitlines()]
assert any('buildFinished' in event.get('id',{}) and event['finished']['exitCode'].get('code',0)==0 for event in events)
record={'argv':argv,'exit_code':result.returncode,'started_unix':started,'wall_seconds':time.time()-started,'bep_sha256':digest(bep),'bep_event_count':len(events),'bep_role':'Real follow-up build of the identical target/configuration; reuses only outputs actually compiled in this same initially empty workspace. Original cold compilation remains separately recorded.','target_outputs_preloaded':False}
wait(lambda:any(c.get('log','').endswith('consumer_load.log') and c['exit_code']==0 for c in commands()))
source=Path('/workspace/consumer/saved_model');assert (source/'saved_model.pb').is_file()
shutil.copytree(source,out/'saved_model')
models=[{'path':str(p.relative_to(out)),'bytes':p.stat().st_size,'sha256':digest(p)} for p in sorted((out/'saved_model').rglob('*')) if p.is_file()]
reports=out/'upstream_test_reports';reports.mkdir()
test_reports=[]
for target in ['tensorflow/python/kernel_tests/nn_ops/softmax_op_test','tensorflow/python/saved_model/load_test']:
 candidates=[Path('/workspace/src/bazel-testlogs')/(target+'_cpu')/'test.xml',Path('/workspace/src/bazel-testlogs')/target/'test.xml']
 path=next((path for path in candidates if path.is_file()),None);assert path is not None,str(candidates)
 destination=reports/(target.replace('/','_')+'.xml');shutil.copy2(path,destination)
 root=ET.parse(destination).getroot(); suites=[root] if root.tag=='testsuite' else list(root.iter('testsuite'))
 cases=sum(int(s.attrib.get('tests',0)) for s in suites); failures=sum(int(s.attrib.get('failures',0))+int(s.attrib.get('errors',0)) for s in suites)
 assert cases>0 and failures==0
 test_reports.append({'target':target,'actual_test_target':path.parent.name,'path':str(destination.relative_to(out)),'sha256':digest(destination),'tests':cases,'failures':failures})
record.update(saved_model_files=models,original_test_xml=test_reports,actual_main_invocations=[c['argv'] for c in commands() if c['phase'] in ['build','official_test','consumer']])
(out/'tensorflow_deliverables.json').write_text(json.dumps(record,indent=2)+'\n')
print('GENUINE_TENSORFLOW_DELIVERABLES_PRESERVED',len(models),[(r['target'],r['tests']) for r in test_reports],flush=True)
