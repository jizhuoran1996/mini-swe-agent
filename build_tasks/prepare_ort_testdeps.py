"""Cache genuine declared wheel dependencies for the fresh ORT consumer."""
import fcntl
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def prepare() -> None:
    with (ROOT / 'preparation.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with (ROOT / 'runs/runtime_ort_testdeps.log').open('w') as log:
            subprocess.run(['docker', 'build', '--memory=2g', '--memory-swap=2g',
                            '--cpu-period=100000', '--cpu-quota=200000',
                            '--label', 'sbench.build.runtime=true',
                            '-t', 'sbench-build-runtime:ort-testdeps', '-f',
                            str(ROOT / 'runtime/Dockerfile.ort-testdeps'),
                            str(ROOT / 'runtime')],
                           env={**os.environ, 'DOCKER_BUILDKIT': '0'},
                           stdout=log, stderr=subprocess.STDOUT, timeout=600, check=True)
    path = ROOT / 'runtime/policy.json'
    policy = json.loads(path.read_text())
    policy['task_image_overrides']['BUILDv1-F10'] = 'sbench-build-runtime:ort-testdeps'
    path.write_text(json.dumps(policy, indent=2) + '\n')
    print('GENUINE_ORT_DECLARED_DEPENDENCIES_READY', flush=True)


if __name__ == '__main__':
    prepare()
