# GPUv1-D10 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

将英文来源文档翻译成指定八种语言，保持 document_id/segment_id 与段落顺序，交付逐语言翻译文件，并提供可继续处理其他原始段落的本地 GPU 接口。

### 来源和工作范围

google/wmt24pp 的 en-de_DE、en-fr_FR、en-es_MX、en-it_IT、en-ja_JP、en-ko_KR、en-zh_CN、en-ru_RU 全部有效行；CohereLabs/aya-expanse-32b

### 交付要求

- translations/<language>.jsonl
- documents/<language>/*.txt
- segment_manifest.json
- translation_service_config.json

### 必须完成的工作

- 按文档和语言整理来源段落，不跨文档拼接
- 加载多语言模型实际生成各目标语言译文
- 保持逐段对齐、文档顺序与未完成记录，生成按语言分目录的翻译包

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

在模型保留的 session 中处理 manifest 预留的后续文档，更新翻译目录而不覆盖原译文，并对用户指定文档导出整篇文本。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
