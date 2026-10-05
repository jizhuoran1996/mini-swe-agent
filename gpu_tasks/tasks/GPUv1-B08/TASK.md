# GPUv1-B08：微调视频动作识别并输出片段目录

把预训练 VideoMAE 适配到 Something-Something V2 的动作类别，为完整验证视频输出 clip ID、类别概率与预测，并交付可处理新片段的模型和视频解码/采样配置。

本次执行是小规模真实 GPU 调试实例。原包正式配置完整保留；调试通过不能写成正式规模通过。模型或算法计划：`VideoMAE ViT-Base`。实际输入、模型 revision、路径和 SHA256 必须以只读 `input/manifest.json` 为准；资产未准备好时，报告缺失，不生成假输入或假预测。

## 来源及范围

VideoMAE ViT-Base SSV2 source recipe: scripts/ssv2/videomae_vit_base_patch16_224_tubemasking_ratio_0.9_epoch_2400/finetune.sh; 174 classes; 16 frames; 30-epoch fine-tuning.

调试范围：{"data": "固定数百个真实视频的短调试清单", "schedule": "短微调仅检查解码、label 和 checkpoint"}

## 实际工作

- 准备完整实际视频，检查解码长度与标注映射。
- 执行真实 GPU 微调，保留声明的帧采样与有效 batch。
- 对完整验证集执行源 multi-view 聚合，交付每片段概率和分类模型。

## 交付物

- fine-tuned checkpoint 与优化器状态
- val clip predictions/probabilities
- label_map.json 与采样配置
- 批量预测入口和验证报告

统一提供 `solution/main.py`、`solution/README.md`、可恢复产物和 `output/run.json`。源码和输出只能写到 `solution/`、`output/`。说明所有入口、依赖、输入覆盖、精度、seed、参数、完成事件、阶段耗时和实际设备；训练任务必须记录参数更新与恢复状态，服务任务必须记录真正可查询的 ready。

## 后续使用和独立验收

保留模型后处理预先声明的动作复核视频清单，交付易混动作对的实际预测和对应帧时间位置。

- 核对原视频 ID 覆盖和 174 类概率维度、有限性与归一化。
- 独立按固定 multi-view 规则聚合预测并重算 top-k，参考运行校准容差。
- 检查真实视频解码和不同时间帧，拒绝把静态帧复制成整段。

禁止情况：

- 用单张静态帧重复填满视频
- 删除无法正确处理的 clip
- 把标签抄成 one-hot 概率
- 不同后端采用不同 test crop/segment 数

## 测试环境

工作目录 `/workspace`，单张 RTX 5090，容器根文件系统和输入只读，无网络，不挂载主机 home、Docker socket 或 API key。最多 24 GiB 主机 RAM、无 swap、6 CPU、256 进程、8 GiB 工作区。实际参数见运行 manifest；GPU 作业串行，并保留显存余量。超限会终止本容器。使用已经提供的 `python` 和框架；缺失资产应报告，不能在主机执行替代工作。

请在容器中实际实现和执行任务，再交付源码、可重载产物和完成说明。不要人为增加工具调用、重复样本、sleep 或无用 GPU 状态。


当前实施约束：
Native CUDA VideoMAE finetuning from true pretrained ViT Base,16 frames,174classes,real source clips. Persist checkpoint/optimizer/RNG, class maps, clip predictions; source official run_class_finetuning.py invocation; checkpoint reload and extra optimizer updates.
只读input中所需文件详见manifest。实现完整source-native适配器，入口 run --input input --output output、resume（若有状态）与doctor --input input；doctor必须列出所有缺失文件/软件并exit78。未准入资产不准造假、下载、CPU替代或报告任务通过。main --help与源码编译是基础可用性检查。
