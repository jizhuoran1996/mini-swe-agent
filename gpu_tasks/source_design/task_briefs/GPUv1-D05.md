# GPUv1-D05 · 把文档图像问题转成可检索的答案台账

Convert document-image questions into a queryable answer ledger

**组别**：任务侧模型推理与检索处理　 **实施优先级**：standard　 **阶段**：design

**Canonical goal**：`docvqa_original_validation_answer_ledger`

**Workflow family**：`document_visual_question_answering`

## 任务目标

读取文档页面图像并回答清单中的业务问题，交付按 question ID 和页面 ID 组织的答案台账；保留模型以处理同页面的后续问题。

## 具体来源工作负载

原始 DocVQA 单页 validation 全集，Qwen2.5-VL-32B-Instruct；使用官方来源图像和问题，不用 DocVQA2026 小样本替代

## 输入与配置

- 原始 DocVQA validation 图像与问题、独立答案文件
- Qwen2.5-VL-32B-Instruct 官方模型与 processor
- 来源图像大小、固定像素预算和问题模板

## 需要完成的工作

- 对齐图像、问题和页面 ID，实际解码图像
- 用本地多模态模型执行视觉编码与答案生成
- 提交完整答案 JSON 和页面到结果的映射

## 交付物

- docvqa_answers.jsonl
- page_manifest.json
- processor_config.json

## 后续使用与状态

在同一模型进程处理其他页面问题，或复用已保留页面输入处理该页下一道来源问题。

## 独立验收

- 检查题目覆盖、实际输入页面和非空答案
- 用 ANLS 对独立标注重新评分，容差依据固定参考运行确定
- 留出页面问题真实调用，禁止仅通过台账缓存返回全部答案

## 应拒绝的失败方式

- 只做 OCR 转录而不回答题目
- 跳过高分辨率页面或改用现成预测
- 更换成 DocVQA2026 部分数据却沿用本任务 ID

## 规模配方

### Debug：仅调通

- **data**：16 张不同验证页面及其全部问题
- **hardware_target**：T2：单 80 GiB GPU

### Reference large：正式生产规模

- **data**：原始 DocVQA validation 完整问题及所有对应页面；builder 从官方清单冻结确切数量和哈希
- **model**：Qwen2.5-VL-32B-Instruct，BF16；像素预算遵循并固定官方 processor 设置
- **hardware_target**：T2：单 80 GiB GPU 为起点；完整形状容量在建包时验证
- **useful_output**：按题与页面组织的完整答案台账

### 可选扩展：同一任务的变体

- **data**：原有页面在 2–4 GPU 模型副本间分片
- **hardware_target**：T3：2–4 GPU，无需复制页面来制造规模
- **not_new_task**：True

## GPU工作与预期资源形态

32B 模型驻留结合图像输入和视觉 token，覆盖图片解码、H2D、视觉编码和文本生成。

## 资源标签（待画像验证）

- multimodal_encoder
- image_h2d
- weight_residency
- short_decode

## 设备能力

- CUDA
- BF16
- image_processor

## 后端要求

- 被测 sandbox 能访问声明的 GPU 设备与匹配的 CUDA/driver 用户态库；正式运行不静默转 CPU 或远程模型 API。
- 初始模型和输入在声明的只读路径，产物写入本 session 工作区；驱动兼容性与单/多 GPU 能力准入独立于功能验收。

## 回放约束

- 替换的仅是负责决策的 agent LLM；本任务载入的模型及其 prefill、decode、embedding 或 reranking 每次都真实执行，不返回旧预测冒充执行。
- 冻结模型/数据内容哈希、tokenizer/processor、dtype、算子后端、解码及分片参数；服务端口和作业 ID 在本轮绑定，不能复用旧句柄。
- 工具完成以 CUDA 工作与输出提交完成为准；记录的模型等待不替代服务 ready、CUDA event 或文件落盘依赖。

## Builder需要实现的部分

- 取得官方图像并绑定原始 validation 清单与许可
- 移植 Qwen 官方数据格式到 Qwen2.5-VL processor
- 制作 ANLS oracle 与页面覆盖检查

## 与相关任务的边界

按问题提取页面信息；D07 则交付整页结构化全文，因此交付目标与输出规模不同。

## 数据血缘

- docvqa

## 任务范围与条件

- 图像许可与访问条件需履行；规格 ZIP 不包含原始图像。
- ANLS 不能替代输入完整性和实际执行验证。

## 来源记录

- [D_DOCVQA] DocVQA dataset — [来源](https://site.docvqa.org/datasets/docvqa)；检查位置：DocVQA original document-image QA dataset, linked challenge access
- [D_DOCVQA_ADAPTER] Qwen-VL DocVQA evaluation recipe — [来源](https://github.com/QwenLM/Qwen-VL/blob/master/eval_mm/EVALUATION.md)；检查位置：DocVQA section: original images/annotations, val.jsonl, docvqa_val and evaluate_vqa.py
- [D_QWENVL32] Qwen2.5-VL-32B-Instruct model card — [来源](https://huggingface.co/Qwen/Qwen2.5-VL-32B-Instruct)；检查位置：Local image inference, batch inference, image resolution and video input examples

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
