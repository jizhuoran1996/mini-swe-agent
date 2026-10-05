"""Isolated, serialized GPU workspace with hard host-resource limits."""
import fcntl
import json
import io
import os
from pathlib import Path
import shutil
import subprocess
import threading
import tarfile
import time
import uuid

ROOT = Path(__file__).resolve().parent
POLICY = json.loads((ROOT / "runtime/policy.json").read_text())
BASE_PYTHON_ENV = Path(os.environ.get("SBENCH_PYTHON_ENV",str(ROOT/"runtime/python_env") if (ROOT/"runtime/python_env").is_dir() else "/home/zrji/.venv")).resolve()

def run_path(summary):
    path=Path(summary['run_directory'])
    return path if path.is_absolute() else ROOT/path


def call(args, **kw):
    return subprocess.run(args, text=True, capture_output=True, **kw)


class Sandbox:
    def __init__(self, task_id, inputs=None, models=None, artifacts=None, memory_gib=None, report_dir=None,gpu_enabled=True):
        self.task_id = task_id
        self.gpu_enabled=gpu_enabled
        self.inputs = Path(inputs).resolve() if inputs else None
        self.models = Path(models).resolve() if models else None
        self.artifacts = Path(artifacts).resolve() if artifacts else None
        self.memory_gib = memory_gib or POLICY["host_memory_gib"]
        self.name = "sbench-"+task_id.lower().replace("_", "-")+"-"+uuid.uuid4().hex[:8]
        self.report_dir = Path(report_dir or ROOT / "runs" / self.name)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.abort = None
        self.stop_event = threading.Event()
        self.created = False
        self.started = None
        self.lock = None

    def __enter__(self):
        self.lock = (ROOT / ("gpu.lock" if self.gpu_enabled else "cpu.lock")).open("a+")
        fcntl.flock(self.lock, fcntl.LOCK_EX)
        if shutil.disk_usage(ROOT).free < POLICY["host_disk_free_floor_gib"]*2**30:
            self.close()
            raise RuntimeError("host disk reserve is too low to admit a task")
        # External jobs do not use our flock. Wait for genuine device headroom
        # before starting a new solver, without touching other processes.
        admitted_at=time.time()
        with (self.report_dir/'admission.jsonl').open('w') as log:
            while True:
                if not self.gpu_enabled:break
                probe=call(['nvidia-smi','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],timeout=10)
                values=[v.strip() for v in probe.stdout.strip().split(',')]
                if probe.returncode or len(values)!=2:
                    self.close();raise RuntimeError('GPU admission probe failed')
                log.write(json.dumps({'wait_seconds':time.time()-admitted_at,'gpu_used_mib':int(values[0]),'gpu_utilization':int(values[1])})+'\n');log.flush()
                if int(values[0])<4096 and int(values[1])<30:break
                if time.time()-admitted_at>1800:
                    self.close();raise RuntimeError('GPU remains occupied by external work; admission deadline exceeded')
                self.stop_event.wait(2)
        self.admission_wait_seconds=time.time()-admitted_at
        args = ["docker", "run", "-d", "--name", self.name, "--label", "sbench.managed=true", "--label", "sbench.task="+self.task_id,
                "--network", "none", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--user", f"{os.getuid()}:{os.getgid()}", "--memory", f"{self.memory_gib}g", "--memory-swap", f"{self.memory_gib}g", "--cpus", str(POLICY["cpu_count"]),
                "--pids-limit", str(POLICY["pids_limit"]), "--shm-size", f"{POLICY['shared_memory_gib']}g", "--ulimit", f"fsize={POLICY['single_file_max_gib']*2**30}:{POLICY['single_file_max_gib']*2**30}",
                "--ulimit", "nofile=4096:4096", "--tmpfs", f"/workspace:rw,nosuid,nodev,size={POLICY['workspace_tmpfs_gib']}g,mode=1777",
                "--tmpfs", f"/tmp:rw,nosuid,nodev,size={POLICY['temporary_tmpfs_gib']}g,mode=1777",
                "--mount", f"type=bind,src={BASE_PYTHON_ENV},dst=/opt/task-python,readonly",
                "--mount", f"type=bind,src={ROOT/'pydeps'},dst=/opt/suite-deps,readonly",
                "--mount", f"type=bind,src={ROOT/'runtime/guard'},dst=/opt/guard,readonly",
                "--env", "PYTHONPATH=/opt/guard:/opt/suite-deps:/opt/task-python/lib/python3.12/site-packages",
                "--env", "SBENCH_GPU_GUARD=1", "--env", "HF_HOME=/tmp/hf", "--env", "TORCH_HOME=/tmp/torch", "--env", "XDG_CACHE_HOME=/tmp/cache", "--env", "MPLCONFIGDIR=/tmp/mpl",
                "--env", "HF_HUB_OFFLINE=1", "--env", "TRANSFORMERS_OFFLINE=1"]
        args += ['--ulimit','core=0:0']
        if (ROOT/'cuda128deps/torch').is_dir():
            args += ['--mount',f'type=bind,src={ROOT/"cuda128deps"},dst=/opt/cuda128-deps,readonly',
                     '--env','PYTHONPATH=/opt/guard:/opt/cuda128-deps:/opt/suite-deps:/opt/task-python/lib/python3.12/site-packages']
        if (ROOT/'compat_deps/huggingface_hub').is_dir():
            args += ['--mount',f'type=bind,src={ROOT/"compat_deps"},dst=/opt/compat-deps,readonly',
                     '--env','PYTHONPATH=/opt/guard:/opt/cuda128-deps:/opt/compat-deps:/opt/suite-deps:/opt/task-python/lib/python3.12/site-packages']
        if any(k in self.task_id.lower() for k in ['c09','c10']) and (ROOT/'qwen_tts_deps/transformers').is_dir():
            args += ['--mount',f'type=bind,src={ROOT/"qwen_tts_deps"},dst=/opt/qwen-tts-deps,readonly',
                     '--env','PYTHONPATH=/opt/guard:/opt/cuda128-deps:/opt/qwen-tts-deps:/opt/compat-deps:/opt/suite-deps:/opt/task-python/lib/python3.12/site-packages']
        if (ROOT/'cuda_compat/nvidia/cuda_nvrtc/lib').is_dir():
            args += ['--mount',f'type=bind,src={ROOT/"cuda_compat"},dst=/opt/cuda-compat,readonly',
                     '--env','LD_LIBRARY_PATH=/opt/cuda-compat/nvidia/cuda_nvrtc/lib:/opt/task-python/lib/python3.12/site-packages/nvidia/cuda_runtime/lib:/opt/task-python/lib/python3.12/site-packages/nvidia/cufft/lib:/opt/task-python/lib/python3.12/site-packages/nvidia/cublas/lib']
        if self.gpu_enabled:args += ['--gpus','device='+POLICY['gpu_device']]
        if self.inputs:
            args += ["--mount", f"type=bind,src={self.inputs},dst=/workspace/input,readonly"]
        if self.models:
            args += ["--mount", f"type=bind,src={self.models},dst=/models,readonly"]
        if self.artifacts:
            args += ["--mount", f"type=bind,src={self.artifacts},dst=/artifacts,readonly"]
        args += [POLICY["image"], "sleep", "infinity"]
        p = call(args, timeout=30)
        if p.returncode:
            self.close()
            raise RuntimeError(p.stderr[-4000:])
        self.created = True
        self.started = time.time()
        inspect = call(["docker", "inspect", self.name], timeout=10)
        (self.report_dir / "container.json").write_text(inspect.stdout)
        self.thread = threading.Thread(target=self.watch, daemon=True)
        self.thread.start()
        return self

    def watch(self):
        with (self.report_dir / "resources.jsonl").open("w") as f:
            while not self.stop_event.is_set():
                try:
                    p = call(["nvidia-smi", "--query-gpu=uuid,memory.used,utilization.gpu,temperature.gpu,power.draw", "--format=csv,noheader,nounits"], timeout=5)
                    fields = [s.strip() for s in p.stdout.strip().split(",")]
                    available_kib = next(int(s.split()[1]) for s in Path("/proc/meminfo").read_text().splitlines() if s.startswith("MemAvailable:"))
                    stats = call(["docker", "stats", "--no-stream", "--format", "{{json .}}", self.name], timeout=8)
                    f.write(json.dumps({"t": time.time()-self.started, "gpu": p.stdout.strip(), "container_stats": stats.stdout.strip(), "host_available_kib": available_kib})+"\n")
                    f.flush()
                    if self.gpu_enabled and len(fields)>=4 and int(fields[1]) > POLICY["gpu_abort_used_mib"]:
                        self.abort = "GPU memory headroom exceeded"
                    elif self.gpu_enabled and len(fields)>=4 and int(fields[3]) >= POLICY["gpu_abort_temperature_c"]:
                        self.abort = "GPU temperature guard exceeded"
                    elif available_kib*1024 < POLICY["host_available_memory_floor_gib"]*2**30:
                        self.abort = "host memory reserve exceeded"
                    elif time.time()-self.started > POLICY["task_wall_timeout_seconds"]:
                        self.abort = "task wall deadline exceeded"
                    elif shutil.disk_usage(ROOT).free < POLICY["host_disk_free_floor_gib"]*2**30:
                        self.abort = "host disk reserve exceeded"
                    if self.abort:
                        call(["docker", "kill", self.name], timeout=10)
                        break
                except Exception as e:
                    f.write(json.dumps({"watchdog_error": type(e).__name__})+"\n")
                    f.flush()
                    self.abort = "resource watchdog failed"
                    call(["docker", "kill", self.name], timeout=10)
                    break
                self.stop_event.wait(POLICY["watchdog_interval_seconds"])

    def exec(self, command, timeout=None):
        if self.abort:
            return {"exit_code": 137, "output": self.abort, "guard_abort": self.abort, "seconds": 0}
        t = time.time()
        limit = timeout or POLICY["command_timeout_seconds"]
        try:
            p = call(["docker", "exec", "--workdir", "/workspace", self.name, "bash", "-c", command], timeout=limit)
            return {"exit_code": p.returncode, "output": (p.stdout+p.stderr)[-24000:], "seconds": time.time()-t, "guard_abort": self.abort}
        except subprocess.TimeoutExpired:
            self.abort = "command timeout"
            call(["docker", "kill", self.name], timeout=10)
            return {"exit_code": 124, "output": "command exceeded deadline; container terminated", "seconds": time.time()-t, "guard_abort": self.abort}

    def put(self, source, target):
        source = Path(source)
        target = Path(target)
        if not str(target).startswith("/workspace/"):
            raise ValueError("uploads must stay in the writable workspace")
        p = call(["docker", "exec", self.name, "mkdir", "-p", str(target.parent)], timeout=10)
        if p.returncode:
            raise RuntimeError(p.stderr[-3000:])
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as archive:
            archive.add(source, arcname=target.name)
        if buf.tell() > 32*2**20:
            raise ValueError("large assets must be mounted read-only rather than copied to the workspace")
        p = subprocess.run(["docker", "exec", "-i", self.name, "tar", "--no-same-owner", "-xf", "-", "-C", str(target.parent)], input=buf.getvalue(), capture_output=True, timeout=30)
        if p.returncode:
            raise RuntimeError(p.stderr.decode()[-3000:])

    def collect(self, destination, names=("solution", "output")):
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        for name in names:
            if name not in ("solution", "output", "evaluation"):
                raise ValueError("only declared artifact directories may be exported")
            # Docker's archive API does not export this container's tmpfs mounts.
            # Stream from the live mount namespace, then use safe tar extraction.
            archive_path = destination / (name+".export.tar")
            with archive_path.open("wb") as out:
                p = subprocess.run(["docker", "exec", self.name, "tar", "-cf", "-", "-C", "/workspace", name], stdout=out, stderr=subprocess.PIPE, timeout=180)
            if p.returncode:
                (destination / (name+".missing.txt")).write_text(p.stderr.decode()[-4000:])
            else:
                with tarfile.open(archive_path) as archive:
                    excluded=[]
                    def artifact_filter(member,path):
                        try:return tarfile.data_filter(member,path)
                        except (tarfile.AbsoluteLinkError,tarfile.LinkOutsideDestinationError) as error:
                            excluded.append({'name':member.name,'target':member.linkname,'reason':type(error).__name__})
                            return None
                    archive.extractall(destination, filter=artifact_filter)
                    if excluded:(destination/(name+'.excluded_links.json')).write_text(json.dumps(excluded,indent=2))
            archive_path.unlink(missing_ok=True)

    def close(self):
        self.stop_event.set()
        if hasattr(self, "thread"):
            self.thread.join(timeout=10)
        if self.created:
            (self.report_dir / "final_state.json").write_text(call(["docker", "inspect", "--format", "{{json .State}}", self.name], timeout=10).stdout)
            call(["docker", "rm", "-f", self.name], timeout=20)
            self.created = False
        if self.lock:
            fcntl.flock(self.lock, fcntl.LOCK_UN)
            self.lock.close()
            self.lock = None

    def __exit__(self, *_):
        self.close()
