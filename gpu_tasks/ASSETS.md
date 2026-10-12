# Assets outside Git

本目录提交60题规格、原始Flash源码、已验收的Codex修复、尚待GPU验收的修复、容器与验收程序、来源和资产锁、测得证据。冻结数据、隐藏oracle、模型权重、完整运行产物和Python依赖环境保存在原机。

当前v1.1源码归档位于 `/data/data/zrji/gpu60-native-20261012/release/`，内容已展开到本目录，发布记录为51/60个debug实例通过。归档的字节数与SHA256见 `release_manifest.json`；Git中的发布说明和校验清单另有更新。

| 文件 | 字节数 | SHA256 |
|---|---:|---|
| `gpu60_review_v1.1.zip` | 3207691 | `44ff8be45a8c6ba78aef932a6ff785fc73aa86a8c2dc35ffbefe2cfb77fed476` |

新原生输入、模型、依赖环境和产物位于 `/data/data/zrji/gpu60-native-20261012/`；模型与原有冻结输入也保存在 `/home/zrji/sbench/gpu_suite/`。v1.1构建使用 `--skip-inputs`，没有生成新的输入ZIP。当前没有GitHub Release资产下载链接。

旧v1输入归档仍位于 `/home/zrji/sbench/gpu_suite/release/gpu60_debug_inputs_v1.zip`（486128453字节，SHA256 `255bcef915daab8365aa983d9ceea94e5aa09269dfbb430529339bad6db1d562`）。它记录此前48项通过时的输入，不能覆盖本次新增原生资产或替换当前输入清单。恢复时依据每题 `input_lock.json` 核对文件，模型依据 `model_locks/` 核对。

在本目录验证Git源码和记录：

```bash
sha256sum -c SHA256SUMS
```

`tasks/*/input_lock.json` 锁定真实输入文件的字节数和SHA256；隐藏oracle仅用于评分阶段。`.gitignore` 排除恢复后的大资产、运行输出和本地凭据。`runtime/native_environment/`记录两个新增专用环境及本次完成情况。

按 `model_locks/` 中的 revision、URL 和 SHA256 恢复模型。`restore_models.py` 支持其中的 Hugging Face 模型；其他来源使用相应锁中的 URL 和准备脚本。按照 [REPORT.md](REPORT.md) 和 `runtime/environment_*.json` 恢复依赖环境，然后使用容器运行器执行任务。

重新运行 `prepare_*.py` 可能下载上游当前版本，得到不同的实例。优先恢复冻结输入；输入锁不匹配时不能将新数据算作本次已验收实例。

`release_manifest.json`记录当前v1.1本地归档；`release_validation.json`记录本次发布检查。本目录的 `SHA256SUMS` 校验本次Git导出的文件；检查发布文件不会增加GPU验收数。
