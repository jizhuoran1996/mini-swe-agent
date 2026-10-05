import argparse
import json
from pathlib import Path
from author import request_files, save
from credentials import read_key
from status import ROOT


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('task_id')
    parser.add_argument('--feedback-file')
    args = parser.parse_args()
    key = read_key()
    task = ROOT / 'tasks' / args.task_id
    summary = json.loads((task / 'latest_run.json').read_text())
    run = Path(summary['run_directory'])
    delivery = json.loads((run / 'author_delivery.json').read_text())
    feedback = Path(args.feedback_file).read_text() if args.feedback_file else json.dumps({k: summary.get(k) for k in ['compilation','help','doctor','execution','guard_abort']}, ensure_ascii=False)
    fixed, raw = request_files(args.task_id, key, previous=delivery, feedback=feedback[-24000:])
    save(args.task_id,fixed,raw,suffix='repair',previous_delivery=delivery)
