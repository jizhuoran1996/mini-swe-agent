# GPUv1-D04：生成并执行可复用的数据库查询

input/chinook.sqlite 是完整真实公开 Chinook 示例库，schema.sql 和6个问题只给输入，没有 gold SQL。用CUDA Qwen2.5-Coder-0.5B-Instruct，把schema与问题送入模型，greedy最多256新token，统一提取SQL，保存 raw output/token_ids/SQL。只允许SELECT或WITH只读查询，sqlite连接mode=ro，进度回调限制每条执行<=3秒；危险SQL应拒绝。入口 python solution/main.py run --input input --output output；输出 answers.jsonl（id/sql/results或真实execution_error/raw/token_ids）、run.json；支持 query --database PATH --question TEXT --output JSON 的新问题。不得agent直接写问题答案或gold SQL冒充模型输出，语义错误算任务模型质量。独立检查模型生成、SQL防写入、全覆盖、新查询及独立gold执行对比。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
