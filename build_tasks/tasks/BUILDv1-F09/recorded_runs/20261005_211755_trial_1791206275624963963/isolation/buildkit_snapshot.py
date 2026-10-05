"""Shared execution and evidence plumbing; project recipes are authored by Flash."""
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import tarfile
import time


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


class Session:
    def __init__(self, input_dir, output_dir, jobs=4):
        self.input = Path(input_dir).resolve()
        self.output = Path(output_dir).resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.src = Path('/workspace/src')
        self.build = Path('/workspace/build')
        self.install = self.output / 'install'
        self.consumer = Path('/workspace/consumer')
        self.jobs = min(int(jobs), 4)
        self.manifest = json.loads((self.input / 'manifest.json').read_text())
        self.commands = []
        self.tests = []
        self.started = time.time()
        for p in [self.src, self.build, self.install, self.consumer, self.output / 'logs']:
            p.mkdir(parents=True, exist_ok=True)

    def prepare(self):
        archive = self.input / self.manifest['source']['filename']
        if digest(archive) != self.manifest['source']['sha256']:
            raise ValueError('source archive checksum mismatch')
        if any(self.src.iterdir()) or any(self.build.iterdir()) or any(self.install.iterdir()):
            raise ValueError('clean build requires empty source/build/install directories')
        with tarfile.open(archive) as source:
            for member in source.getmembers():
                parts = Path(member.name).parts
                if not parts or '..' in parts or Path(member.name).is_absolute():
                    raise ValueError('unsafe source archive member')
                if len(parts) == 1:
                    continue
                member.name = str(Path(*parts[1:]))
                source.extract(member, self.src, filter='data')
        return self.src

    def run(self, argv, cwd=None, phase='build', name=None, env=None, timeout=7200, check=True):
        if self.manifest['task_id']=='BUILDv1-F01':
            for name in ['tbb','QNNPACK','asmjit','gloo','cutlass']:
                license=self.src/'third_party'/name/'LICENSE'
                if license.exists() and license.read_text(errors='replace').startswith('Placeholder license for a submodule'):
                    raise ValueError('Generated placeholder input rejected: '+str(license))
        if isinstance(argv, str):
            raise TypeError('commands must be explicit argument lists')
        number = len(self.commands)
        name = re.sub(r'[^A-Za-z0-9_.-]', '_', name or phase)
        log = self.output / 'logs' / f'{number:03d}_{name}.log'
        started = time.time()
        record = {'index': number, 'argv': [str(a) for a in argv], 'cwd': str(cwd or self.src), 'phase': phase,
                  'log': str(log.relative_to(self.output)), 'started_unix': started}
        process_env = os.environ.copy()
        process_env.update({str(k): str(v) for k, v in (env or {}).items()})
        reason = None
        limit = 128 * 2**20
        process = subprocess.Popen(record['argv'], cwd=record['cwd'], env=process_env,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        written = 0
        with log.open('wb') as stream:
            while selector.get_map():
                if time.time() - started > timeout:
                    reason = 'command wall deadline exceeded'
                if reason:
                    os.killpg(process.pid, signal.SIGKILL)
                    break
                events = selector.select(timeout=1)
                for key, _ in events:
                    data = os.read(key.fileobj.fileno(), 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    remaining = limit - written
                    stream.write(data[:remaining]); written += min(len(data),remaining)
                    if len(data) > remaining:
                        reason = 'command log exceeds 128 MiB limit'
                        break
            if reason:
                stream.write(('\n[CONTROLLER RESOURCE STOP: ' + reason + ']\n').encode())
        selector.close(); process.stdout.close()
        process.wait(timeout=15)
        record.update(exit_code=process.returncode, wall_seconds=time.time() - started,
                      log_sha256=digest(log), log_limit_bytes=limit, resource_stop=reason)
        if reason and process.returncode == 0:
            record['exit_code'] = 125
        self.commands.append(record)
        self.write('commands.json', self.commands)
        if check and (process.returncode or reason):
            tail = log.read_bytes()[-10000:].decode(errors='replace')
            raise RuntimeError(f'{phase} command failed ({process.returncode}): {argv}\n{tail}')
        return log

    def test(self, name, argv, cwd=None, parser='auto', env=None, timeout=3600):
        log = self.run(argv, cwd=cwd, phase='official_test', name=name, env=env, timeout=timeout)
        text = log.read_text(errors='replace')
        count = None
        kind = None
        patterns = [
            ('pytest_cases', r'(\d+) passed(?:,| in|$)'),
            ('gtest_cases', r'\[\s*PASSED\s*\]\s+(\d+) tests?'),
            ('ctest_registered_targets', r'\d+% tests passed,\s*\d+ tests failed out of (\d+)'),
            ('unittest_cases', r'Ran (\d+) tests?'),
            ('mocha_cases', r'(?m)^\s*(\d+) passing(?:\s|\()'),
            ('meson_registered_targets', r'(?m)^Ok:\s*(\d+)\s*$'),
            ('cpython_cases', r'Total tests:\s*run=([\d,]+)'),
            ('ruby_cases', r'(\d+) tests, (\d+) assertions'),
            ('junit_cases', r'Tests run:\s*(\d+)'),
            ('dejagnu_pass', r'# of expected passes\s+(\d+)'),
            ('tap_assertions', r'(?m)^1\.\.(\d+)\s*$'),
        ]
        for label, pattern in patterns:
            matches = re.findall(pattern, text)
            if matches and (parser == 'auto' or parser in label):
                count = sum(int((m[0] if isinstance(m, tuple) else m).replace(',','')) for m in matches)
                kind = label
                break
        record = {'selector': name, 'command_index': len(self.commands) - 1, 'exit_code': 0,
                  'parsed_count': count, 'count_unit': kind, 'raw_log': str(log.relative_to(self.output)),
                  'nonempty_log': bool(text.strip()), 'log_sha256': digest(log)}
        self.tests.append(record)
        self.write('tests.json', self.tests)
        empty = re.search(r'No tests were found|no tests ran|collected 0 items|\b0 tests from 0 test suites', text, re.I)
        unexpected=re.findall(r'# of (?:unexpected failures|unexpected successes|unresolved testcases)\s+(\d+)',text)
        if any(int(value)>0 for value in unexpected):
            raise RuntimeError('official DejaGNU suite reported unexpected results: '+name)
        all_skipped = bool(re.search(r'\d+ skipped.* in ',text)) and 'pytest' in ' '.join(str(x) for x in argv) and not re.search(r'\b[1-9]\d* passed',text)
        if kind=='ctest_registered_targets':
            skipped=len(re.findall(r'\*\*\*Skipped',text))
            record['registered_targets_skipped']=skipped
            all_skipped=skipped>=count
        self.write('tests.json',self.tests)
        if not text.strip() or count == 0 or empty or all_skipped:
            raise RuntimeError('empty official test evidence: ' + name)
        return log

    def write(self, name, value):
        path = self.output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

    def finish(self, features=None):
        if not self.tests:
            raise RuntimeError('no official tests were executed')
        failed = [command for command in self.commands
                  if command['phase'] == 'official_test' and command['exit_code'] != 0]
        if failed:
            raise RuntimeError('official tests failed; refusing successful completion')
        files = [p for p in self.install.rglob('*') if p.is_file() and not p.is_symlink()]
        if not files and not list(self.output.glob('*.whl')):
            raise RuntimeError('no installed artifacts or source-built wheel')
        self.write('install_manifest.json', [{'path': str(p.relative_to(self.install)), 'bytes': p.stat().st_size,
                                             'sha256': digest(p)} for p in files])
        if files:
            with tarfile.open(self.output / 'install.tar.gz', 'w:gz') as archive:
                archive.add(self.install, arcname='install')
        self.write('run.json', {'task_id': self.manifest['task_id'], 'source': self.manifest['source'],
                               'profile': self.manifest['profile'], 'features': features or {},
                               'wall_seconds': time.time() - self.started,
                               'official_selectors': [t['selector'] for t in self.tests],
                               'execution_complete': True, 'independent_verified': False})
