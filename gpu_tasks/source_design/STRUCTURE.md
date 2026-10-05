# 机器可读结构

`task_registry.json`是主记录，顶层为metadata和tasks；`tasks.jsonl`逐行保存同一批完整task对象。`sources.json`顶层为metadata和sources，使用source ID引用。可重复URL保留在不同来源记录中；统计上不能视为独立benchmark。

## Task字段

- 身份：id、group、title_zh/title_en、canonical_goal_key、workflow_family、data_lineage。
- 来源：source_task_or_workload、source_ids、derivation_kind。
- 任务合同：agent_goal、inputs、required_work、deliverables、continuation、oracle、negative_cases。
- 规模：scale_plan.debug/reference_large/optional_scale_out；每档为可扩展对象，完整说明数据、模型/计算和工程设备目标。
- 系统条件：gpu_rationale、resource_shape_tags、gpu_capabilities、backend_requirements、replay_notes。
- 实施：new_builder_work、distinct_from_related_tasks、implementation_priority、limitations。
- 证据：readiness.stage、readiness.evidence；reference_measurements中的未知实测值为null。
- 视图：agent_prompt_path、task_brief_path；部分任务增加input_visibility和oracle_scope。

## 状态前进

`design → built → verified → replayed → profiled → resource_admitted`。

各阶段需要累计证据：built需要asset_lock/environment_lock/implementation_manifest；verified增加oracle_report；replayed增加trajectory_manifest/replay_report；profiled增加reference_profile及必要实测值；resource_admitted增加admission_report。证据字段填`{"path":"evidence/file.json","sha256":"实际64位十六进制哈希"}`，路径相对包根。必须存在真实文件并匹配hash。校验器只检查证据结构和身份，不能替人判断结果的科学有效性。

修改主记录后运行`python3 render_views.py --root .`再运行`python3 validate_plan.py --self-check`。README和发布报告描述本次版本，后续新发布时需同步更新并重生成校验和。
