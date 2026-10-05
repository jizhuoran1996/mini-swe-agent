# GPUv1-A03 · 构建可离线交付的英德机器翻译模型

Build an offline English–German translation model

**组别**：语言、语音与推荐模型训练　 **实施优先级**：standard　 **阶段**：design

**Canonical goal**：`wmt16_en_de_transformer_big`

**Workflow family**：`supervised_machine_translation`

## 任务目标

使用指定平行语料构建英德翻译模型，交付能够批量翻译新闻句子的模型与词表，并生成完整测试译文和可复算的质量报告。

## 具体来源工作负载

fairseq Scaling NMT: WMT16 En-De bpe32k + transformer_vaswani_wmt_en_de_big

## 输入与配置

- 来源中链接的 WMT16 En-De 32k BPE 完整训练数据
- newstest2013 验证与 newstest2014 测试
- Transformer-big、共享词表和 fairseq Scaling NMT 优化器设置

## 需要完成的工作

- 保持双语句对一一对应，建立共享字典和二进制数据清单
- 训练完整模型并按固定验证策略选择/平均 checkpoint
- 重新加载选定模型，执行 beam=4、lenpen=0.6 的实际测试解码和 detokenized sacreBLEU

## 交付物

- translation_model.pt、dict.en/de.txt、BPE 资产
- newstest2014.de 与逐句原始 sample IDs
- sacrebleu.json：版本、签名和可复算指标

## 后续使用与状态

用已交付模型翻译另一份冻结的新闻批次，保持原分词与词表；输出句序和完整译文。

## 独立验收

- 重载模型并重算固定子集输出，核对句数、顺序和无丢行
- 独立计算 sacreBLEU，与参考校准范围比较
- 检查训练/验证/测试清单独立，BPE 处理与评测签名一致
- 拒绝提交参考译文或只提交已知 benchmark 分数

## 应拒绝的失败方式

- 复制 target 测试文件作为译文
- 省略较长句子以降低耗时
- 训练小模型但将文件命名为 Transformer-big

## 规模配方

### Debug：仅调通

- **data**：训练句对固定 10,000 对、验证/测试各 100 句
- **work**：相同架构的流程检查
- **hardware_target**：T1 1×24–48 GiB

### Reference large：正式生产规模

- **data**：完整 WMT16 En-De bpe32k train，newstest2013/2014 原始划分
- **model**：Transformer-big；参考协议：验证 BLEU 连续5次评估无改进或30 epochs 上限，采集后冻结实际更新预算
- **output**：完整译文和可离线使用模型
- **hardware_target**：T3 4–8×40–80 GiB；工程目标，未测量

### 可选扩展：同一任务的变体

- **data**：同一全量语料
- **work**：设备数、批量积累和 checkpoint 频率作为运行配置；不复制句对放大规模
- **hardware_target**：T3 8 GPUs

## GPU工作与预期资源形态

完整平行语料上的 encoder–decoder 反向传播与序列解码包含持续计算、变长 batch、数据加载及模型持有。

## 资源标签（待画像验证）

- encoder_decoder_training
- variable_length
- all_reduce
- checkpoint_io
- decode_after_training

## 设备能力

- CUDA
- FP16 mixed precision
- NCCL

## 后端要求

- 固定 fairseq 和 CUDA 工具链；历史依赖需容器化
- 支持多进程数据加载与并行训练

## 回放约束

- 采集结束后把训练预算、数据序列和 checkpoint 选择规则固定；不同后端不以运行速度缩减样本
- 等待实际训练/保存完成再执行翻译

## Builder需要实现的部分

- 镜像化归档项目及准备数据的可用下载路径
- 冻结派生 early-stop/上限协议并进行质量校准
- 实现句级对照验证和完整轨迹采集

## 与相关任务的边界

文本到文本的跨语言交付；A05 输入为语音并含声学 encoder，A01/A08 的目标也不同。

## 数据血缘

- wmt16_en_de

## 任务范围与条件

- 训练上限是 THENAME 派生协议，不是官方发布分数的复现承诺
- 历史准备数据的地址和许可证需在构建前落实

## 来源记录

- [A_WMT_NMT] fairseq Scaling Neural Machine Translation — [来源](https://github.com/facebookresearch/fairseq/blob/main/examples/scaling_nmt/README.md)；检查位置：WMT16 En-De bpe32k data; transformer_vaswani_wmt_en_de_big; newstest2013/2014; checkpoint averaging

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
