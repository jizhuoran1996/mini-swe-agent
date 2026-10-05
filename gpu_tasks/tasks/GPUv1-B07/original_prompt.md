# GPUv1-B07 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

为 SemanticKITTI 的完整扫描训练点级语义分割器，对验证序列每个点生成与原始扫描顺序对应的标签文件，并交付按距离统计的语义覆盖报告。

### 来源和工作范围

Cylinder3D official config/semantickitti.yaml and train.sh; SemanticKITTI single-scan semantic segmentation; official semantic-kitti-api evaluator.

### 交付要求

- Cylinder3D checkpoint 与有效配置
- sequences/08/predictions/*.label
- 逐类与按距离 IoU 报告
- label 映射与批量预测入口

### 必须完成的工作

- 按官方 learning_map 训练，同时保留逆映射。
- 执行源训练配置声明的完整计划，保存最佳与最终 checkpoint。
- 对完整序列 08 推理，输出每个原始点的标签和距离分层报告。

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

从保存模型继续处理声明的未标注序列，生成结构正确的标签包；已处理扫描的标签和索引必须保持可追溯。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
