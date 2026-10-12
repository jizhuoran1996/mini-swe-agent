# GPU60 review v1.1

60份任务规格与原始DeepSeek Flash源码，51个debug实例独立验收，9个尚待验收，正式大规模未执行。新增已验收实现保留Codex修复来源。

从[REPORT.md](REPORT.md)开始；[status.json](status.json)给出每题准确状态与质量/资源记录。TASK.md是本轮求解契约，source_spec.json是原始正式规格，input/manifest.json冻结实际调试变体。三者不可互相冒充。

模型、原始输入与大体积环境不在Git或review ZIP中；按各任务输入锁、[ASSETS.md](ASSETS.md)和REPORT.md恢复。原机gpu_suite/assets/models及/data/data/zrji/gpu60-native-20261012保存完整资产与结果。pending_native_repair目录保存尚未经过GPU验收的修复，不计为通过。

运行使用run_delivery.py，它为每题建立有界容器；验收用grade_task.py。缺资产原生任务doctor返回78，不会生成伪结果。参考本机已验收的环境版本，跨主机冷启动仍需验证。
