# GPUv1-F09 · 训练车辆外流场代理并交付阻力预测

Train an aerodynamic surrogate and deliver drag predictions

**组别**：科学机器学习与物理计算　 **实施优先级**：advanced　 **阶段**：design

**Canonical goal**：`drivaernet_aerographnet_surface_fields`

**Workflow family**：`external_aerodynamic_surrogate`

## 任务目标

利用已有CFD样本建立车辆外流场代理，交付能从真实车体曲面网格预测压力、壁面剪切和阻力的模型，并给出留出车辆的数值场。

## 具体来源工作负载

DrivAerNet v1约4000个车辆几何；PhysicsNeMo AeroGraphNet +experiment=drivaernet/agn。

## 输入与配置

- DrivAerNet_v1数据及对应原始train/val/test划分
- 官方drivaernet/agn模型、网格预处理和损失配置
- 真实网格、表面CFD标签和阻力系数；不混用DrivAerNet++划分

## 需要完成的工作

- 建立稳定的网格节点/边与标签映射
- 训练AeroGraphNet并保存模型和数据统计
- 为整个官方test split生成.vtp数值场和阻力表

## 交付物

- 可重载AGN检查点
- predicted_fields/*.vtp
- drag_predictions.csv与留出集压力/剪切/阻力误差

## 后续使用与状态

重新载入模型，对声明的新几何批次生成预测并与先前目录合并；保留网格缓存，避免跨车辆节点映射混淆。

## 独立验收

- 重读VTP，检查节点/几何和压力/剪切字段对应
- 独立加载模型对隐藏车辆真实推理并重算指标
- 检查划分无泄漏、阻力系数及单位/归一化；质量容差随固定参考预算校准

## 应拒绝的失败方式

- 只预测标量阻力而缺少要求的表面场
- 把Ahmed或新版++样本混入v1却不声明
- 删除复杂网格或只导出少量测试车
- 复制已有CFD标签当预测

## 规模配方

### Debug：仅调通

- **workload**：v1固定2训练/2验证车辆，原有网格预处理，仅做构建检查。

### Reference large：正式生产规模

- **data**：完整DrivAerNet v1官方train/val/test；采用drivaernet/agn定义的真实表面网格与节点处理。
- **work**：按来源模型训练阶段达到参考机校准的固定更新数，然后输出整个test split；不得把官方文档只跑2个test sample的演示参数当正式任务。
- **hardware_target**：T3：4×80GiB GPU，数据并行；不是已验证显存下限。

### 可选扩展：同一任务的变体

- **workload**：同一任务8 GPU或在相同v1数据上的单GPU分阶段执行；+ +版本需单独冻结数据revision，不能悄然更换。

## GPU工作与预期资源形态

真实不规则大曲面图的多层消息传递占用设备激活/边状态；网格缓存和数据加载形成与规则图像不同的GPU输入通道。

## 资源标签（待画像验证）

- large_mesh_graph
- message_passing
- sustained_training
- dataset_cache
- collectives

## 设备能力

- CUDA PyTorch
- PhysicsNeMo compatible graph implementation
- distributed all-reduce

## 后端要求

- VTK/PyVista与固定图框架版本
- 足够文件描述符和shared-memory支持预处理池
- GPU及固定训练rank映射

## 回放约束

- CFD真值是输入资产；GPU训练和预测必须由本次工具实际执行
- 图缓存冷热状态及预处理成本分开记录，不能只预热某个后端

## Builder需要实现的部分

- 冻结v1数据manifest与官方划分，避免页面默认跳到++
- 验证drivaernet/agn代码与数据接口
- 校准完整网格的GPU资源及固定训练预算
- 实现VTP、标量阻力和几何身份验证器

## 与相关任务的边界

服务于车辆外气动的物理场预测，输出连续曲面量；不同于通用图分类、点云语义分割或3D生成。

## 数据血缘

- DrivAerNet/v1
- PhysicsNeMo/AeroGraphNet/drivaernet-agn

## 任务范围与条件

- 数据为非商业研究许可；商业用途另有条件
- 网页含Ahmed设置，不能把Ahmed的8A100/500epoch结果归给DrivAerNet
- 模型质量与训练预算需参考验证

## 来源记录

- [F_AEROGRAPHNET] AeroGraphNet for external aerodynamic evaluation — [来源](https://docs.nvidia.com/physicsnemo/latest/physicsnemo/examples/cfd/external_aerodynamics/aero_graph_net/README.html)；检查位置：DrivAerNet; drivaernet/agn; training and inference
- [F_DRIVAERNET] DrivAerNet and DrivAerNet++ — [来源](https://github.com/Mohamedelrefaie/DrivAerNet)；检查位置：DrivAerNet_v1; train_val_test_splits; license

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
