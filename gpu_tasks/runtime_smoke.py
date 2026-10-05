import json
from pathlib import Path
from container import ROOT, Sandbox

report_dir = ROOT / "runs/runtime_smoke"
r = {}
with Sandbox("runtime-smoke", inputs=ROOT/"tasks/GPUv1-E05/input", report_dir=report_dir) as s:
    r["limits"] = s.exec("cat /sys/fs/cgroup/memory.max; cat /sys/fs/cgroup/memory.swap.max; cat /sys/fs/cgroup/pids.max; cat /sys/fs/cgroup/cpu.max; df -B1 /workspace /tmp; test ! -e /var/run/docker.sock; test ! -e /home/zrji/sbench/pilot_gpu/oracle")
    r["gpu"] = s.exec("python -c 'import torch; x=torch.ones((64,64),device=\"cuda\"); print(torch.cuda.get_device_name(),float((x@x).sum()),torch.cuda.get_per_process_memory_fraction())'")
    r["readonly"] = s.exec("python -c 'from pathlib import Path; Path(\"input/not_allowed\").write_text(\"bad\")'")
    r["libraries"] = s.exec("python - <<'PY'\nimport importlib\nfor n in ['transformers','datasets','diffusers','peft','accelerate','scipy','pandas','h5py','xgboost','openmm','cv2','torchvision','torchaudio']:\n try:m=importlib.import_module(n);print(n,'OK',getattr(m,'__version__',''))\n except Exception as e:print(n,type(e).__name__,str(e)[:250])\nPY")
    (report_dir/"checks.json").write_text(json.dumps(r,indent=2)+"\n")
    print(json.dumps(r,indent=2),flush=True)
    task=ROOT/'tasks/GPUv1-E05';latest=json.loads((task/'latest_run.json').read_text());s.put(Path(latest['run_directory'])/'workspace/solution', '/workspace/solution')
    r["pilot_build"] = s.exec("python solution/main.py build --input input --output output")
    r["pilot_query"] = s.exec("python solution/main.py query --index output/index --queries input/queries.npy --output output/reloaded")
    s.collect(report_dir/"workspace")
    print(json.dumps({k:v for k,v in r.items() if k.startswith('pilot')},indent=2),flush=True)
(report_dir/"checks.json").write_text(json.dumps(r,indent=2)+"\n")
assert all(r[k]["exit_code"]==0 for k in ("limits","gpu","pilot_build","pilot_query"))
assert r["readonly"]["exit_code"]!=0
print("CONTAINER SMOKE PASSED")
