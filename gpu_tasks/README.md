# GPU60 tasks and DeepSeek Flash solutions

独立的 GPU sandbox 任务包，包含 60 份任务规格、60 份 DeepSeek Flash 源码、原始 119 条来源记录、容器控制器及已测验收证据。

当前状态：60/60 通过容器编译与 CLI 检查；48 个冻结的真实 debug 实例通过执行与交付验收；12 个原生任务待补数据、权重或专用环境。正式 reference-large 配置尚未执行，模型质量单独记录。

- [REPORT.md](REPORT.md)：验收结果、资源限制、质量边界与复现步骤。
- [status.json](status.json)：逐题状态、质量指标和资源记录。
- [tasks/](tasks/)：每题的 `TASK.md`、Flash 实现 `solution/`、冻结输入 manifest 和证据 `evidence/`。
- [source_design/](source_design/)：原始正式规格、agent 提示和 119 条来源。
- [ASSETS.md](ASSETS.md)：冻结输入、模型和环境的恢复方式及未上传资产。

`TASK.md` 是本轮求解契约，`source_spec.json` 是原始正式规格，`input/manifest.json` 冻结实际 debug 变体。调试结果不能替代正式配置的结果。

运行使用 `run_delivery.py`，它为每题建立有资源上限的断网容器；验收用 `grade_task.py`。缺资产的原生任务 `doctor` 返回 78。环境、真实输入和任务模型恢复后才能执行；跨主机冷启动尚未验证。
