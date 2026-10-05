# 去重、来源与计数

本包包含60个具体候选任务设计。任务实例、工作流家族、模型、数据集、规模、轨迹和实验场景分别计数，不声称有60种独立GPU算法或60个全新的上游benchmark。

每题有稳定ID、workflow_family、canonical_goal_key、source_task_or_workload与来源绑定。不同真实数据问题或不同交付目标可以成为同一家族的任务实例；只改变模型尺寸、batch、精度、种子、并发、设备数、checkpoint策略、CPU/GPU实现或输入规模，不自动形成新任务。

## 需要共同审核的关系

- A的训练/适配与D的实际推理可以共享数据来源；训练产物和推理结果是不同目标，但必须标注共享语料/模型，不能当作完全独立来源。
- B的视觉训练/结果交付与C的生成/编辑可能共享COCO等输入；任务语义不同，输入lineage仍相关。
- E的GPU ANN、表格和图任务与之前Memory/I/O包可能具有同一目标。GPU实现属于执行变体；合并总语料时按原始目标与数据审核canonical ID，不能把CPU换GPU直接累加成新问题。
- F的科学模型预测、训练和实际物理模拟有不同交付；同一数据集的重采样、时间长度和系统规模仍是规模实例。
- 同一prompt、同一视频、同一向量反复计算只构成重复运行，不提供新输入多样性。

候选目录给出的semantic distinction便于审核，但最终独立任务数量在完成原数据和运行绑定后确定。workload mixer同时报告选中轨迹、独立canonical task、workflow family、输入lineage和重复比例。

## 版本演进

升级源模型/依赖、改变数据split或任务语义时创建task revision并保留来源记录。只改后端/调度策略则更新scenario manifest。一个任务可被同时标为GPU计算、显存驻留、host-memory或I/O混合，资源类别不用互斥。
