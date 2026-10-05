#!/usr/bin/env python3
"""Validate engineering task-design structure and referenced evidence, not builds."""
import argparse
import copy
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

TASK_FIELDS = '''id title_zh title_en project upstream_repo canonical_goal_key source_ids
source_task_or_workflow derivation_kind language_stack build_system planned_scale_class
agent_goal initial_state required_work build_recipe target_scope test_selection consumer_verification
deliverables continuation incremental_variant scale_plan resource_controls resource_shape_tags
backend_requirements offline_dependency_plan replay_notes oracle negative_cases new_builder_work
source_lineage related_prior_tasks implementation_priority limitations group readiness
reference_measurements resource_tags_status default_scenario task_brief_path agent_prompt_path'''.split()
SOURCE_FIELDS = '''id title url publisher source_type inspected_unit supports inspected_on
inspected_ref pinned_revision license_or_access_status'''.split()
LIST_FIELDS = '''source_ids language_stack build_system initial_state required_work
consumer_verification deliverables resource_controls resource_shape_tags backend_requirements
offline_dependency_plan replay_notes oracle negative_cases new_builder_work source_lineage limitations'''.split()
STAGES = {
    'source_grounded_design':[],
    'instance_built':['source_dependency_lock','environment_lock','implementation_manifest'],
    'oracle_verified':['source_dependency_lock','environment_lock','implementation_manifest','oracle_report'],
    'trajectory_collected':['source_dependency_lock','environment_lock','implementation_manifest','oracle_report','trajectory_manifest'],
    'replay_verified':['source_dependency_lock','environment_lock','implementation_manifest','oracle_report','trajectory_manifest','replay_report'],
    'reference_profiled':['source_dependency_lock','environment_lock','implementation_manifest','oracle_report','trajectory_manifest','replay_report','reference_profile'],
}


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def data_errors(registry,sources):
    errors=[]
    tasks=registry.get('tasks',[]); records=sources.get('sources',[])
    expected={f'BUILDv1-{g}{i:02d}' for g in 'ABCDEF' for i in range(1,11)}
    ids=[t.get('id') for t in tasks]
    if len(tasks)!=60 or set(ids)!=expected or len(set(ids))!=len(ids):
        errors.append('Expected 60 unique task IDs A01 through F10.')
    if registry.get('metadata',{}).get('task_count')!=len(tasks):
        errors.append('Metadata task_count does not match records.')
    source_ids=[s.get('id') for s in records]
    if len(source_ids)!=len(set(source_ids)):
        errors.append('Duplicate source IDs.')
    source_set=set(source_ids)
    if sources.get('metadata',{}).get('source_record_count')!=len(records):
        errors.append('Source count mismatch.')
    if sources.get('metadata',{}).get('unique_url_count')!=len({s.get('url') for s in records}):
        errors.append('Unique source URL count mismatch.')
    for s in records:
        sid=s.get('id','?')
        for key in SOURCE_FIELDS:
            if key not in s or (key!='pinned_revision' and not s[key]):
                errors.append(f'{sid}: missing source field {key}.')
        if not str(s.get('url','')).startswith('https://'):
            errors.append(f'{sid}: source URL must be HTTPS.')
    goals=[]; repos=[]
    for t in tasks:
        tid=t.get('id','?')
        for key in TASK_FIELDS:
            if key not in t:
                errors.append(f'{tid}: missing {key}.')
        for key in LIST_FIELDS:
            if not isinstance(t.get(key),list) or not t.get(key):
                errors.append(f'{tid}: {key} must be a nonempty list.')
        for key in ['agent_goal','source_task_or_workflow','target_scope','test_selection','continuation','related_prior_tasks']:
            if not t.get(key):
                errors.append(f'{tid}: empty {key}.')
        if t.get('group') not in 'ABCDEF' or not str(tid).startswith('BUILDv1-'+str(t.get('group'))):
            errors.append(f'{tid}: group/ID mismatch.')
        if t.get('planned_scale_class') not in ['small','medium','large','very_large']:
            errors.append(f'{tid}: invalid planned size.')
        if t.get('implementation_priority') not in ['pilot','standard','advanced']:
            errors.append(f'{tid}: invalid priority.')
        for sid in t.get('source_ids',[]):
            if sid not in source_set:
                errors.append(f'{tid}: unknown source ID {sid}.')
        if not isinstance(t.get('build_recipe'),dict) or any(not t['build_recipe'].get(k) for k in ['configure','build','package','test']):
            errors.append(f'{tid}: incomplete configure/build/package/test recipe.')
        if not isinstance(t.get('scale_plan'),dict) or any(not t['scale_plan'].get(k) for k in ['core','reference','extended']):
            errors.append(f'{tid}: incomplete core/reference/extended profiles.')
        if not isinstance(t.get('incremental_variant'),dict) or not t['incremental_variant']:
            errors.append(f'{tid}: missing optional incremental contract.')
        if t.get('default_scenario')!='clean-source-build':
            errors.append(f'{tid}: unexpected baseline scenario.')
        stage=t.get('readiness',{}).get('stage')
        if stage not in STAGES:
            errors.append(f'{tid}: invalid readiness stage.')
        else:
            ev=t['readiness'].get('evidence',{})
            for key in STAGES[stage]:
                item=ev.get(key)
                if not isinstance(item,dict) or not item.get('path') or not re.fullmatch('[0-9a-f]{64}',str(item.get('sha256',''))):
                    errors.append(f'{tid}: stage {stage} needs real {key} path and SHA-256.')
        measurements=t.get('reference_measurements',{})
        if stage=='source_grounded_design' and any(v is not None for v in measurements.values()):
            errors.append(f'{tid}: design-only record cannot claim reference measurements.')
        if stage=='reference_profiled' and any(measurements.get(k) is None for k in ['tool_active_wall_s','host_cpu_core_s','host_memory_peak_gib','workspace_peak_gib']):
            errors.append(f'{tid}: profiled stage lacks core measurements.')
        goals.append(t.get('canonical_goal_key'))
        repos.append(str(t.get('upstream_repo','')).rstrip('/').removesuffix('.git').lower())
    if len(goals)!=len(set(goals)):
        errors.append('Duplicate canonical goals.')
    if len(repos)!=len(set(repos)):
        errors.append('Duplicate primary repositories: review task independence.')
    return errors


