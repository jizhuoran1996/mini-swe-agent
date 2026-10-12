# GPUv1-B07 原生适配器

原始Cylinder3D不对称稀疏网络，55853366参数，480×360×32圆柱网格；00训练4个完整扫描，08验证2个完整扫描，01新请求1个扫描。原始代码作spconv2特征API兼容和NumPy类型修复，保留网络、体素化和CE+Lovasz损失，原始训练循环补优化器/RNG/epoch持久化。尚未GPU执行或独立评分。

原始Flash适配器由Codex明确修复；权重、数据及source revision以只读input/manifest.json、input_lock.json和source_lock.json为准。无网络容器中不下载或制造替代数据。

```bash
python solution/main.py doctor --input input
python solution/main.py run --input input --output output
python solution/main.py resume --input input --output output
```

使用gpu_suite/native_trial.py的隔离容器执行，评分仍需grade_task.py对应的独立评分器。尚待GPU的修复不计为验收通过。Python 3.10 native任务使用专用legacy-env；FCN3使用独立fcn3-env；已验收的B05/F08依赖锁定native_deps，F06使用只读原生二进制。环境锁见runtime/native_environment。
