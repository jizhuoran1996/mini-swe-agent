# GPUv1-A09 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

使用真实问题、相关段落和困难负例训练问答检索模型，交付问题/段落编码器，并为冻结候选段落集合生成可用于后续检索的表征及验证排名。

### 来源和工作范围

DPR biencoder_nq with nq_train+nq_train_hn1, nq_dev, BERT-base question/context encoders

### 交付要求

- biencoder.pt及tokenizer/config
- passage_embeddings/与passage_id映射
- validation_rankings.jsonl、平均排名/Recall报告和训练清单

### 必须完成的工作

- 核对正例、困难负例和问题划分，保留去重与来源ID
- 按来源40-epoch训练协议执行双编码器更新，保存question/context encoder及optimizer
- 将固定验证候选池编码，生成每个问题的候选排名；使用准确点积评测以隔离ANN算法影响

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

使用已训练的context encoder编码另一批冻结段落，并用question encoder处理后续问题；验证旧新向量维度和模型版本一致。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
