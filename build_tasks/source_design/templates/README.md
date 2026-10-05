# 实例模板

这些 JSON 是字段模板，null 由真实实例与证据填充，不是可直接执行的默认配置。task registry 绑定工程来源；instance 进一步冻结源码、工具链、目标、测试、缓存和并行配置。

- source_dependency_lock：代码、依赖、bootstrap 工具链和镜像身份。
- instance：clean/incremental 场景、具体构建目标、测试集合和资源预算。
- test_evidence：harness 的测试单位、非空集合、实际执行与失败/skip。
- replay_manifest：完整轨迹、计划到达、当前动态句柄和真实工具依赖。
- run_result：阶段、资源、结果、失败和产物。
- backend_capabilities：逐项证实的平台能力；null 表示未验证。

resource 标签按 profiling 确定；成功产物的 hash 证明本次身份，不自动要求不同编译环境产生逐字节相同文件。后台作业的结束依据当前执行结果，不能由记录的 sleep 推断。
