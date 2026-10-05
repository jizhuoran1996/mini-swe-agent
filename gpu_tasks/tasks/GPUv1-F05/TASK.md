# GPUv1-F05：推进真实蛋白溶液体系并交付可恢复状态

input/initial.pdb、system.xml 和 positions_nm.npy 是来自实验 RCSB 1UBQ 的 ubiquitin 水溶液，Amber14/TIP3P-FB、PME、HBond constraints，来源和原子数见 manifest。OpenMM 8.6.1 与 CUDA12 插件已提供；如插件报告缺库，请报告具体错误，不能改 CPU 假装 GPU 执行。
入口 python solution/main.py run --input input --output output。在实际 CUDA 平台、mixed precision、DeviceIndex=0、DeterministicForces=true 上进行能量最小化（最多 100 次），以 seed=2026 初始化 300K 速度，随后 Verlet NVE dt=2 fs、constraints tolerance=1e-6 推进 200 steps，每 20 步记录全部原子 positions/velocities、time、potential/kinetic energy。交付 trajectory.npz、energies.json、完整 system.xml/initial.pdb、state.xml（positions/velocities/box/time）、checkpoint.chk（二进制真正 restart state）、run.json（实际 CUDA platform/properties/原子数/步数/积分器与单位）。必须同步完成后提交，不返回空轨迹。
支持 python solution/main.py resume --checkpoint output/checkpoint.chk --artifacts output --steps 50 --output output/continued，在输入目录不存在的新进程中恢复再推进 50 steps，仍用保存的原始 system 与 Verlet 配置，不再次最小化/随机初始化。独立检查原子全覆盖、时间 0.4ps→0.5ps、位置速度 finite、能量变化有限、真实 CUDA 力计算、state 与轨迹最后帧一致、checkpoint 重载后的连续物理推进。RMSD 只用于这段短轨迹的描述，不声称足以分析长期动力学。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
