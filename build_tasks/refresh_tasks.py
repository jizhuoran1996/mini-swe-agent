"""Refresh visible frozen bindings after an explicit source/dependency revision."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
for task in sorted((ROOT/'tasks').iterdir()):
    spec=json.loads((task/'source_spec.json').read_text())
    manifest=json.loads((task/'input/manifest.json').read_text())
    previous=(task/'TASK.md').read_text()
    prefix=previous.split('## Source and execution binding')[0]
    footer=previous.split('\n```\n')[-1]
    (task/'TASK.md').write_text(prefix+'## Source and execution binding\n\n```json\n'+json.dumps(manifest,ensure_ascii=False,indent=2)+'\n```\n'+footer)