def file_errors(root,registry):
    errors=[]
    lines=[json.loads(s) for s in (root/'tasks.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()]
    if lines!=registry['tasks']:
        errors.append('tasks.jsonl must contain exact full registry records in order.')
    for t in registry['tasks']:
        for key in ['task_brief_path','agent_prompt_path']:
            path=root/t[key]
            if not path.is_file() or t['id'] not in path.read_text(encoding='utf-8'):
                errors.append(f'{t["id"]}: missing or mismatched {key}.')
        for key,item in t['readiness'].get('evidence',{}).items():
            if item is None:
                continue
            if not isinstance(item,dict) or not item.get('path'):
                errors.append(f'{t["id"]}: invalid evidence {key}.'); continue
            path=(root/item['path']).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file():
                errors.append(f'{t["id"]}: missing/out-of-scope evidence {key}.'); continue
            if hashlib.sha256(path.read_bytes()).hexdigest()!=item.get('sha256'):
                errors.append(f'{t["id"]}: evidence hash mismatch for {key}.')
    for name in ['BUILD_SCENARIOS.md','SOURCE_AND_DEPENDENCIES.md','TEST_AND_ORACLE.md','MEASUREMENT.md','REPLAY_AND_STATE.md','BACKEND_CAPABILITIES.md','CODEX_HANDOFF.md','DEDUP_AND_SCOPE.md','SIZE_AND_PILOTS.md','TASK_CATALOG.md','SOURCES.md','README.md']:
        if not (root/name).is_file():
            errors.append(f'Missing common guide {name}.')
    for path in root.rglob('*.md'):
        text=path.read_text(encoding='utf-8')
        if text.count('```')%2:
            errors.append(f'Unbalanced fenced code block: {path.relative_to(root)}.')
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',text):
            if re.match(r'(https?://|mailto:|#)',target):
                continue
            dest=(path.parent/target.split('#',1)[0]).resolve()
            if not dest.exists():
                errors.append(f'Broken local link in {path.relative_to(root)}: {target}.')
    for path in (root/'templates').glob('*.json'):
        if read_json(path).get('status')!='template':
            errors.append(f'Template status missing: {path.name}.')
    return errors


def self_checks(registry,sources):
    cases={}
    dup=copy.deepcopy(registry); dup['tasks'][1]['id']=dup['tasks'][0]['id']
    cases['duplicate_id_rejected']=bool(data_errors(dup,sources))
    missing=copy.deepcopy(registry); missing['tasks'][0]['source_ids']=['MISSING-SOURCE']
    cases['missing_source_rejected']=bool(data_errors(missing,sources))
    false_stage=copy.deepcopy(registry); false_stage['tasks'][0]['readiness']['stage']='reference_profiled'
    cases['unsupported_readiness_claim_rejected']=bool(data_errors(false_stage,sources))
    empty=copy.deepcopy(registry); empty['tasks'][0]['test_selection']=''
    cases['empty_test_spec_rejected']=bool(data_errors(empty,sources))
    measured=copy.deepcopy(registry); measured['tasks'][0]['readiness']['stage']='source_grounded_design'; measured['tasks'][0]['reference_measurements']['host_cpu_core_s']=123
    cases['invented_reference_measurement_rejected']=bool(data_errors(measured,sources))
    return cases


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    p.add_argument('--self-check',action='store_true')
    p.add_argument('--write-report',action='store_true')
    args=p.parse_args(); root=args.root.resolve()
    registry=read_json(root/'task_registry.json'); sources=read_json(root/'sources.json')
    errors=data_errors(registry,sources)+file_errors(root,registry)
    checks=self_checks(registry,sources) if args.self_check else {}
    if checks and not all(checks.values()):
        errors.append('A validator negative self-check failed.')
    report={'validation_scope':'task-design structure, source references, local views and readiness evidence; not project compilation',
            'status':'passed' if not errors else 'failed','task_count':len(registry['tasks']),
            'group_counts':dict(Counter(t['group'] for t in registry['tasks'])),
            'source_record_count':len(sources['sources']),
            'negative_self_checks':checks,'errors':errors}
    if args.write_report:
        (root/'VALIDATION_REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    raise SystemExit(0 if not errors else 1)


if __name__=='__main__':
    main()
