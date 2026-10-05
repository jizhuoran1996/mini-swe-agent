import argparse
import json
from pathlib import Path
import time
from container import ROOT, Sandbox
from status import update, write_json
from solution_review import review


def grade_task(task_id, run_directory=None, adopt=False):
    task=ROOT/'tasks'/task_id
    summary=json.loads((Path(run_directory)/'summary.json').read_text()) if run_directory else json.loads((task/'latest_run.json').read_text())
    run=Path(summary['run_directory'])
    if not run.is_absolute():
        run=ROOT/run
    revision=run/'flash_consumer_revision.json'
    if revision.exists():
        receipt=json.loads(revision.read_text())
        authored=Path(receipt['final_code_source_run'])
        delivery=json.loads((authored/'author_delivery.json').read_text())
        assert json.loads((run/'author_delivery.json').read_text())==delivery
        for name,content in delivery['files'].items():
            assert (run/'workspace'/name).read_bytes()==content.encode()
        response=json.loads((authored/'author_response.json').read_text())
        summary.update(code_source_run=str(authored),usage=response['usage'],
                       flash_consumer_revision=receipt)
    output=run/'workspace/output'
    if not (output/'run.json').exists():
        candidates=list(output.glob('*/run.json'))
        if len(candidates)==1:
            output=candidates[0].parent
    grading=run/('grading_'+str(time.time_ns()))
    source=run/'workspace/solution/main.py'
    if task_id=='BUILDv1-A02' and 'PAGER_C' in source.read_text():
        update(task_id,stage='solver_review_failed',built_from_source=False,official_tests_passed=False,independent_consumer_passed=False,failure='Custom pager replaces official CLI test dependency; use actual less and rerun.')
        print('REVIEW_REJECTED',task_id,'custom test dependency',flush=True)
        return {'passed':False,'failure':'custom pager replaces real less'}
    if task_id=='BUILDv1-C10' and 'ExternalData_Add_Target' in source.read_text() and 'suppressed (offline)' in source.read_text():
        update(task_id,stage='solver_review_failed',built_from_source=False,official_tests_passed=False,independent_consumer_passed=False,failure='Replacing upstream ExternalData fetch with a no-op is forbidden; use supported build options or real frozen data.')
        print('REVIEW_REJECTED',task_id,'mocked upstream data acquisition',flush=True)
        return {'passed':False,'failure':'mocked upstream data acquisition'}
    rejection=review(task_id,source.parent)
    if rejection:
        update(task_id,stage='solver_review_failed',built_from_source=False,official_tests_passed=False,independent_consumer_passed=False,failure=rejection)
        print('REVIEW_REJECTED',task_id,rejection,flush=True)
        return {'passed':False,'failure':rejection}
    with Sandbox(task_id+'-grade',inputs=task/'input',artifacts=output,report_dir=grading/'isolation') as sandbox:
        sandbox.put(ROOT/'grader_inside.py','/workspace/grader_inside.py')
        for module in ['grader_runtimes.py','grader_python.py','grader_media.py','grader_databases.py','grader_languages.py','grader_lightgbm.py']:
            sandbox.put(ROOT/module,'/workspace/'+module)
        result=sandbox.exec(['python3','grader_inside.py',task_id],timeout=600)
        collected=sandbox.collect(grading,evaluation_only=True)
    passed=result['exit_code']==0 and collected['collected'] and (grading/'output/evaluation/results.json').exists()
    evaluation=json.loads((grading/'output/evaluation/results.json').read_text()) if passed else {'passed':False,'failure':result['output'][-8000:]}
    (grading/'command.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    summary.update(built_from_source=passed,official_tests_passed=passed,independent_consumer_passed=passed,
                   evaluation=evaluation,evaluation_directory=str(grading))
    current=json.loads((task/'latest_run.json').read_text())
    current_result=current['run_directory']==str(run) or adopt and passed
    if adopt and passed:
        summary['selection_reason']='Independent verification of a preserved Flash-authored candidate'
    if current_result:
        write_json(task/'latest_run.json',summary)
    (run/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    if not current_result:
        print('GRADED_HISTORICAL_RUN',task_id,passed,flush=True)
        return evaluation
    update(task_id,built_from_source=passed,official_tests_passed=passed,independent_consumer_passed=passed,
           stage='core_independently_verified' if passed else 'independent_acceptance_failed',
           evaluation_path=str(grading/'output/evaluation/results.json') if passed else None,
           failure=None if passed else evaluation['failure'][-2000:])
    print('GRADED',task_id,passed,flush=True)
    return evaluation


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('ids',nargs='+')
    parser.add_argument('--run-directory')
    parser.add_argument('--adopt',action='store_true')
    args=parser.parse_args()
    for task_id in args.ids:
        grade_task(task_id,args.run_directory,args.adopt)
