# GPUv1-B10 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

使用 Virtual KITTI 2 的真实渲染 RGB/深度数据适配户外米制深度模型，并在声明的真实 KITTI 验证图像上交付以米为单位的深度图；对指定图像结合相机内参导出可读取点云。

### 来源和工作范围

Depth Anything V2 metric_depth/train.py --dataset vkitti --encoder vitl; dataset/splits/vkitti2/train.txt and dataset/splits/kitti/val.txt; 40-epoch default.

### 交付要求

- metric-depth checkpoint 与训练配置
- 每图 float depth 数组和几何 metadata
- 声明图像的 PLY 点云
- 独立推理脚本、深度评测和投影报告

### 必须完成的工作

- 核对 VKITTI2 深度单位、有效区域和源划分，不将真实 KITTI 验证标签用于训练。
- 按源 metric-depth 配方训练 encoder/head 并保留模型/优化器状态。
- 对完整 KITTI 验证清单预测米制深度，按真实内参把指定结果投影为点云。

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

用已保存模型处理新的已声明户外帧清单，交付深度及按距离分层的几何统计；复用模型和固定内参规则。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
