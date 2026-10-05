"""Conservative allocator defaults for the single GPU testing profile."""
import os
import ctypes
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
if os.environ.get("SBENCH_GPU_GUARD") == "1":
    compat_nvrtc='/opt/cuda-compat/nvidia/cuda_nvrtc/lib/libnvrtc.so.12'
    if os.path.isfile(compat_nvrtc):
        ctypes.CDLL(compat_nvrtc,mode=ctypes.RTLD_GLOBAL)
    import torch
    if torch.cuda.is_available():
        torch.cuda.set_per_process_memory_fraction(0.75, 0)
