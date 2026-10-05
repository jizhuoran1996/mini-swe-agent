# GPUv1-F10：训练三维物理代理并交付多步预测

input/train_fields.npy 是 The Well turbulent radiative layer 3D 的真实 train trajectory 前 8 个时刻，shape=(8,5,32,32,64)，场顺序 density/pressure/vx/vy/vz、空间顺序 x/y/z。这是完整物理域的 stride4 下采样，不是随机体素。validation_initial.npy 是不同官方 valid trajectory 的初始场，仅给初始，不给未来 3 帧；坐标/time/边界条件见输入元数据。
实现 CUDA 3D FNO，至少包含真正的 torch.fft.rfftn/irfftn 与可训练 Fourier 模式权重（不能只做 Conv3D 冒充 FNO）。按 train 数据统计归一化，预测下一时刻场，至少 5 次优化器更新，固定 seed。允许 residual forecasting，记录 width/modes/normalization。入口 python solution/main.py train --input input --output output；输出 checkpoint.pt（权重、配置、optimizer/step/训练统计、RNG）、rollout.npy（仅 valid 初始场自回归推进 3 steps，shape=(3,5,32,32,64)）、state.npz（推进到最后的完整 5 场与 time）、run.json（train loss、坐标和 source绑定、同步耗时）。支持 python solution/main.py forecast --checkpoint output/checkpoint.pt --initial input/validation_initial.npy --steps 3 --output output/reloaded.npy；另支持 --initial output/state.npz 继续 2 步。独立检查真实 FFT forward/backward、checkpoint 参数更新、全部 3D 场与步数、fresh reload 预测一致、future rollout 只依赖 initial/preceding predicted state；未来误差与 persistence baseline 单独报告，debug 不声称完整源 FNO 质量通过。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
