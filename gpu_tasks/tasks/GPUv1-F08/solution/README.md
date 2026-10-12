# GPUv1-F08 原生适配器

原始CorrDiff regression和diffusion checkpoint，16通道448×448真实条件场；5个不同seed成员加续跑第6个，另一个真实时间点和seed11新请求。官方native generator/sampler函数、独立GPU六成员复算和新请求通过；正式规模未执行。

原始Flash适配器由Codex明确修复；权重、数据及source revision以只读input/manifest.json、input_lock.json和source_lock.json为准。无网络容器中不下载或制造替代数据。

```bash
python solution/main.py doctor --input input
python solution/main.py run --input input --output output
python solution/main.py resume --input input --output output
```

使用gpu_suite/native_trial.py的隔离容器执行，评分仍需grade_task.py对应的独立评分器。尚待GPU的修复不计为验收通过。Python 3.10 native任务使用专用legacy-env；FCN3使用独立fcn3-env；已验收的B05/F08依赖锁定native_deps，F06使用只读原生二进制。环境锁见runtime/native_environment。
