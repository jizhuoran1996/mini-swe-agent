# GPUv1-B06 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

从 nuScenes 多次 LiDAR 扫描训练三维目标检测器，为完整验证场景交付包含位置、尺寸、朝向和速度的物体框，能够按场景和时间戳查询检测结果。

### 来源和工作范围

MMDetection3D CenterPoint configs/centerpoint/centerpoint_voxel0075_second_secfpn_head-circlenms_8xb4-cyclic-20e_nus-3d.py; nuScenes v1.0-trainval.

### 交付要求

- CenterPoint checkpoint
- nuScenes detection JSON 与场景查询索引
- 有效配置和转换程序
- 重算检测指标与数据清单

### 必须完成的工作

- 构建源格式数据索引，保留扫帧时间和坐标转换。
- 按源配置训练 CenterPoint 并保存优化器/模型状态。
- 对完整验证场景执行 3D 检测，转换到 nuScenes 输出格式并生成时间索引。

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

用既有检测结果追查指定时段的物体空间轨迹，并用保存模型重新处理预先选定的完整验证场景，核对 token 和坐标一致性。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
