# GPUv1-F04 原生适配器

原始EquiformerV2 153M All+MD权重、原始OCP calculator；官方OC20四个IS2RE验证分区内按SHA256(sid)取前2，共8个真实初始体系。五步LBFGS加五步恢复，原始ASE restart保存优化器历史，固定原始fixed原子。尚未GPU执行或独立评分。

原始Flash适配器由Codex明确修复；权重、数据及source revision以只读input/manifest.json、input_lock.json和source_lock.json为准。无网络容器中不下载或制造替代数据。

```bash
python solution/main.py doctor --input input
python solution/main.py run --input input --output output
python solution/main.py resume --input input --output output
```

使用gpu_suite/native_trial.py的隔离容器执行，评分仍需grade_task.py对应的独立评分器。尚待GPU的修复不计为验收通过。Python 3.10 native任务使用专用legacy-env；FCN3使用独立fcn3-env；已验收的B05/F08依赖锁定native_deps，F06使用只读原生二进制。环境锁见runtime/native_environment。
