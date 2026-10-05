# GPUv1-F06 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

使用给定SNAP势推进有限温度BCC钽晶体，交付可续跑的原子状态、能量漂移和径向分布报告，确认计算期间的结构行为。

### 来源和工作范围

LAMMPS examples/snap/in.snap.Ta06A；potentials/Ta06A.snap、Ta06A.snapcoeff、Ta06A.snapparam；Kokkos GPU。

### 交付要求

- initial.data和final.restart
- thermo.csv、trajectory文件和RDF结果
- 实际势/积分/邻域参数及构建信息

### 必须完成的工作

- 从官方晶格规则建立声明空间域并保存初态
- 通过Kokkos GPU进行NVE时间积分
- 输出规定频率的能量、原子轨迹和restart，计算RDF/结构统计

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

从final.restart接着积分5ps，再生成新增区间的统计；要求保留速度、盒和势配置。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
