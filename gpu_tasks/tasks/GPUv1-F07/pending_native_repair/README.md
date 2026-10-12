# GPUv1-F07 原生适配器

原始FCN3模型包、Earth2Studio 0.19和Makani，完整全球721×1440、72通道真实ARCO ERA5。两成员、两步、每步6小时，续跑另一步；保存全部预报通道、原始相关噪声状态及其专用CPU/CUDA Generator。五输出通道u10m/v10m/t2m/msl/tcwv；原始模型不预测降水。尚未GPU执行或独立评分。

原始Flash适配器由Codex明确修复；权重、数据及source revision以只读input/manifest.json、input_lock.json和source_lock.json为准。无网络容器中不下载或制造替代数据。

```bash
python solution/main.py doctor --input input
python solution/main.py run --input input --output output
python solution/main.py resume --input input --output output
```

使用gpu_suite/native_trial.py的隔离容器执行，评分仍需grade_task.py对应的独立评分器。尚待GPU的修复不计为验收通过。Python 3.10 native任务使用专用legacy-env；FCN3使用独立fcn3-env；已验收的B05/F08依赖锁定native_deps，F06使用只读原生二进制。环境锁见runtime/native_environment。
