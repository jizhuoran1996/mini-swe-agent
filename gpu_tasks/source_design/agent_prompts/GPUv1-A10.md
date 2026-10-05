# GPUv1-A10 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

用固定英文百科快照训练通用文本表示模型，交付编码器、词表和可恢复训练状态，并在独立文档上完成掩码预测与句子表示导出。

### 来源和工作范围

NVIDIA BERT large two-phase pretraining + Wikimedia Wikipedia 20231101.en

### 交付要求

- bert_encoder.pt、large.json、vocab.txt
- optimizer_and_progress/与预训练数据manifest
- heldout_mlm_predictions、sentence_embeddings及可复算评测报告

### 必须完成的工作

- 按文章边界构建预训练数据和固定masked targets，保留article IDs和token覆盖清单
- 从声明随机初始化运行来源LAMB两阶段训练，真实更新参数并保存最终及可恢复状态
- 重载encoder对保留文章计算masked-token NLL/accuracy，导出一组真实句子表示

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

使用已交付encoder处理新的冻结文档批次，输出句子表示和掩码预测，复用训练完成后的模型状态。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
