# GPUv1-D08 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

将给定阿拉伯语和印地语语料转为带稳定文档 ID 的语义向量分片，部署查询嵌入接口，并在后续调用中继续处理剩余分片和新查询。

### 来源和工作范围

MIRACL ar 与 hi 全部段落及 dev 查询；Qwen/Qwen3-Embedding-8B，4,096 维输出

### 交付要求

- embeddings/shard-*.safetensors
- row_to_docid.parquet
- query_embeddings.safetensors
- embedding_service_config.json
- service/serve.py 与 service/launcher.json（可启动的模型服务入口）
- service/request_schema.json、response_schema.json 与 model_config.json
- service/service_binding.json（逻辑服务到本轮 endpoint/模型进程/设备的绑定）
- requests/initial.jsonl、requests/continuation.jsonl 与在线响应/完成事件记录

### 必须完成的工作

- 建立文档 ID 到向量行的双向映射
- 对全部实际文本在 GPU 上执行模型前向，分片保存向量
- 部署查询编码接口，输出 dev 查询向量与小型固定检索探针的结果
- 交付实际可启动的 multilingual_embedding_service 服务；实现 POST /v1/embeddings 的请求/响应 schema，并输出本轮逻辑服务绑定。

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

模型保持加载时接收后续查询；对 manifest 预留的语料分片追加编码并更新索引清单，不重新编码已提交分片。；具体后续请求来自 requests/continuation.jsonl，在 recorded wait 后通过本轮逻辑服务绑定真实提交并验收。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
