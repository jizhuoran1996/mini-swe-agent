# Assets outside Git

本目录提交任务规格、Flash 源码、容器与验收程序、来源和资产锁、测得证据。冻结数据、隐藏 oracle、模型权重、完整运行产物和 Python 依赖环境未提交到 Git。

本次交付的两个本地归档位于原工作空间 `/home/zrji/sbench/gpu_suite/release/`：

| 文件 | 字节数 | SHA256 |
|---|---:|---|
| `gpu60_review_v1.zip` | 2658088 | `9bd2cdec2a4308a4f82419ae1fe24fe700f50380b02367c5d5726635a9a476cc` |
| `gpu60_debug_inputs_v1.zip` | 486128453 | `255bcef915daab8365aa983d9ceea94e5aa09269dfbb430529339bad6db1d562` |

源码归档的内容已展开提交。冻结输入归档约 464 MiB，保留在上述原机路径，尚未上传 GitHub；当前没有 GitHub Release 下载链接。

拿到冻结输入归档后，在本目录执行：

```bash
unzip /path/to/gpu60_debug_inputs_v1.zip -d .
sha256sum -c SHA256SUMS
```

归档含真实 debug 输入与独立验收所需的隐藏 oracle。`tasks/*/input_lock.json` 锁定输入文件的字节数和 SHA256；隐藏 oracle 仅用于评分阶段。`.gitignore` 排除恢复后的大资产、运行输出和本地凭据。

按 `model_locks/` 中的 revision、URL 和 SHA256 恢复模型。`restore_models.py` 支持其中的 Hugging Face 模型；其他来源使用相应锁中的 URL 和准备脚本。按照 [REPORT.md](REPORT.md) 和 `runtime/environment_*.json` 恢复依赖环境，然后使用容器运行器执行任务。

重新运行 `prepare_*.py` 可能下载上游当前版本，得到不同的实例。优先恢复冻结输入；输入锁不匹配时不能将新数据算作本次已验收实例。

`release_manifest.json` 与 `release_validation.json` 记录原始两个归档的校验结果；本目录的 `SHA256SUMS` 校验本次 Git 导出的文件。
