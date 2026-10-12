# GPUv1-B06 原生适配器

原始MMDetection3D CenterPoint voxel0075 / SECOND / SECFPN / circle NMS，8条mini_train、4条mini_val真实帧及完整历史LiDAR sweeps。原始模型8938262参数；CPU数据管线已完整读取8条输入。调试batch1、一轮训练加一轮续跑；CBGS与GT对象采样关闭。尚未GPU执行或独立评分。

原始Flash适配器由Codex明确修复；权重、数据及source revision以只读input/manifest.json、input_lock.json和source_lock.json为准。无网络容器中不下载或制造替代数据。

```bash
python solution/main.py doctor --input input
python solution/main.py run --input input --output output
python solution/main.py resume --input input --output output
```

使用gpu_suite/native_trial.py的隔离容器执行，评分仍需grade_task.py对应的独立评分器。尚待GPU的修复不计为验收通过。Python 3.10 native任务使用专用legacy-env；FCN3使用独立fcn3-env；已验收的B05/F08依赖锁定native_deps，F06使用只读原生二进制。环境锁见runtime/native_environment。
