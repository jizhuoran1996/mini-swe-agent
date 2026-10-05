import json,shutil
from pathlib import Path
from assets import ROOT,dataset_rows,digest
from prepare_graphs import manifest
from replay_existing import replay
from grade_task import grade

task=ROOT/'tasks/GPUv1-A09';backup=task/'instances/debug_first_rows_v1';backup.mkdir(parents=True,exist_ok=True)
for name in ['input','oracle']:
    if not (backup/name).exists():shutil.copytree(task/name,backup/name)
if not (backup/'latest_run.json').exists():shutil.copy2(task/'latest_run.json',backup/'latest_run.json')
seen=set();selected=[]
for item in dataset_rows('rajpurkar/squad','plain_text','validation',1200):
    row=item['row']
    if row['context'] in seen:continue
    seen.add(row['context']);selected.append({'id':row['id'],'question':row['question'],'context':row['context'],'source_row_idx':item['row_idx']})
    if len(selected)==24:break
assert len(selected)==24
(task/'input/validation.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in selected))
old=json.loads((task/'input/manifest.json').read_text());old.pop('files',None)
old.update(instance_version='debug_distinct_contexts_v2',validation_selection='first24 unique context strings among first1200 native validation rows',unique_validation_contexts=24,previous_instance=str(backup),deviations=old['deviations']+['Validation now has24 distinct native passages; v1 artifacts are retained separately and not used to claim retrieval quality'])
manifest('GPUv1-A09',old)
print('A09 REFINED 24 distinct validation contexts',flush=True)
result=replay('GPUv1-A09','python solution/main.py train --input input --output output --epochs 1');print('replayed',result['solver_declared_complete'],flush=True);print(json.dumps(grade('GPUv1-A09')),flush=True)
