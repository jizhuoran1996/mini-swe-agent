# GPUv1-A05：训练英语语音到德语文本的翻译模型

以英语录音和配对德语译文训练语音翻译模型，交付可以直接从英语音频生成德语文本的模型，并提交完整测试集译文。

本次执行是小规模真实 GPU 调试实例。原包正式配置完整保留；调试通过不能写成正式规模通过。模型或算法计划：`openai/whisper-tiny`。实际输入、模型 revision、路径和 SHA256 必须以只读 `input/manifest.json` 为准；资产未准备好时，报告缺失，不生成假输入或假预测。

## 来源及范围

CoVoST2 English–German + fairseq s2t_transformer_s ST recipe

调试范围：{"data": "train_st_en_de中固定200个互异音频，测试20个", "work": "相同声学与翻译架构的数据连通性检查", "hardware_target": "T1 1×24–48 GiB"}

## 实际工作

- 匹配音频ID、目标译文和分割，构建特征/词表与配置
- 按 ST recipe 执行真实30,000次更新，来源的encoder冻结前1000更新策略保持声明
- 选择并平均来源协议所需checkpoint，生成test_st_en_de译文

## 交付物

- speech_translation.pt、数据配置与词表
- test_translations.jsonl：audio_id及德语预测
- sacrebleu报告、checkpoint lineage和训练清单

统一提供 `solution/main.py`、`solution/README.md`、可恢复产物和 `output/run.json`。源码和输出只能写到 `solution/`、`output/`。说明所有入口、依赖、输入覆盖、精度、seed、参数、完成事件、阶段耗时和实际设备；训练任务必须记录参数更新与恢复状态，服务任务必须记录真正可查询的 ready。

## 后续使用和独立验收

使用交付模型处理另一组冻结英语录音，并对长短音频分别汇总翻译质量，复用先前的模型和特征配置。

- 独立进程从原始音频运行真实模型，核对音频到译文一一映射
- 全量输出句数/语言配置/顺序正确；独立计算sacreBLEU
- 训练集和测试集严格按CoVoST2划分，质量容差在参考执行后固定
- 确认声学encoder路径真实使用，未用人工transcript调用文本翻译器替代

禁止情况：

- 直接使用参考德语译文或英语transcript进行旁路翻译
- 未训练而仅复制公开ST checkpoint
- 漏掉较长或难解码的音频

## 测试环境

工作目录 `/workspace`，单张 RTX 5090，容器根文件系统和输入只读，无网络，不挂载主机 home、Docker socket 或 API key。最多 24 GiB 主机 RAM、无 swap、6 CPU、256 进程、8 GiB 工作区。实际参数见运行 manifest；GPU 作业串行，并保留显存余量。超限会终止本容器。使用已经提供的 `python` 和框架；缺失资产应报告，不能在主机执行替代工作。

请在容器中实际实现和执行任务，再交付源码、可重载产物和完成说明。不要人为增加工具调用、重复样本、sleep 或无用 GPU 状态。


当前实施约束：
Use fairseq speech_to_text CUDA training on all frozen genuine train.tsv records, source s2t_transformer_s. Save checkpoint_last.pt with optimizer/RNG, config and native generated translations; source frame features must not be replaced by random logmels. Expose run and resume with extra updates; use upstream generate.py for a new TSV.
只读input中所需文件详见manifest。实现完整source-native适配器，入口 run --input input --output output、resume（若有状态）与doctor --input input；doctor必须列出所有缺失文件/软件并exit78。未准入资产不准造假、下载、CPU替代或报告任务通过。main --help与源码编译是基础可用性检查。
