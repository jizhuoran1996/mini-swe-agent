# GPUv1-D07 · 将混合版式文档解析为可再利用的结构化档案

Parse mixed-layout documents into reusable structured archives

**组别**：任务侧模型推理与检索处理　 **实施优先级**：advanced　 **阶段**：design

**Canonical goal**：`omnidocbench_full_page_structured_archive`

**Workflow family**：`document_structural_parsing`

## 任务目标

将整页文档转为保持阅读顺序的 Markdown 档案，正确保存表格结构和 LaTeX 公式，使产物可以用于后续检索、表格导出与公式处理。

## 具体来源工作负载

OmniDocBench 全 1,651 页，v1.7 评估协议对应的数据快照，Qwen2.5-VL-72B-Instruct

## 输入与配置

- OmniDocBench 官方整页图像与页 ID；结构标注仅验证器可见
- Qwen2.5-VL-72B-Instruct
- 固定 OCR/表格/公式提示与页面尺寸处理配置

## 需要完成的工作

- 实际加载整页图像并执行多模态模型解析
- 为每页输出 Markdown，并按约定保留 HTML 表格与 LaTeX 公式
- 交付稳定命名的目录和解析失败清单，随后从产物导出表格目录

## 交付物

- pages/*.md
- tables/*.html
- formula_manifest.jsonl
- page_status.jsonl

## 后续使用与状态

从已生成的页面档案提取指定表格和公式，处理后续页面并更新目录；模型驻留策略跟随采集轨迹。

## 独立验收

- 页 ID 覆盖和文件可读性检查；表格结构/公式语法进行独立解析
- 用冻结的 OmniDocBench 匹配与 text/table/formula/reading-order 指标复算质量
- 质量容差由参考运行标定；不以文件数量代替内容验收

## 应拒绝的失败方式

- 把整张图片链接放进 Markdown 充当解析
- 只输出 OCR 文本而丢弃表格和公式
- 复制公开 leaderboard 结果或标注 JSON

## 规模配方

### Debug：仅调通

- **data**：按不同文档类型固定 12 页
- **hardware_target**：T3：4×80 GiB GPU；先验收输出格式

### Reference large：正式生产规模

- **data**：全量 1,651 页；v1.7 evaluator 与数据内容 hash 同时冻结
- **model**：Qwen2.5-VL-72B-Instruct，BF16，固定页面像素预算与生成结束规则
- **hardware_target**：T3：4×80 GiB GPU
- **useful_output**：整页结构化文档档案，含表格与公式

### 可选扩展：同一任务的变体

- **data**：相同页面清单按文档分片，不重复页面增压
- **hardware_target**：T3：最多 8 GPU 多副本/模型并行
- **not_new_task**：True

## GPU工作与预期资源形态

高分辨率页面视觉编码与较长结构化输出使 prefill、decode、驻留权重和结果工作区共同参与。

## 资源标签（待画像验证）

- large_weight_residency
- high_resolution_vision
- long_decode
- structured_artifacts

## 设备能力

- CUDA
- BF16
- multi_gpu_tensor_parallel
- image_processor

## 后端要求

- 被测 sandbox 能访问声明的 GPU 设备与匹配的 CUDA/driver 用户态库；正式运行不静默转 CPU 或远程模型 API。
- 初始模型和输入在声明的只读路径，产物写入本 session 工作区；驱动兼容性与单/多 GPU 能力准入独立于功能验收。

## 回放约束

- 替换的仅是负责决策的 agent LLM；本任务载入的模型及其 prefill、decode、embedding 或 reranking 每次都真实执行，不返回旧预测冒充执行。
- 冻结模型/数据内容哈希、tokenizer/processor、dtype、算子后端、解码及分片参数；服务端口和作业 ID 在本轮绑定，不能复用旧句柄。
- 工具完成以 CUDA 工作与输出提交完成为准；记录的模型等待不替代服务 ready、CUDA event 或文件落盘依赖。

## Builder需要实现的部分

- 绑定 v1.7 评估代码与对应完整数据快照；不要沿用旧 1,355 页计数
- 为指定 72B 模型固定页面提示与 processor，并实测完整生成上限
- 接入原生解析指标与 HTML/LaTeX 产物有效性检查

## 与相关任务的边界

整页内容解析输出，而非 D05 的单个问题答案；同属文档多模态大类，但目标、oracle 与输出结构不同。

## 数据血缘

- omnidocbench

## 任务范围与条件

- 代码许可证与文档数据研究用途条款不同。
- 源标注和匹配版本变化会改变分数，版本不可只写 main。

## 来源记录

- [D_OMNIDOC] OmniDocBench document parsing benchmark — [来源](https://github.com/opendatalab/OmniDocBench)；检查位置：Updates v1.7; full 1,651 pages; end2end predictions and text/table/formula/reading-order metrics; Qwen2.5-VL-72B model entry
- [D_QWENVL72] Qwen2.5-VL-72B-Instruct model card — [来源](https://huggingface.co/Qwen/Qwen2.5-VL-72B-Instruct)；检查位置：Local image/video inference and processing controls; model license; Processing Long Texts: long-video max_position_embeddings may be raised to 64k; YaRN caution

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
