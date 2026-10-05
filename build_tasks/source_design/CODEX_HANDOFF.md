# 实现交接：从任务卡到可采集实例

## 交付层次

本包完成 60 个来源绑定的任务规格、官方构建/测试入口和验收设计。`task_registry.json` 是机器可读主记录；`tasks.jsonl` 是同一记录的逐行视图；`task_briefs/` 面向实现者，`agent_prompts/` 是实例化后交给 agent 的提示模板。

每题记录 `new_builder_work`。执行以下步骤将设计提升为可运行、可验证、可采集和可回放实例，不用重新发明工程目标。

## 推荐实施顺序

1. **锁定实例**：选择任务指定/允许的 release，解析不可变源码、子模块和依赖引用；固定 core/reference/extended 之一，填写 source dependency lock。
2. **准备环境**：预置工具链与依赖；验证离线构建可行。初始环境无目标工程的构建结果。记录 feature probes 和实际配置，防止缺依赖导致功能自动缩水。
3. **实现验收**：展开官方测试选择；保存必需目标及 nonempty 检查；实现源码树之外的真实 consumer。定义失败分类与证据路径。
4. **完整预演**：从初始环境真实完成构建、测试、打包及验收。修正具体版本所需命令，不改变原来的功能目标；保存 revision 和修改记录。
5. **采集轨迹**：让 agent 解决任务，保留完整模型等待、工具依赖、动态句柄、工作树与结果。不要仅把固定脚本的命令行包装成虚构 agent 对话。
6. **验证回放**：在清洁初始环境中真实重放工具命令，核对输出与功能 oracle，处理动态 PID/端口和后台作业依赖。
7. **建立画像**：固定参考配置，测量资源与阶段成本；记录成功/失败和实际工作量，再决定资源标签、规模档和调配资格。

## First pilots

每组先做两题会比较容易判断环境与验证器是否通用。建议候选见 `SIZE_AND_PILOTS.md`；它不是将大型工程缩成 smoke test，而是先用小型/中型工程打通相同的交付与记账流程，再推进 PyTorch、LLVM、GCC、TensorFlow、Envoy 等大型工程。

## 运行约束

所有写入使用 session 范围内源码副本、build tree、安装前缀和临时目录。优先使用 unprivileged prefix，不安装到宿主系统目录。若源码必须 in-tree 构建，就为该实例准备私有源码副本。不要重定义 HOME 或依赖用户现有配置；通过构建工具支持的显式路径配置。

不在 task script 内更改宿主 CPU governor、清空宿主页缓存或切换全局 runtime。那些属于受控实验平台设置。公网下载、远端构建执行和对象缓存默认为关闭或明确预置，按 profile 需要再启用。

## 证据与状态

`readiness.stage` 从 `source_grounded_design` 逐步进入 `instance_built`、`oracle_verified`、`trajectory_collected`、`replay_verified`、`reference_profiled`。每步应有 artifact path 和 SHA-256。设计阶段的实际资源数值为空，不用估算值冒充 profiling。

`scripts/validate_pack.py` 验证设计包结构、ID、来源关联、关键字段和状态一致性；它不编译 60 个工程，也不代替任务专用 oracle。修改 registry 后运行 `scripts/render_views.py` 更新任务卡、提示和目录，再重新执行结构校验并更新 checksum。
