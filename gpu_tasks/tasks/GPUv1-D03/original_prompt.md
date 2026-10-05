# GPUv1-D03 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

为给定 Python/Java 代码库上下文提供下一行补全，产出逐条补全档案和一个接收上下文的本地接口，使后续请求能继续使用已部署模型。

### 来源和工作范围

LongBench repobench-p test 全 500 条，Qwen/Qwen2.5-Coder-32B-Instruct

### 交付要求

- completions.jsonl
- raw_generations.jsonl
- completion_service_config.json
- service/serve.py 与 service/launcher.json（可启动的模型服务入口）
- service/request_schema.json、response_schema.json 与 model_config.json
- service/service_binding.json（逻辑服务到本轮 endpoint/模型进程/设备的绑定）
- requests/initial.jsonl、requests/continuation.jsonl 与在线响应/完成事件记录

### 必须完成的工作

- 实现输入模板，保持跨文件内容和代码前缀顺序
- 部署 GPU 补全端点，执行全部真实补全并截取约定的下一行结果
- 保留完整原始响应供错误诊断，交付规范化结果
- 交付实际可启动的 repository_completion_service 服务；实现 POST /v1/completions 的请求/响应 schema，并输出本轮逻辑服务绑定。

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

对封存的后续上下文分片继续补全，保持原有记录不被覆盖，并检查更新后接口仍可调用。；具体后续请求来自 requests/continuation.jsonl，在 recorded wait 后通过本轮逻辑服务绑定真实提交并验收。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
