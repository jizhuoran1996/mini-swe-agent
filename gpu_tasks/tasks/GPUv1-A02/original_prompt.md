# GPUv1-A02 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

给定已训练的 SFT 模型和偏好样本，交付能够正确加载的偏好对齐模型，并提供独立候选回复对上的评分审计及实际对话回复。

### 来源和工作范围

Alignment Handbook Zephyr DPO + corrected HuggingFaceH4/ultrafeedback_binarized train_prefs

### 交付要求

- aligned_model/ 和 tokenizer/template
- pair_scores.parquet：prompt_id、chosen/rejected 的可复算 log probabilities
- validation_report.json 与训练覆盖清单

### 必须完成的工作

- 核对 chosen/rejected 角色、相同 prompt 和模板，排除格式损坏记录并保留清单
- 进行真实 DPO 更新，保持参考策略固定，保存参数、参考模型标识及优化器进度
- 用新模型对保留 pairs 计算相对偏好分数，并为指定 prompts 生成真实回复

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

接收一组未用于训练的候选回复对，利用当前模型和冻结参考策略执行排序审计，输出可追溯分数及异常样本。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
