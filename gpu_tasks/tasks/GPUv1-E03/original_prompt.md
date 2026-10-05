# GPUv1-E03 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

使用完整 HIGGS 数据训练可重载的信号/背景分类器，提交冻结测试集的逐事件概率及特征说明，支持后续新批次分类。

### 来源和工作范围

UCI HIGGS 11,000,000 rows; XGBoost CUDA histogram training and QuantileDMatrix

### 交付要求

- higgs_model.ubj
- test_probabilities.parquet
- feature_schema.json、training_manifest.json

### 必须完成的工作

- 验证列与标签并避免测试集参与拟合
- 在 GPU 构造量化数据并执行完整训练
- 保存 Booster、特征顺序及逐样本测试预测，再重新加载预测

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

用已加载模型对固定第二批事件产生概率和阈值分组统计，保留模型状态供查询。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
