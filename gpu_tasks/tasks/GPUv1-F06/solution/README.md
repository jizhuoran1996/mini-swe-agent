# GPUv1-F06 原生适配器

原始LAMMPS Ta SNAP / Kokkos CUDA，sm120原生编译。128个真实Ta原子，100步积分加50步restart续跑；完整GPU连续150步独立运行比对和三项负控制通过。RDF、势能、速度和周期边界坐标独立复算，正式大规模未执行。

原始Flash适配器由Codex明确修复；权重、数据及source revision以只读input/manifest.json、input_lock.json和source_lock.json为准。无网络容器中不下载或制造替代数据。

```bash
python solution/main.py doctor --input input
python solution/main.py run --input input --output output
python solution/main.py resume --input input --output output
```

使用gpu_suite/native_trial.py的隔离容器执行，评分仍需grade_task.py对应的独立评分器。尚待GPU的修复不计为验收通过。Python 3.10 native任务使用专用legacy-env；FCN3使用独立fcn3-env；已验收的B05/F08依赖锁定native_deps，F06使用只读原生二进制。环境锁见runtime/native_environment。
