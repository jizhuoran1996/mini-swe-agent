# GPUv1-E09 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

在论文、作者等多类型关系构成的学术图上训练论文主题分类器，交付可恢复模型和按原始paper ID组织的预测，让后续查询能继续使用模型与图特征。

### 来源和工作范围

IGBH-large real heterogeneous graph/features; MLPerf retired_benchmarks/rgat/train_rgnn_multi_gpu.py model=rgat, 3 layers, hidden=512, 4 heads, fan_out=15,10,5

### 交付要求

- rgat_checkpoint.pt
- paper_predictions.parquet
- graph_feature_manifest.json
- inference.py

### 必须完成的工作

- 核对各节点类型、关系和特征映射，完成声明的图布局/特征精度准备
- 按GLT异构采样/多GPU训练路径执行完整训练
- 保存模型/优化器/采样状态，导出验证ID预测并重载验证

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

重载提交模型，对已声明的一组未查询论文执行主题预测，并保留实际图特征worker。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
