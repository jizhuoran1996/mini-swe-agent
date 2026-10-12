# GPUv1-F03 原生适配器

原始OpenFold finetuning_ptm_1权重和model_1_ptm预设，真实CASP14 T1050/T1052/T1053/T1061全长序列及MMseqs2真实MSA。原始长序列offload路径；本次debug不准入模板命中，不能当作历史模板条件质量评测。TensorRT关闭时改为延迟导入其可选库。尚未GPU执行或独立评分。

原始Flash适配器由Codex明确修复；权重、数据及source revision以只读input/manifest.json、input_lock.json和source_lock.json为准。无网络容器中不下载或制造替代数据。

```bash
python solution/main.py doctor --input input
python solution/main.py run --input input --output output
python solution/main.py resume --input input --output output
```

使用gpu_suite/native_trial.py的隔离容器执行，评分仍需grade_task.py对应的独立评分器。尚待GPU的修复不计为验收通过。Python 3.10 native任务使用专用legacy-env；FCN3使用独立fcn3-env；已验收的B05/F08依赖锁定native_deps，F06使用只读原生二进制。环境锁见runtime/native_environment。
