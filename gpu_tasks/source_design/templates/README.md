# 实例化模板

模板中的null由实际构建与运行填充，不是可执行的默认配置。任务来源已在registry绑定；每次实例需要另外冻结输入ID、不可变版本、真实资产哈希、oracle和资源配置。

- `asset_lock.template.json`：按模型、数据、代码、评价器分别锁定；agent输入与oracle-only资产分开。
- `instance.template.json`：冻结工作量、初始/后续提示、设备预算、状态与质量规则。
- `replay_manifest.template.json`：记录轨迹身份、计划到达、真实工具依赖及每轮动态绑定。
- `run_report.template.json`：保留执行完整性、质量、资源准入和主机/设备记账。
- `backend_capabilities.template.json`：逐项实际验证；null表示未验证，不能当false或true。

GPU完成、服务ready与产物提交应有明确事件，不能仅依据Bash命令返回或固定sleep推定。字段provider/version/scope/units用于区分框架内存、设备显存和采样计数器。模板不规定某一版DCGM字段名。
