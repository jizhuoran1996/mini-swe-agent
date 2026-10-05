# GPUv1-E10 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

根据已有论文特征和引用关系训练缺失参考文献推荐器，提交可重载模型和每个保留查询的候选排序，支持后续论文查询。

### 来源和工作范围

OGBL-Citation2 full 2,927,963 nodes / 30,561,187 edges; official sampler.py GraphSAGE [15,10,5], three layers, 256 hidden channels

### 交付要求

- citation_model.pt 与 predictor_state.pt
- query_rankings.parquet
- split_and_sampling_manifest.json
- recommend.py

### 必须完成的工作

- 建立只含训练边的采样图
- 在GPU执行邻居采样批次的GraphSAGE和link predictor训练
- 用官方Evaluator计算MRR并保存逐query排序和checkpoint

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

用保留模型处理另一组固定论文和候选引用，确保不将新查询答案加入训练图。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
