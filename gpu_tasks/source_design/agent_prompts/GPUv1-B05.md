# GPUv1-B05 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

处理 KiTS19 声明的完整三维 CT 病例集，生成肾脏与肿瘤的体积分割，恢复每例的空间信息，并交付可由下游程序读取的分割体和体积统计。

### 来源和工作范围

MLPerf Inference KiTS19 3D U-Net PyTorch CUDA workload; official 42-case accuracy set and matching reference model/preprocessing.

### 交付要求

- 每例 NIfTI 或明确声明的体素数组及 affine/spacing sidecar
- kidney/tumor volume CSV
- 可重载推理入口
- 病例覆盖、模型和配置 manifest

### 必须完成的工作

- 核对每例 CT 几何和输入规范，生成声明的预处理数据。
- 在 GPU 上执行全部病例的真实三维分割，处理完整体而不是少数二维切片。
- 恢复输出到声明空间，计算每类体积并交付 case-level 清单。

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

在保留模型的后续工具调用中，重访指定病例并导出指定切面及连通区域摘要；统计必须与已交付体分割一致。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
