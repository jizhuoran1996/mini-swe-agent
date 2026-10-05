#!/usr/bin/env python3
"""Validate source-bound design records. This never executes a GPU task."""
import argparse
import copy
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

REQUIRED = (
    'id title_zh title_en group workflow_family canonical_goal_key '
    'source_task_or_workload source_ids derivation_kind agent_goal inputs '
    'required_work deliverables continuation oracle negative_cases scale_plan '
    'gpu_rationale resource_shape_tags gpu_capabilities backend_requirements '
    'replay_notes new_builder_work distinct_from_related_tasks '
    'implementation_priority limitations readiness reference_measurements '
    'agent_prompt_path task_brief_path data_lineage'
).split()
SOURCE_REQUIRED = (
    'id title url publisher source_type inspected_unit supports inspected_on '
    'inspected_ref pinned_revision asset_license_status'
).split()
STAGES = ['design', 'built', 'verified', 'replayed', 'profiled', 'resource_admitted']
EVIDENCE = {
    'built': ['asset_lock', 'environment_lock', 'implementation_manifest'],
    'verified': ['oracle_report'],
    'replayed': ['trajectory_manifest', 'replay_report'],
    'profiled': ['reference_profile'],
    'resource_admitted': ['admission_report'],
}
MEASUREMENTS = [
    'gpu_count', 'session_wall_s', 'tool_active_wall_s', 'gpu_allocated_device_s',
    'device_memory_peak_gib', 'device_memory_integral_gib_s',
    'host_cpu_core_s', 'host_memory_integral_gib_s', 'workspace_peak_gib',
    'h2d_bytes', 'd2h_bytes', 'inter_gpu_bytes'
]
HEX64 = re.compile(r'^[0-9a-f]{64}$')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def validate(root, registry, sources, check_files=True):
    errors = []
    tasks = registry.get('tasks', [])
    src = sources.get('sources', [])
    ids = [t.get('id') for t in tasks]
    expected = {f'GPUv1-{g}{i:02d}' for g in 'ABCDEF' for i in range(1, 11)}
    if len(tasks) != 60 or set(ids) != expected:
        errors.append('Expected exactly GPUv1-A01 through GPUv1-F10 (60 IDs).')
    if len(ids) != len(set(ids)):
        errors.append('Duplicate task ID.')
    keys = [t.get('canonical_goal_key') for t in tasks]
    if len(keys) != len(set(keys)):
        errors.append('Duplicate canonical goal key; review variants/deduplication.')
    src_ids = [s.get('id') for s in src]
    if len(src_ids) != len(set(src_ids)):
        errors.append('Duplicate source ID.')
    known_sources = set(src_ids)
    for s in src:
        prefix = str(s.get('id', 'source'))
        for k in SOURCE_REQUIRED:
            if k not in s or (s[k] is None and k != 'pinned_revision'):
                errors.append(f'{prefix}: missing source field {k}.')
        u = urlparse(str(s.get('url', '')))
        if u.scheme not in ('https', 'http') or not u.netloc or u.username or u.password:
            errors.append(f'{prefix}: invalid public source URL.')
    for t in tasks:
        prefix = str(t.get('id', 'task'))
        for k in REQUIRED:
            if k not in t or t[k] is None or t[k] == '' or t[k] == []:
                errors.append(f'{prefix}: missing required field {k}.')
        if not set(t.get('source_ids', [])).issubset(known_sources):
            errors.append(f'{prefix}: unknown source reference.')
        if not t.get('source_ids'):
            errors.append(f'{prefix}: unbound source workload.')
        if t.get('implementation_priority') not in ('pilot', 'standard', 'advanced'):
            errors.append(f'{prefix}: invalid priority.')
        if t.get('derivation_kind') not in (
            'native_benchmark_adaptation', 'official_workflow_adaptation',
            'benchmark_data_plus_official_implementation'
        ):
            errors.append(f'{prefix}: invalid derivation kind.')
        for key in ('debug', 'reference_large', 'optional_scale_out'):
            v = t.get('scale_plan', {}).get(key)
            if not isinstance(v, dict) or not v:
                errors.append(f'{prefix}: missing concrete scale plan {key}.')
        for key in ('oracle', 'negative_cases', 'required_work', 'deliverables'):
            if len(t.get(key, [])) < 2:
                errors.append(f'{prefix}: insufficient {key}.')
        if prefix.startswith('GPUv1-') and t.get('group') != prefix[6]:
            errors.append(f'{prefix}: group mismatch.')
        state = t.get('readiness', {})
        stage = state.get('stage')
        if stage not in STAGES:
            errors.append(f'{prefix}: invalid readiness stage.')
            continue
        evidence = state.get('evidence', {})
        for passed in STAGES[1:STAGES.index(stage) + 1]:
            for key in EVIDENCE[passed]:
                e = evidence.get(key)
                if not isinstance(e, dict) or not e.get('path') or not HEX64.fullmatch(str(e.get('sha256', ''))):
                    errors.append(f'{prefix}: stage {stage} requires {key} path + sha256.')
                    continue
                path = root / e['path']
                try:
                    path.resolve().relative_to(root.resolve())
                except ValueError:
                    errors.append(f'{prefix}: evidence escapes package root.')
                    continue
                if check_files:
                    if not path.is_file():
                        errors.append(f'{prefix}: missing evidence file {e["path"]}.')
                    elif hashlib.sha256(path.read_bytes()).hexdigest() != e['sha256']:
                        errors.append(f'{prefix}: evidence hash mismatch {key}.')
        measurements = t.get('reference_measurements', {})
        for key in MEASUREMENTS:
            if key not in measurements:
                errors.append(f'{prefix}: missing measurement slot {key}.')
        if stage == 'design' and any(v is not None for v in measurements.values()):
            errors.append(f'{prefix}: design-only task cannot claim measured resource values.')
        if STAGES.index(stage) >= STAGES.index('profiled'):
            for key in ('gpu_count', 'session_wall_s', 'device_memory_peak_gib'):
                if not isinstance(measurements.get(key), (float, int)) or isinstance(measurements.get(key), bool) or measurements[key] < 0:
                    errors.append(f'{prefix}: profiled stage requires measured {key}.')
        for key in ('agent_prompt_path', 'task_brief_path'):
            value = t.get(key, '')
            path = root / value
            try:
                path.resolve().relative_to(root.resolve())
            except ValueError:
                errors.append(f'{prefix}: unsafe generated path.')
                continue
            if check_files and not path.is_file():
                errors.append(f'{prefix}: missing generated {key}.')
    if check_files:
        p = root / 'tasks.jsonl'
        try:
            rows = [json.loads(line) for line in p.read_text(encoding='utf-8').splitlines() if line.strip()]
            if rows != tasks:
                errors.append('tasks.jsonl differs from task_registry.json.')
        except (OSError, ValueError) as exc:
            errors.append(f'tasks.jsonl could not be read: {exc}')
        for folder in ('task_briefs', 'agent_prompts'):
            if len(list((root / folder).glob('GPUv1-*.md'))) != 60:
                errors.append(f'{folder}: expected 60 Markdown files.')
        for required_file in (
            'README.md', 'TASK_CATALOG.md', 'SOURCES.md', 'GPU_ADMISSION.md',
            'REPLAY_AND_STATE.md', 'INSTANCE_AND_ORACLE.md', 'CLOUD_SCENARIOS.md',
            'DATA_AND_SCALE.md', 'BACKEND_CAPABILITIES.md', 'CODEX_HANDOFF.md',
            'DEDUP_AND_LINEAGE.md', 'KNOWN_GAPS.md', 'STRUCTURE.md'
        ):
            if not (root / required_file).is_file():
                errors.append(f'Missing documentation: {required_file}.')
    return errors


