# GPUv1-B05 原生适配器

MLPerf KiTS19原始TorchScript 3D U-Net，case00000全体积、50个128³ Gaussian加权窗口，恢复原始体素网格与仿射。GPU推理和独立重新加载模型复算通过；kidney Dice 0.967813，tumor Dice 0.836271。另一原始病例的追加GPU请求尚待执行。

原始Flash适配器由Codex明确修复；权重、数据及source revision以只读input/manifest.json、input_lock.json和source_lock.json为准。无网络容器中不下载或制造替代数据。

```bash
python solution/main.py doctor --input input
python solution/main.py run --input input --output output
python solution/main.py resume --input input --output output
```

使用gpu_suite/native_trial.py的隔离容器执行，评分仍需grade_task.py对应的独立评分器。尚待GPU的修复不计为验收通过。Python 3.10 native任务使用专用legacy-env；FCN3使用独立fcn3-env；已验收的B05/F08依赖锁定native_deps，F06使用只读原生二进制。环境锁见runtime/native_environment。
