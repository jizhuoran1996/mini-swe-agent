import argparse,time,shutil
import json
from pathlib import Path
from container import ROOT,Sandbox,run_path
from status import update

def grade(tid):
    task=ROOT/'tasks'/tid
    summary=json.loads((task/'latest_run.json').read_text())
    run=run_path(summary)
    if summary['guard_abort'] or not (run/'workspace/output').is_dir():
        update(tid,stage='solve_failed',failure=summary['guard_abort'] or 'solver turn limit')
        return {'passed':False,'failure':'solver did not finish'}
    scripts={'GPUv1-E03':'grade_e03_inside.py','GPUv1-A01':'grade_a01_inside.py',**{'GPUv1-A'+str(n).zfill(2):'grade_text_inside.py' for n in (3,10)},**{'GPUv1-E'+str(n).zfill(2):'grade_graphs_inside.py' for n in range(6,11)},'GPUv1-D08':'grade_services_inside.py','GPUv1-D09':'grade_services_inside.py'}
    scripts.update({k:'grade_adaptation_inside.py' for k in ['GPUv1-A08','GPUv1-A09','GPUv1-F10']})
    scripts.update({k:'grade_training_inside.py' for k in ['GPUv1-A04','GPUv1-A06','GPUv1-A07','GPUv1-B01','GPUv1-B04','GPUv1-B10','GPUv1-F01','GPUv1-F02']})
    scripts.update({k:'grade_data_inside.py' for k in ['GPUv1-E01','GPUv1-E02','GPUv1-E04','GPUv1-E05','GPUv1-F05']})
    scripts.update({k:'grade_detection_preference_inside.py' for k in ['GPUv1-A02','GPUv1-B02','GPUv1-B03']})
    scripts.update({k:'grade_generation_inside.py' for k in ['GPUv1-D01','GPUv1-D02','GPUv1-D03','GPUv1-D04','GPUv1-D05','GPUv1-D06','GPUv1-D07','GPUv1-D10']})
    scripts.update({f'GPUv1-C{n:02d}':'grade_media_inside.py' for n in range(1,11)})
    if tid not in scripts:raise ValueError('No frozen independent evaluator for '+tid)
    # Keep previous failed evaluations instead of overwriting their evidence.
    previous=[run/'evaluation_command.json',run/'evaluation_isolation',run/'graded']
    if any(p.exists() for p in previous):
        archive=run/'evaluation_history'/str(time.time_ns());archive.mkdir(parents=True)
        for p in previous:
            if p.exists():shutil.move(str(p),str(archive/p.name))
    with Sandbox(tid+'-grade',inputs=task/'input',models=ROOT/'assets/models',artifacts=run/'workspace',report_dir=run/'evaluation_isolation') as s:
        s.put(ROOT/scripts[tid],'/workspace/evaluate.py')
        if (task/'oracle/validation_labels.npy').exists():s.put(task/'oracle/validation_labels.npy','/workspace/validation_labels.npy')
        if tid=='GPUv1-F10':s.put(task/'oracle/validation_fields.npy','/workspace/validation_labels.npy')
        if (task/'oracle/references.json').exists():s.put(task/'oracle/references.json','/workspace/references.json')
        if tid=='GPUv1-C06':s.put(task/'oracle/clean','/workspace/clean')
        if tid=='GPUv1-E05':
            neighbors=ROOT/'benchmark_oracles/sift1m_neighbors.npy'
            if not neighbors.exists():neighbors=task/'oracle/neighbors.npy'
            if not neighbors.exists():neighbors=ROOT.parent/'pilot_gpu/oracle/neighbors.npy'
            s.put(neighbors,'/workspace/neighbors.npy')
        result=s.exec('python evaluate.py '+tid)
        (run/'evaluation_command.json').write_text(json.dumps(result,indent=2)+'\n')
        s.collect(run/'graded',names=('evaluation',))
    report_path=run/'graded/evaluation/results.json'
    report=json.loads(report_path.read_text()) if result['exit_code']==0 and report_path.exists() else {'passed':False,'failure':result['output'][-4000:]}
    summary['independent_evaluation_passed']=bool(report['passed'])
    summary['evaluation']=report
    (task/'latest_run.json').write_text(json.dumps(summary,indent=2)+'\n')
    (run/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    update(tid,stage='debug_passed' if report['passed'] else 'evaluation_failed',flash_solved=bool(report['passed'] or summary['solver_declared_complete']),container_tested=bool(report['passed']),failure=None if report['passed'] else report.get('failure'),evaluation_path=str(report_path))
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('task_id');args=parser.parse_args()
    print(json.dumps(grade(args.task_id),indent=2))
