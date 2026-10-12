# GPUv1-A05 原生适配器

fairseq s2t_transformer_s，200条真实CoVoST2训练音频、20条测试音频及2条新测试音频。原生80维滤波器组特征和10000词SentencePiece；原始英语ASR encoder初始化。调试50次更新+5次续跑，warmup20、冻结0；正式30000次更新及1000次冻结未执行。原始trainer补充真实Python/NumPy/Torch/CUDA RNG保存恢复。

原始Flash适配器由Codex明确修复；权重、数据及source revision以只读input/manifest.json、input_lock.json和source_lock.json为准。无网络容器中不下载或制造替代数据。

```bash
python solution/main.py doctor --input input
python solution/main.py run --input input --output output
python solution/main.py resume --input input --output output
```

使用gpu_suite/native_trial.py的隔离容器执行，评分仍需grade_task.py对应的独立评分器。尚待GPU的修复不计为验收通过。Python 3.10 native任务使用专用legacy-env；FCN3使用独立fcn3-env；已验收的B05/F08依赖锁定native_deps，F06使用只读原生二进制。环境锁见runtime/native_environment。
