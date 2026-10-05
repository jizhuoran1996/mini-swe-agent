# GPUv1-D09 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

接收检索系统为问题提供的候选文档，部署 GPU 重排服务，对每个 query-document 对真实打分，交付排名、分数和可查回的证据文档 ID。

### 来源和工作范围

BEIR nq test 全 3,452 查询；从全 2.68M 语料冻结的每题 top-100 BM25 候选；Qwen3-Reranker-8B

### 交付要求

- pair_scores.parquet
- ranked_evidence.jsonl
- candidate_manifest.json
- rerank_service_config.json
- service/serve.py 与 service/launcher.json（可启动的模型服务入口）
- service/request_schema.json、response_schema.json 与 model_config.json
- service/service_binding.json（逻辑服务到本轮 endpoint/模型进程/设备的绑定）
- requests/initial.jsonl、requests/continuation.jsonl 与在线响应/完成事件记录

### 必须完成的工作

- 检查候选来自声明语料且没有重复 ID
- 逐对执行 GPU 联合编码与分数计算，对每个查询稳定排序
- 保存全部候选分数与 top-k 证据列表，并保留服务供后续查询
- 交付实际可启动的 evidence_reranking_service 服务；实现 POST /v1/rerank 的请求/响应 schema，并输出本轮逻辑服务绑定。

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

使用同一服务处理后续查询分片，保留此前候选与排名文件并提交新增结果。；具体后续请求来自 requests/continuation.jsonl，在 recorded wait 后通过本轮逻辑服务绑定真实提交并验收。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
