"""Resource bounded, offline build sessions without host or GPU access."""
import fcntl
import io
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parent
POLICY = json.loads((ROOT / 'runtime/policy.json').read_text())


def call(argv, **kwargs):
    return subprocess.run(argv, capture_output=True, text=True, **kwargs)


class Sandbox:
    def __init__(self, task_id, inputs=None, artifacts=None, report_dir=None, preparation=False):
        self.policy = json.loads((ROOT/'runtime/policy.json').read_text())
        self.small_build = not preparation and task_id in {*(f'BUILDv1-A{i:02d}' for i in range(1,11)),'BUILDv1-B04','BUILDv1-B06','BUILDv1-B07','BUILDv1-B08','BUILDv1-C01','BUILDv1-C02','BUILDv1-C03','BUILDv1-C04','BUILDv1-C08','BUILDv1-D01','BUILDv1-D03','BUILDv1-D04','BUILDv1-D05','BUILDv1-D06','BUILDv1-D08','BUILDv1-D09','BUILDv1-E06','BUILDv1-E09','BUILDv1-F04','BUILDv1-F05','BUILDv1-F06','BUILDv1-F07','BUILDv1-F08','BUILDv1-F09'}
        self.small_build |= not preparation and self.policy.get('task_build_profiles', {}).get(task_id) == 'small_build'
        if self.small_build:
            self.policy.update(memory_gib=12,workspace_tmpfs_gib=8,cpu_count=4)
        self.light_build = not preparation and task_id=='BUILDv1-C06'
        self.light_build |= not preparation and self.policy.get('task_build_profiles', {}).get(task_id) == 'light_build'
        if self.light_build:
            self.policy.update(memory_gib=16,workspace_tmpfs_gib=12,cpu_count=4)
        self.micro_build = not preparation and self.policy.get('task_build_profiles', {}).get(task_id) == 'micro_build'
        if self.micro_build:
            self.policy.update(memory_gib=5, workspace_tmpfs_gib=4, cpu_count=2)
        self.medium_build = not preparation and not self.micro_build and task_id in {
            'BUILDv1-B03','BUILDv1-B05','BUILDv1-B10','BUILDv1-C09','BUILDv1-C10',
            'BUILDv1-D02','BUILDv1-E01','BUILDv1-E02','BUILDv1-E03','BUILDv1-E04',
            'BUILDv1-E05','BUILDv1-E07','BUILDv1-E08','BUILDv1-E10',
        }
        if self.medium_build:
            self.policy.update(memory_gib=16,workspace_tmpfs_gib=12,cpu_count=4)
        if preparation:
            self.policy.update(memory_gib=8, workspace_tmpfs_gib=8, cpu_count=2, task_wall_timeout_seconds=3600)
            if task_id=='BUILDv1-F02-prepare':
                self.policy.update(memory_gib=16,workspace_tmpfs_gib=12)
        elif task_id.endswith('-smoke'):
            self.policy.update(memory_gib=2,workspace_tmpfs_gib=2,cpu_count=1,task_wall_timeout_seconds=300)
        elif task_id.endswith('-grade'):
            self.policy.update(memory_gib=8,workspace_tmpfs_gib=8,cpu_count=2,task_wall_timeout_seconds=900)
        canonical=task_id.removesuffix('-grade').removesuffix('-smoke')
        override=self.policy.get('task_image_overrides',{}).get(canonical)
        if override and not preparation:self.policy['image']=override
        if task_id=='BUILDv1-F08':self.policy['pids_limit']=8192
        if task_id=='BUILDv1-B10':self.policy['pids_limit']=4096
        available=sorted(os.sched_getaffinity(0))
        offset=14 if preparation or self.micro_build else 18 if task_id.endswith('-smoke') else 16 if task_id.endswith('-grade') else 10 if self.small_build else 19 if self.light_build else 6 if self.medium_build else 0
        count=min(self.policy['cpu_count'],len(available))
        selected=available[offset:offset+count] if offset+count<=len(available) else available[:count]
        self.policy['cpu_affinity']=selected
        self.task_id = task_id
        self.inputs = Path(inputs).resolve() if inputs else None
        self.artifacts = Path(artifacts).resolve() if artifacts else None
        self.report_dir = Path(report_dir or ROOT / 'runs' / task_id)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.name = 'sbench-build-' + task_id.lower() + '-' + uuid.uuid4().hex[:8]
        self.preparation = preparation
        self.network_policy='bridge' if preparation else 'none'
        if self.inputs and not preparation and not task_id.endswith(('-grade','-smoke')):
            manifest=json.loads((self.inputs/'manifest.json').read_text())
            self.network_policy=manifest.get('network_policy','none')
            assert self.network_policy in ['none','bridge']
        self.policy['network']=self.network_policy
        self.created = False
        self.abort = None
        self.stop = threading.Event()

    def __enter__(self):
        self.lock = (ROOT / ('preparation.lock' if self.preparation or self.micro_build else 'grading.lock' if self.task_id.endswith('-grade') else 'smoke.lock' if self.task_id.endswith('-smoke') else 'light_build.lock' if self.light_build else 'small_build.lock' if self.small_build else 'medium_build.lock' if self.medium_build else 'execution.lock')).open('a+')
        fcntl.flock(self.lock, fcntl.LOCK_EX)
        if self.task_id=='BUILDv1-F02-prepare':
            self.extra_lock=(ROOT/'medium_build.lock').open('a+')
            fcntl.flock(self.extra_lock,fcntl.LOCK_EX)
        if shutil.disk_usage(ROOT).free < self.policy['host_disk_free_floor_gib'] * 2**30:
            self.close()
            raise RuntimeError('host disk reserve insufficient')
        memory = next(int(s.split()[1]) for s in Path('/proc/meminfo').read_text().splitlines() if s.startswith('MemAvailable:'))
        if memory * 1024 < (self.policy['memory_gib'] + self.policy['host_available_memory_floor_gib']) * 2**30:
            self.close()
            raise RuntimeError('host memory reserve insufficient')
        if self.inputs and not self.preparation:
            frozen=self.report_dir/'input_snapshot'
            frozen.mkdir()
            payload=(self.inputs/'manifest.json').read_bytes()
            json.loads(payload)
            (frozen/'manifest.json').write_bytes(payload)
            (self.report_dir/'input_manifest.json').write_bytes(payload)
            for item in self.inputs.iterdir():
                if item.is_file() and item.name!='manifest.json':
                    (frozen/item.name).hardlink_to(item)
            self.inputs=frozen.resolve()
            self.input_snapshot=frozen
            self.policy['input_manifest_sha256']=hashlib.sha256(payload).hexdigest()
        helper=self.report_dir/'buildkit_snapshot.py'
        shutil.copyfile(ROOT/'buildkit.py',helper)
        argv = ['docker', 'run', '-d', '--init', '--name', self.name, '--label', 'sbench.build.managed=true',
                '--network', self.network_policy, '--read-only', '--cap-drop', 'ALL',
                '--security-opt', 'no-new-privileges', '--user', f'{os.getuid()}:{os.getgid()}',
                '--memory', f"{self.policy['memory_gib']}g", '--memory-swap', f"{self.policy['memory_gib']}g",
                '--cpus', str(self.policy['cpu_count']), '--cpuset-cpus', ','.join(map(str,self.policy['cpu_affinity'])), '--pids-limit', str(self.policy['pids_limit']),
                '--shm-size', '1g', '--ulimit', 'core=0:0',
                '--ulimit', f"fsize={self.policy['single_file_max_gib'] * 2**30}:{self.policy['single_file_max_gib'] * 2**30}",
                '--tmpfs', f"/workspace:rw,exec,nosuid,nodev,size={self.policy['workspace_tmpfs_gib']}g,mode=1777",
                '--tmpfs', f"/tmp:rw,exec,nosuid,nodev,size={self.policy['temporary_tmpfs_gib']}g,mode=1777",
                '--mount', f'type=bind,src={helper.resolve()},dst=/opt/controller/buildkit.py,readonly',
                '--env', 'PYTHONPATH=/opt/controller', '--env', 'PATH=/opt/bootstrap/rust/bin:/opt/bootstrap/node/bin:/opt/node-tools/bin:/opt/bootstrap/go/bin:/opt/build-tools/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin', '--env', 'UV_THREADPOOL_SIZE=4', '--env', f"JAVA_TOOL_OPTIONS=-XX:ActiveProcessorCount={self.policy['cpu_count']} -XX:ParallelGCThreads=2 -XX:ConcGCThreads=1", '--env', 'OMP_NUM_THREADS=4', '--env', 'OPENBLAS_NUM_THREADS=4', '--env', 'MKL_NUM_THREADS=4',
                '--env', 'MAVEN_OPTS=-Xmx4g -XX:ActiveProcessorCount=4', '--env', 'GRADLE_OPTS=-Xmx4g -XX:ActiveProcessorCount=4', '--env','MAVEN_REPOSITORY=/workspace/cache/maven', '--env','YARN_CACHE_FOLDER=/workspace/cache/yarn',
                '--env', 'GOCACHE=/workspace/cache/go-build', '--env', 'GOMODCACHE=/workspace/cache/go-mod',
                '--env', 'GOPROXY=off', '--env', 'GOTOOLCHAIN=local', '--env', 'LIT_OPTS=-j 2',
                '--env', 'npm_config_cache=/workspace/cache/npm', '--env', 'CARGO_HOME=/workspace/cache/cargo',
                '--env', 'GRADLE_USER_HOME=/workspace/cache/gradle']
        if self.task_id.removesuffix('-smoke').removesuffix('-grade')=='BUILDv1-B10':
            index=next(i for i,value in enumerate(argv) if value.startswith('JAVA_TOOL_OPTIONS='))
            del argv[index-1:index+1]
        if self.task_id=='BUILDv1-F08':
            argv+=['--env','OMP_THREAD_LIMIT=128']
            self.policy['openmp_thread_limit']=128
        if self.preparation and (ROOT/'runs/asset_proxy.json').exists():
            proxy=json.loads((ROOT/'runs/asset_proxy.json').read_text())['url']
            for key in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy']:
                argv += ['--env',key+'='+proxy]
            argv += ['--env','NO_PROXY=localhost,127.0.0.1,repo.maven.apache.org,repo.maven.org,repo.gradle.org','--env','no_proxy=localhost,127.0.0.1,repo.maven.apache.org,repo.maven.org,repo.gradle.org']
        if self.inputs:
            argv += ['--mount', f'type=bind,src={self.inputs},dst=/workspace/input,readonly']
        if self.artifacts:
            argv += ['--mount', f'type=bind,src={self.artifacts},dst=/artifacts,readonly']
        argv += [self.policy['image'], 'sleep', 'infinity']
        result = call(argv, timeout=60)
        if result.returncode:
            self.close()
            raise RuntimeError(result.stderr[-3000:])
        (self.report_dir/'effective_policy.json').write_text(json.dumps(self.policy,indent=2))
        self.created = True
        self.started = time.time()
        (self.report_dir / 'container.json').write_text(call(['docker', 'inspect', self.name], timeout=10).stdout)
        self.thread = threading.Thread(target=self.watch, daemon=True)
        self.thread.start()
        self.exec(['mkdir', '-p', '/tmp/sbench-home', '/workspace/cache'], timeout=10)
        return self

    def watch(self):
        with (self.report_dir / 'resources.jsonl').open('w') as log:
            while not self.stop.is_set():
                try:
                    stats = call(['docker', 'stats', '--no-stream', '--format', '{{json .}}', self.name], timeout=10)
                    memory = next(int(s.split()[1]) for s in Path('/proc/meminfo').read_text().splitlines() if s.startswith('MemAvailable:'))
                    free = shutil.disk_usage(ROOT).free
                    elapsed = time.time() - self.started
                    log.write(json.dumps({'elapsed_s': elapsed, 'container': stats.stdout.strip(),
                                          'host_available_memory_kib': memory, 'host_disk_free_bytes': free}) + '\n')
                    log.flush()
                    if free < self.policy['host_disk_free_floor_gib'] * 2**30:
                        self.abort = 'host disk reserve exceeded'
                    elif memory * 1024 < self.policy['host_available_memory_floor_gib'] * 2**30:
                        self.abort = 'host memory reserve exceeded'
                    elif elapsed > self.policy['task_wall_timeout_seconds']:
                        self.abort = 'task wall deadline exceeded'
                except Exception as error:
                    self.abort = 'resource monitoring failed: ' + type(error).__name__
                if self.abort:
                    call(['docker', 'kill', self.name], timeout=15)
                    break
                self.stop.wait(2)

    def exec(self, argv, timeout=10800):
        started = time.time()
        if self.abort:
            return {'exit_code': 137, 'output': self.abort, 'guard_abort': self.abort}
        try:
            process = call(['docker', 'exec', '-w', '/workspace', self.name] + argv, timeout=timeout)
            return {'exit_code': process.returncode, 'output': (process.stdout + process.stderr)[-18000:],
                    'wall_seconds': time.time() - started, 'guard_abort': self.abort}
        except subprocess.TimeoutExpired:
            self.abort = 'command timeout'
            call(['docker', 'kill', self.name], timeout=15)
            return {'exit_code': 124, 'output': self.abort, 'wall_seconds': time.time() - started, 'guard_abort': self.abort}

    def put(self, source, target):
        source = Path(source)
        target = Path(target)
        if not str(target).startswith('/workspace/'):
            raise ValueError('uploads must stay in workspace')
        result = self.exec(['mkdir', '-p', str(target.parent)], timeout=10)
        if result['exit_code']:
            raise RuntimeError(result['output'])
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w') as archive:
            archive.add(source, arcname=target.name, filter=lambda item: None if '__pycache__' in item.name else item)
        if buffer.tell() > 16 * 2**20:
            raise ValueError('large assets must use read-only mounts')
        process = subprocess.run(['docker', 'exec', '-i', self.name, 'tar', '--no-same-owner', '-xf', '-', '-C', str(target.parent)],
                                 input=buffer.getvalue(), capture_output=True, timeout=30)
        if process.returncode:
            raise RuntimeError(process.stderr.decode()[-2000:])

    def collect(self, destination, evaluation_only=False):
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        packaged = self.exec(['test', '-f', '/workspace/output/install.tar.gz'], timeout=10)['exit_code'] == 0
        nested_packaged = not evaluation_only and not packaged and self.exec(['test','-f','/workspace/output/install/install.tar.gz'],timeout=10)['exit_code']==0
        argv = ['docker', 'exec', self.name, 'tar', '-cf', '-', '-C', '/workspace']
        temporary_environments = ['output/builder_venv', 'output/toolvenv', 'output/venv']
        argv += ['--exclude=' + path for path in temporary_environments]
        if evaluation_only:
            argv += ['--exclude=output/install']
        elif packaged:
            argv += ['--exclude=output/install']
        elif nested_packaged:
            argv += ['--exclude=output/install/install']
        argv += ['output']
        process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        with tarfile.open(fileobj=process.stdout, mode='r|') as archive:
            for member in archive:
                if shutil.disk_usage(ROOT).free < self.policy['host_disk_free_floor_gib'] * 2**30:
                    process.terminate()
                    raise RuntimeError('artifact collection stopped at host disk reserve')
                archive.extract(member, destination, filter='data')
        process.stdout.close()
        stderr = process.stderr.read().decode(errors='replace')
        code = process.wait(timeout=60)
        if code:
            return {'collected': False, 'error': stderr[-2000:]}
        (destination / 'artifact_storage.json').write_text(json.dumps({'install_storage': 'install.tar.gz' if packaged else 'expanded',
                                                                     'duplicate_install_tree_copied': not packaged,
                                                                     'excluded_temporary_build_environments': temporary_environments}, indent=2))
        return {'collected': True, 'install_archive_only': packaged}

    def close(self):
        self.stop.set()
        if hasattr(self, 'thread'):
            self.thread.join(timeout=15)
        if self.created:
            probe=self.exec(['python3','-c',"from pathlib import Path; import json; root=Path('/sys/fs/cgroup'); print(json.dumps({n:(root/n).read_text() for n in ['memory.events','memory.peak','memory.max','memory.swap.max','cpu.stat','cpu.max','cpuset.cpus.effective','pids.peak'] if (root/n).exists()}))"],timeout=15)
            (self.report_dir/'cgroup_final.json').write_text(json.dumps(probe,indent=2))
            result = call(['docker', 'inspect', self.name], timeout=15)
            (self.report_dir / 'final_state.json').write_text(result.stdout)
            call(['docker', 'rm', '-f', self.name], timeout=30)
            self.created = False
        if hasattr(self,'input_snapshot'):
            shutil.rmtree(self.input_snapshot)
            del self.input_snapshot
        if hasattr(self, 'lock') and not self.lock.closed:
            fcntl.flock(self.lock, fcntl.LOCK_UN)
            self.lock.close()
        if hasattr(self,'extra_lock') and not self.extra_lock.closed:
            fcntl.flock(self.extra_lock,fcntl.LOCK_UN)
            self.extra_lock.close()

    def __exit__(self, exc_type, exc, traceback):
        self.close()
