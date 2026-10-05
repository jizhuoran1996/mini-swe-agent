All16461 real native actions/linking completed; only upstream wheel packaging failed because genuine patchelf executable was missing. Trusted task-specific bootstrap now adds real Ubuntu patchelf, no prebuilt TF target. Add patchelf to doctor/readiness and actual --version bootstrap validation before building. No RPATH stubs/source edits/fake wheels.
Policy reserves8 real CPUs(indices0–5+23–24), still32GiB/noSwap/24GiBworkspace. Manifestbuild_jobs/build_job_limit=8; trusted Session now accepts8 only for that manifest. Remove the hard clamp4; honor min(user_jobs,manifestjoblimit) and bind Bazel --jobs. Delivery run command should --jobs8. Retain LOCAL_RAM_RESOURCES16000, clang18 compatibility options, entire target/options/optimizations/features/inputs unchanged. OfficialTEST_JOBS remains2. Full cold build mandatory; retain original softmax/SavedModel official tests and new-env save/reload consumers, all numerical tolerances. No feature/test reduction, target prebuilts/source modifications/mocks. Return full files.

Actual failure:
ir/dtensor_collective_type_lowering.cc; 3s local ... (4 actions, 3 running)
[16,318 / 16,461] Compiling tensorflow/dtensor/mlir/dtensor_collective_type_lowering.cc; 5s local ... (4 actions running)
[16,319 / 16,461] Compiling tensorflow/dtensor/mlir/lower_send_recv.cc; 6s local ... (4 actions, 3 running)
[16,320 / 16,461] Compiling tensorflow/compiler/jit/xla_compile_on_demand_op.cc; 8s local ... (4 actions running)
[16,321 / 16,461] Compiling tensorflow/compiler/jit/pjrt_compile_util.cc; 7s local ... (4 actions running)
[16,322 / 16,461] Compiling tensorflow/dtensor/mlir/dtensor_layout_to_xla_sharding_op.cc; 4s local ... (4 actions running)
[16,323 / 16,461] Compiling tensorflow/dtensor/mlir/layout_propagation_v2.cc; 6s local ... (4 actions, 3 running)
[16,323 / 16,461] Compiling tensorflow/dtensor/mlir/layout_propagation_v2.cc; 8s local ... (4 actions running)
[16,325 / 16,461] Compiling tensorflow/compiler/jit/kernels/xla_ops.cc; 6s local ... (4 actions running)
[16,326 / 16,461] Compiling tensorflow/dtensor/mlir/dtensor_mixed_precision_reduce.cc; 6s local ... (4 actions, 3 running)
[16,326 / 16,461] Compiling tensorflow/dtensor/mlir/dtensor_mixed_precision_reduce.cc; 7s local ... (4 actions running)
[16,329 / 16,461] Compiling tensorflow/compiler/jit/xla_device.cc; 6s local ... (4 actions, 3 running)
[16,330 / 16,461] Compiling tensorflow/dtensor/mlir/dtensor_mlir_passes.cc; 1s local ... (4 actions, 3 running)
[16,330 / 16,461] Compiling tensorflow/dtensor/mlir/dtensor_mlir_passes.cc; 3s local ... (4 actions running)
[16,331 / 16,461] Compiling tensorflow/dtensor/mlir/dtensor_mlir_passes.cc; 7s local ... (4 actions, 3 running)
[16,334 / 16,461] Compiling tensorflow/core/distributed_runtime/eager/eager_service_impl.cc; 1s local ... (4 actions running)
[16,335 / 16,461] Compiling tensorflow/core/distributed_runtime/eager/eager_service_impl.cc; 2s local ... (4 actions running)
[16,336 / 16,461] Compiling tensorflow/dtensor/mlir/dtensor_multi_device_expansion.cc; 3s local ... (4 actions, 3 running)
[16,336 / 16,461] Compiling tensorflow/dtensor/mlir/dtensor_multi_device_expansion.cc; 4s local ... (4 actions running)
[16,337 / 16,461] Compiling tensorflow/dtensor/mlir/dtensor_multi_device_expansion.cc; 7s local ... (4 actions, 3 running)
[16,339 / 16,461] Compiling tensorflow/dtensor/mlir/dtensor_set_hlo_sharding.cc; 6s local ... (4 actions, 3 running)
[16,340 / 16,461] Compiling tensorflow/compiler/jit/xla_platform_info.cc; 2s local ... (4 actions running)
[16,341 / 16,461] Compiling tensorflow/compiler/jit/xla_platform_info.cc; 5s local ... (4 actions, 3 running)
[16,341 / 16,461] Compiling tensorflow/compiler/jit/xla_platform_info.cc; 6s local ... (4 actions running)
[16,342 / 16,461] Compiling tensorflow/compiler/jit/xla_platform_info.cc; 7s local ... (4 actions, 3 running)
[16,345 / 16,461] Compiling tensorflow/compiler/jit/xla_cpu_device.cc; 1s local ... (4 actions running)
[16,346 / 16,461] Compiling tensorflow/compiler/jit/xla_cpu_device.cc; 7s local ... (4 actions, 3 running)
[16,348 / 16,461] Compiling tensorflow/compiler/jit/get_compiler_ir.cc; 8s local ... (4 actions, 3 running)
[16,350 / 16,461] Compiling tensorflow/compiler/tf2xla/mlir_tf2xla.cc; 2s local ... (4 actions, 3 running)
[16,350 / 16,461] Compiling tensorflow/compiler/tf2xla/mlir_tf2xla.cc; 3s local ... (4 actions running)
[16,352 / 16,461] Compiling tensorflow/compiler/tf2xla/mlir_tf2xla.cc; 5s local ... (4 actions, 3 running)
[16,355 / 16,461] Compiling tensorflow/c/eager/c_api.cc; 2s local ... (4 actions, 3 running)
[16,355 / 16,461] Compiling tensorflow/c/eager/c_api.cc; 3s local ... (4 actions running)
[16,357 / 16,461] Compiling tensorflow/compiler/aot/compile.cc; 2s local ... (4 actions, 3 running)
[16,358 / 16,461] Compiling tensorflow/compiler/aot/compile.cc; 4s local ... (4 actions, 3 running)
[16,359 / 16,461] Compiling tensorflow/compiler/aot/compile.cc; 5s local ... (4 actions running)
[16,361 / 16,461] Compiling tensorflow/compiler/mlir/python/mlir.cc; 6s local ... (4 actions running)
[16,362 / 16,461] Compiling tensorflow/compiler/mlir/python/mlir.cc; 8s local ... (4 actions running)
[16,363 / 16,461] Compiling tensorflow/compiler/mlir/python/mlir.cc; 11s local ... (4 actions, 3 running)
[16,364 / 16,461] Compiling tensorflow/compiler/mlir/python/mlir.cc; 12s local ... (4 actions running)
[16,365 / 16,461] Compiling tensorflow/compiler/mlir/python/mlir.cc; 14s local ... (4 actions running)
[16,366 / 16,461] Compiling tensorflow/compiler/mlir/python/mlir.cc; 16s local ... (4 actions running)
[16,370 / 16,461] Compiling tensorflow/c/eager/dlpack.cc; 1s local ... (4 actions, 3 running)
[16,371 / 16,461] Compiling tensorflow/c/eager/dlpack.cc; 2s local ... (4 actions, 3 running)
[16,374 / 16,461] Compiling tensorflow/dtensor/cc/small_constant_optimization.cc; 1s local ... (4 actions running)
[16,376 / 16,461] Compiling tensorflow/compiler/mlir/tensorflow/c/c_api_unified_experimental_mlir.cc; 1s local ... (4 actions, 3 running)
[16,378 / 16,461] Compiling tensorflow/compiler/mlir/tensorflow/c/c_api_unified_experimental_mlir.cc; 3s local ... (4 actions, 3 running)
[16,378 / 16,461] Compiling tensorflow/compiler/mlir/tensorflow/c/c_api_unified_experimental_mlir.cc; 4s local ... (4 actions running)
[16,380 / 16,461] Compiling tensorflow/compiler/mlir/tensorflow/c/c_api_unified_experimental_mlir.cc; 6s local ... (4 actions, 3 running)
[16,382 / 16,461] Compiling tensorflow/compiler/mlir/tensorflow/c/c_api_unified_experimental_mlir.cc; 7s local ... (4 actions, 3 running)
[16,383 / 16,461] Compiling tensorflow/compiler/mlir/tensorflow/c/c_api_unified_experimental_mlir.cc; 8s local ... (4 actions running)
[16,385 / 16,461] Compiling tensorflow/python/eager/pywrap_tensor.cc; 2s local ... (4 actions, 3 running)
[16,387 / 16,461] Compiling tensorflow/python/eager/pywrap_tensor.cc; 3s local ... (4 actions, 3 running)
[16,389 / 16,461] Compiling tensorflow/python/eager/pywrap_tensor.cc; 5s local ... (4 actions, 3 running)
[16,391 / 16,461] Compiling tensorflow/dtensor/cc/dtensor_device.cc; 6s local ... (4 actions running)
[16,392 / 16,461] Compiling tensorflow/dtensor/cc/dtensor_device.cc; 7s local ... (4 actions, 3 running)
[16,395 / 16,461] Compiling tensorflow/dtensor/cc/dtensor_device.cc; 9s local ... (2 actions running)
[16,396 / 16,461] Compiling tensorflow/python/eager/pywrap_tfe_src.cc; 3s local ... (2 actions, 1 running)
[16,396 / 16,461] Compiling tensorflow/python/eager/pywrap_tfe_src.cc; 4s local ... (2 actions running)
[16,397 / 16,461] Linking tensorflow/libtensorflow_cc.so.2.18.0; 3s local
[16,398 / 16,461] [Prepa] action 'SolibSymlink _solib_k8/_Utensorflow/libtensorflow_cc.so.2.18.0'
[16,442 / 16,461] Linking tensorflow/python/profiler/internal/_pywrap_profiler.so; 0s local ... (4 actions running)
[16,460 / 16,461] Action tensorflow/tools/pip_package/wheel_house; 1s local
ERROR: /workspace/src/tensorflow/tools/pip_package/BUILD:266:9: Action tensorflow/tools/pip_package/wheel_house failed: (Exit 1): build_pip_package_py failed: error executing command (from target //tensorflow/tools/pip_package:wheel) bazel-out/k8-opt-exec-50AE0418/bin/tensorflow/tools/pip_package/build_pip_package_py @bazel-out/k8-opt/bin/tensorflow/tools/pip_package/wheel_house-0.params
Traceback (most recent call last):
  File "/workspace/cache/bazel_output/execroot/org_tensorflow/bazel-out/k8-opt-exec-50AE0418/bin/tensorflow/tools/pip_package/build_pip_package_py.runfiles/org_tensorflow/tensorflow/tools/pip_package/build_pip_package.py", line 391, in <module>
    prepare_wheel_srcs(args.headers, args.srcs, args.xla_aot,
  File "/workspace/cache/bazel_output/execroot/org_tensorflow/bazel-out/k8-opt-exec-50AE0418/bin/tensorflow/tools/pip_package/build_pip_package_py.runfiles/org_tensorflow/tensorflow/tools/pip_package/build_pip_package.py", line 242, in prepare_wheel_srcs
    patch_so(srcs_dir)
  File "/workspace/cache/bazel_output/execroot/org_tensorflow/bazel-out/k8-opt-exec-50AE0418/bin/tensorflow/tools/pip_package/build_pip_package_py.runfiles/org_tensorflow/tensorflow/tools/pip_package/build_pip_package.py", line 287, in patch_so
    rpath = subprocess.check_output(
            ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/workspace/cache/bazel_output/external/python_x86_64-unknown-linux-gnu/lib/python3.12/subprocess.py", line 466, in check_output
    return run(*popenargs, stdout=PIPE, timeout=timeout, check=True,
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/workspace/cache/bazel_output/external/python_x86_64-unknown-linux-gnu/lib/python3.12/subprocess.py", line 548, in run
    with Popen(*popenargs, **kwargs) as process:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/workspace/cache/bazel_output/external/python_x86_64-unknown-linux-gnu/lib/python3.12/subprocess.py", line 1026, in __init__
    self._execute_child(args, executable, preexec_fn, close_fds,
  File "/workspace/cache/bazel_output/external/python_x86_64-unknown-linux-gnu/lib/python3.12/subprocess.py", line 1955, in _execute_child
    raise child_exception_type(errno_num, err_msg, err_filename)
FileNotFoundError: [Errno 2] No such file or directory: 'patchelf'
Target //tensorflow/tools/pip_package:wheel failed to build
Use --verbose_failures to see the command lines of failed build steps.
[16,461 / 16,461] checking cached actions
INFO: Elapsed time: 7542.419s, Critical Path: 110.99s
INFO: 16461 processes: 1255 internal, 15206 local.
FAILED: Build did NOT complete successfully

