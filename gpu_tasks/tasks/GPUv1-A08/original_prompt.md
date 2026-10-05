# GPUv1-A08 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

将70B基础模型适配到政府长报告摘要，交付与明确基础权重对应的LoRA适配器，并为独立报告生成摘要。训练、保存、后续加载和实际长文解码均在sandbox内执行。

### 来源和工作范围

MLPerf Llama2-70B LoRA + SCROLLS GovReport; public-asset derivative

### 交付要求

- adapter/、base_model_manifest.json、tokenizer和prompt模板
- heldout_summaries.jsonl：report_id及真实预测
- training_coverage.json、公共资产预处理说明与评测报告

### 必须完成的工作

- 构造固定报告到摘要监督样本，明确长于8192 token的截断/packing与标签掩码规则
- 对q/k/v/o attention投影执行真实LoRA更新；合并投影到分离投影的映射须验证，训练一遍完整train
- 交付adapter和基础模型hash后重新加载，在保留报告上生成摘要并计算ROUGE/长度与覆盖信息

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

用同一个基础模型和新adapter处理另一批长报告，生成摘要和报告ID映射；允许同session中保留已加载权重等待后续请求。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
