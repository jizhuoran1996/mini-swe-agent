# GPUv1-B08 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

把预训练 VideoMAE 适配到 Something-Something V2 的动作类别，为完整验证视频输出 clip ID、类别概率与预测，并交付可处理新片段的模型和视频解码/采样配置。

### 来源和工作范围

VideoMAE ViT-Base SSV2 source recipe: scripts/ssv2/videomae_vit_base_patch16_224_tubemasking_ratio_0.9_epoch_2400/finetune.sh; 174 classes; 16 frames; 30-epoch fine-tuning.

### 交付要求

- fine-tuned checkpoint 与优化器状态
- val clip predictions/probabilities
- label_map.json 与采样配置
- 批量预测入口和验证报告

### 必须完成的工作

- 准备完整实际视频，检查解码长度与标注映射。
- 执行真实 GPU 微调，保留声明的帧采样与有效 batch。
- 对完整验证集执行源 multi-view 聚合，交付每片段概率和分类模型。

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

保留模型后处理预先声明的动作复核视频清单，交付易混动作对的实际预测和对应帧时间位置。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
