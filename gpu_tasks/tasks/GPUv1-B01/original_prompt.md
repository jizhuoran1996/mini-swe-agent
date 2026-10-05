# GPUv1-B01 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

为完整 ImageNet-1K 图像库训练 ResNet-50 分类器，交付能独立重载的模型、标签映射和批量分类入口，并在未参与训练的验证集上生成逐图预测及分类质量报告。

### 来源和工作范围

TorchVision references/classification/train.py; ResNet-50; ILSVRC2012/ImageNet-1K train and validation splits; reference 90-epoch recipe.

### 交付要求

- model.pth 与完整训练状态
- class_index.json
- predict.py 与锁定配置
- validation_predictions.parquet、重算指标和数据清单

### 必须完成的工作

- 检查 train/val 清单与类别目录映射，按上游预处理训练真实图像。
- 执行完整声明训练计划，保存权重、优化器、学习率和数据游标状态。
- 独立重载 checkpoint，对完整验证集推理并交付逐图分类记录。

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

用交付的模型处理一份预先冻结、来自验证集的复核清单，生成指定类别的错误案例清单；复用模型文件与标签映射，不重新训练。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
