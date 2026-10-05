# GPUv1-D09 — 候选文档重排器（Cross-Encoder Reranker）

对 `input/requests.jsonl` 中的真实 MS MARCO query / 候选列表，用本地
`/models/cross-encoder--ms-marco-MiniLM-L6-v2`
(`AutoModelForSequenceClassification`, BertForSequenceClassification)
在 CUDA 上实际 cross-encode 每个 `(query, passage)` pair，取 **raw logit** 作为分数。

- `max_length = 256`，`truncation=True`，batch 内 `padding=True`（padding 被 attention mask 屏蔽，不影响 logits）
- 分数 = `outputs.logits.reshape(-1)`，即 identity 激活后的 logit，不做 sigmoid/softmax
- 排序：`raw_score` 降序；同分时 passage id 升序（数字 id 按数值、其他按字典序，稳定全序）
- 模型 fp32 + `model.eval()` + `torch.inference_mode()`，无 dropout/随机性，重复运行结果逐比特一致
- 输出覆盖全部候选：无漏项、无重复（输入若出现重复 id，仅保留首次出现，保证输出无重复）

## 目录与入口

```
python solution/main.py run  --input input --output output
python solution/main.py serve --port PORT
```

`run --input` 可传目录（自动找 `requests.jsonl`）或直接传 jsonl 文件。

产物（`output/`）：

| 文件 | 内容 |
| --- | --- |
| `rankings.jsonl` | 每个 query 一行：`query_id`、`query`、`num_candidates`、`rankings`（别名 `passages`）数组；数组元素含 `passage_id`（别名 `id`）、`raw_score`（别名 `score`）、`rank` |
| `run.json` | 运行元数据：模型/修订、CUDA 设备、max_length/batch、评分与排序口径、输入输出 sha256、计数、逐 query top-1、耗时、库版本 |

示例行：

```json
{"query_id": "19699", "query": "what is rba", "num_candidates": 10,
 "rankings": [{"passage_id": "4", "id": "4", "raw_score": 10.555728912353516, "score": 10.555728912353516, "rank": 1}, ...]}
```

## 服务模式

模型在服务启动时加载一次并在进程内复用（不按请求重载、不缓存旧结果），
因此对**全新候选列表**、**空闲后**、**重复请求**都可用且幂等。`ThreadingHTTPServer` +
GPU 推理互斥锁，支持并发连接。

- `GET /health`（也支持 `/healthz`、`/`）→
  `{"status":"ok","healthy":true,"model":...,"device":{...},"max_length":256,"requests_served":N,"pairs_scored":M}`
- `POST /rerank`，body `{"query": "...", "passages": [{"id": "...", "text": "..."}]}` →
  `{"status":"ok","query":...,"num_candidates":N,"rankings":[{"passage_id","id","raw_score","score","rank"}, ...],"results":[...]}`
- 非法 JSON / 缺 `query` / 缺 `passages` / 候选缺 `id` → `400`；未知路由 → `404`
- `SIGTERM` / `SIGINT`：停止接受连接、关闭 socket、释放模型与 CUDA 缓存，进程以状态码 `0` 干净退出

服务默认监听 `0.0.0.0`（可用 `--host` 覆盖，如 `--host 127.0.0.1`）；`--port` 必填。

## 复现与自检结果

本机运行（RTX 5090，PyTorch 2.11.0+cu129 / Transformers 5.12.0 / NumPy 2.3.5）：

1. `run`：8 个 query、71 个候选 pair，全部打分成功；`rankings.jsonl` 8 行、`run.json` 生成。
2. 独立标准模型重算：逐 pair 单独 tokenize（不 padding）用同一模型在 CUDA 重算 logits，
   与 `rankings.jsonl` 的 `raw_score` 最大绝对差 **2.56e-06**（要求 ≤ 1e-4）；
   8 个 query 的候选 id 集合与输入完全一致、无重复，rank 连续且排序正确。
3. 确定性：相同输入重复 `run`，`rankings.jsonl` 的 sha256 完全一致。
4. 服务：`/health` 200；首个请求即对未见候选正确评分；空闲 6s 后新候选请求延迟 ~7ms 正常返回；
   重复请求分数一致（模型复用、无重载）；3 类非法输入均 400、未知路由 404；
   `SIGTERM` 后进程退出码 0、端口释放、日志输出 `[serve] stopped cleanly`。

## 说明

- 容器无网络，模型从本地只读目录加载（`local_files_only=True`），未使用任何外部下载。
- 本题不提供 relevance 标签，因此本仓库**不计算/不宣称 MRR**；真实标签 MRR 由评测方另行报告。
- `input/manifest.json` 标明本题为 debug 变体（MiniLM cross-encoder 替代原 8B reranker、
  8 条真实候选列表，`scale=debug_only`），未宣称完成 reference-large。
