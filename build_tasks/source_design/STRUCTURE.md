# 记录结构

`task_registry.json` 顶层为 metadata 与 tasks；60 个 task 记录是主数据。`tasks.jsonl` 逐行保存完全相同的记录，不是删减摘要。`sources.json` 顶层为 metadata 与 sources，任务通过 source IDs 引用。

## 主要字段

- **身份与血缘**：id、group、project、upstream_repo、canonical_goal_key、source_ids、source_lineage。
- **工程目标**：agent_goal、source_task_or_workflow、target_scope、language_stack、build_system。
- **执行合同**：initial_state、required_work、build_recipe、test_selection、consumer_verification、deliverables、continuation。
- **配置**：scale_plan.core/reference/extended、incremental_variant、resource_controls、offline_dependency_plan、backend_requirements。
- **评价与回放**：oracle、negative_cases、replay_notes。
- **实施**：new_builder_work、implementation_priority、limitations、related_prior_tasks。
- **画像**：planned_scale_class 是规划标签；resource_shape_tags 是预期形态；reference_measurements 保存真实测量。
- **状态**：readiness.stage 与 readiness.evidence；design-only 记录不能填写实际资源测量。

build_recipe 使用 configure/build/package/test 四个入口，各项目按自己的工具语义解释，不强制构造虚假的独立阶段。test_selection 可为字符串或结构对象，最终 instance 必须冻结具体测试集合和报告单位。

## 状态推进

`source_grounded_design → instance_built → oracle_verified → trajectory_collected → replay_verified → reference_profiled`。

证据逐步累积：instance_built 需要 source_dependency_lock、environment_lock、implementation_manifest；oracle_verified 增加 oracle_report；trajectory_collected 增加 trajectory_manifest；replay_verified 增加 replay_report；reference_profiled 增加 reference_profile 和基本实测字段。

证据格式为 `{"path":"evidence/example.json","sha256":"实际64位十六进制hash"}`。路径相对包根，文件须真实存在且 hash 匹配。结构验证只证明证据身份和字段齐全，实际科学与工程有效性由对应 oracle 和结果检查负责。

## 视图重建

从包根目录执行 `python3 scripts/render_views.py --root .`，重新生成任务卡、agent 提示、目录、来源说明和 JSONL。之后执行 `python3 scripts/validate_pack.py --self-check --write-report`。README 为发布说明；修改任务范围/数量或发布新版本时同步更新，再生成 CHECKSUMS.sha256。