def negative_checks(root, registry, sources):
    checks = {}
    changed = copy.deepcopy(registry)
    changed['tasks'][1]['id'] = changed['tasks'][0]['id']
    checks['duplicate_id_rejected'] = bool(validate(root, changed, sources, False))
    changed = copy.deepcopy(registry)
    changed['tasks'][0]['source_ids'] = ['NO_SUCH_SOURCE']
    checks['unbound_source_rejected'] = bool(validate(root, changed, sources, False))
    changed = copy.deepcopy(registry)
    changed['tasks'][0]['readiness']['stage'] = 'profiled'
    checks['unsupported_profile_claim_rejected'] = bool(validate(root, changed, sources, False))
    changed = copy.deepcopy(registry)
    changed['tasks'][0]['reference_measurements']['gpu_count'] = 1
    checks['invented_design_measurement_rejected'] = bool(validate(root, changed, sources, False))
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--self-check', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    registry = read_json(root / 'task_registry.json')
    sources = read_json(root / 'sources.json')
    errors = validate(root, registry, sources)
    checks = negative_checks(root, registry, sources) if args.self_check else {}
    if checks and not all(checks.values()):
        errors.append('A validator negative control failed.')
    tasks = registry['tasks']
    report = {
        'validation_scope': 'Design-package structure and consistency only; no GPU execution.',
        'passed': not errors,
        'task_count': len(tasks),
        'source_record_count': len(sources['sources']),
        'unique_source_urls': len({s['url'] for s in sources['sources']}),
        'groups': dict(sorted(Counter(t['group'] for t in tasks).items())),
        'priorities': dict(sorted(Counter(t['implementation_priority'] for t in tasks).items())),
        'readiness': dict(sorted(Counter(t['readiness']['stage'] for t in tasks).items())),
        'negative_controls': checks,
        'errors': errors,
    }
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == '__main__':
    sys.exit(main())
