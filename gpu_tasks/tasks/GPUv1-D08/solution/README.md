# GPUv1-D08 — 多语言文档向量与常驻编码接口

`solution/main.py` 是一个自包含实现：只依赖 `torch` / `transformers` / `numpy`
（服务端 HTTP 用标准库 `http.server`），**不使用 `sentence-transformers` 包**，
直接薄封装原模型的 tokenizer 与 Transformer encoder。

## 统一编码管线（encode 与 serve 走同一代码路径）

```
原始字符串
  -> AutoTokenizer.from_pretrained(model_path, ...)   # 原模型 fast tokenizer
     padding=longest_in_batch, truncation=True, max_length=128
  -> AutoModel.from_pretrained(model_path, dtype=float32).to("cuda")   # 真实 CUDA forward
     hidden = model(**batch).last_hidden_state          # (B, T, 384)
  -> attention-mask mean pooling                        # sum(h*mask)/sum(mask)
  -> F.normalize(p=2, dim=-1)                           # L2 normalize
  -> float32 numpy 向量
```

参数：`max_length=128`、`pooling=attention_mask_mean`、`normalize=l2`、`dtype=float32`、
`device=cuda`（RTX 5090，`torch.cuda` 实际执行，非占位张量）。

### 文档文本的组成

`input/documents.jsonl` 每行含 `id/lang/title/text`。默认编码 **`text` 字段本身**
（`parameters.text_template = "{text}"`，已写入 `output/run.json`）。
如需将标题并入，可用 `--text-template "{title}\n{text}"` 重新生成。
`document_ids.json` 保存原始 JSONL 顺序的 `id` 列表；向量与之一一对应。

## 1) 离线编码

```bash
python solution/main.py encode --input input/documents.jsonl --output output
```

产物（`output/`）：

| 文件 | 内容 |
| --- | --- |
| `embeddings.npy` | `(200, 384) float32`，L2 归一化，行序 = 输入行序 |
| `document_ids.json` | 200 个原始 `id`，原顺序 |
| `run.json` | 输入/模型 hash、参数与覆盖、截断覆盖统计、同步耗时、输出 hash、环境版本 |

`run.json` 关键字段：

* `source.sha256` — `input/documents.jsonl` 的 sha256（与 manifest 一致：
  `6edb9822…eb48a`），`model_hash.aggregate_sha256` / `weights_sha256` — 模型目录全文件 hash；
* `parameters` — `max_length=128`、`truncation=True`、`padding=longest_in_batch`、
  `pooling=attention_mask_mean`、`normalize=l2`、`dtype=float32`、`device=cuda`、`text_template`；
* `overrides` — 相对模型默认（`max_seq_length=128`）的覆盖说明；
* `coverage` — token 长度分布与 `max_length` 截断条数（200 条中 95 条超长被截断）；
* `timings_sec` — `read_input` / `hash_model` / `model_load` / `encode_documents` /
  `reencode_check` / `total_sync`，以及吞吐 `throughput_docs_per_sec`；
* `determinism_check` — 同进程重复编码的最小 cosine（≈0.9999998）；
* `outputs.*.sha256`、`environment`（python/torch/transformers/numpy/CUDA 设备）。

## 2) 常驻服务

```bash
python solution/main.py serve --port 8931
```

启动时同步加载模型到 CUDA 并做一次 warm-up，然后绑定端口并在 stdout 打印一行
`{"event":"ready", ...}`（含端口、设备名、pid）。

* `GET /health` — 真实 CUDA ready 后返回 200：
  `{"status":"ok","ready":true,"model":"sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "device":"cuda","device_name":"NVIDIA GeForce RTX 5090","dtype":"float32",
    "max_length":128,"embedding_dim":384,"pooling":"attention_mask_mean","normalize":"l2","pid":…}`
* `POST /encode` — body `{"texts": ["…", …]}`，返回
  `{"count":n,"dim":384,"normalized":true,"embeddings":[[…384 floats…], …], "device":"cuda","elapsed_sec":…}`。
  空 `texts` 返回空列表；非法 body 返回 400；未知路径返回 404。

服务常驻内存，模型与 CUDA context 不随请求重建：任意空闲间隔后仍可继续调用；
推理用锁串行化（单卡单进程）。收到 `SIGTERM`/`SIGINT` 时优雅 `shutdown()`，
释放模型、关闭 socket、打印 `{"event":"stopped"}` 后以退出码 0 结束进程。
服务不读取也不依赖 `output/embeddings.npy`，每个请求都在 CUDA 上重新前向计算。

## 3) 已执行的验证（均为真实运行结果）

* `encode` 产物 shape `(200,384) float32`，行 L2 范数 ≈ 1；`document_ids.json` 与输入顺序一致。
* 独立的 batch-size=1 参考实现（另一个进程、另一条代码路径）重算全部 200 条向量：
  **min cosine = 0.99999976**（≥ 0.9999）。
* 同一输入两次跨进程编码：min cosine ≈ 1.0，向量稳定。
* `serve`：`/health` 报 `device=cuda` / `device_name=NVIDIA GeForce RTX 5090`；
  对全新文本（未参与离线结果）`/encode` 与同进程独立参考实现的 min cosine ≈ 0.9999999；
  同一请求两次调用的 min cosine ≈ 0.9999999；空闲 10s / 6s 后继续调用一致；
  超长文本（`max_length` 截断）一致；`SIGTERM` 后进程退出码 0 且不再存活。
