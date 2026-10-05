# GPU 轨迹回放与状态契约

## 1. 两种模型调用

THENAME 的 agent 决策模型可以由记录的输出与等待替代。任务中训练、生成、embedding、reranking、视觉推理、科学预测所使用的模型仍必须真实运行。把任务侧推理返回值也从旧轨迹读出，会删除本包要测的 GPU 工作。

采集时允许 agent 检查输入、选择配置、修正并交付；回放时冻结已经选择的工具操作、软件参数、输入与依赖。性能对照中不重新让决策模型选模型、batch 或算法。任务完成不要求固定 tool-call 数量。

## 2. 状态范围

| 状态 | 例子 | 声明与验证 |
|---|---|---|
| GPU resident | 模型权重、KV cache、向量索引、图、优化器状态 | 记录实际设备与持有进程；后续操作使用声明状态 |
| Host resident | tokenizer、数据框、pinned buffer、CPU offload 状态 | 计入任务 host CPU/内存，不隐藏在 driver |
| Writable | checkpoint、生成图像/视频、结果表、索引、仿真轨迹 | 输出与临时数据有清单；语义结果可独立验证 |
| Background | 异步训练、CUDA streams、数据预取、服务请求 | 记录真实完成事件；模型等待期间可以继续工作 |
| External fixture | 受控请求端、只读数据服务、租户命名空间 | 固定初态与重置合同，明确服务端成本与 DUT 成本 |

工具完成、模型等待和 GPU 空闲不是同义词。保留录到的模型等待时，需要继续观察设备、进程和后台活动。对原工作流没有跨轮 GPU 状态的任务，不人为插入空等待；可以和具有自然驻留的任务组成混合负载。

## 3. 逻辑引用与本轮绑定

冻结 manifest 中的逻辑 service、job、model、index、checkpoint 和 output IDs。初始化及实际工具执行返回本轮的 endpoint、端口、句柄、rank、PID 和 GPU UUID/MIG UUID 映射。命令优先通过配置/环境和逻辑引用取得本轮值，不复用上次的端口、旧请求 ID 或过期 URL。

绑定只解析实体引用；不会根据运行结果重新选择算法、语义分支或训练配方。若源轨迹依赖真实输出决定下一步，应使用已经表达该依赖的脚本/任务程序，或者声明该轨迹不支持当前固定回放模式；不能用任意字符串替换掩盖执行差异。

## 4. 完成与数字结果

根据真实 CUDA/event、服务请求结果和产物完成信号建立依赖。训练 checkpoint 要达到完整可加载状态，输出文件完成 close 并满足任务声明的持久性要求。不要把任务 accepted 或 kernel launch 返回当作 GPU 完成，也不要把轮询频率当成新任务。

冻结随机种子、解码规则、模型精度、软件版本和评价器。数值训练、生成式媒体、近似 ANN 与并行模拟可能存在非字节一致结果；分别定义输入身份、产物结构、任务质量和继续使用的判定。压缩图像/视频、浮点文本和 checkpoint 文件不要求跨后端逐字节相同。

## 5. GPU 状态恢复能力

应用 checkpoint（保存/加载模型或仿真状态）、CPU offload、进程级 GPU checkpoint、VM/sandbox snapshot 是不同能力。普通 CPU 内存快照不自动保留 GPU context、设备显存、通信器或连接。控制层只在声明支持并通过状态校验的后端启用相应模式。

首版可以比较保留活服务与应用重载的成本，二者各有明确初态和策略标签。需要透明恢复时，后续任务必须实际访问状态并验结果；只返回 ready 不足以确认恢复。

## 6. 记录的最小事件

planned_arrival、admission、sandbox_ready、model_load_begin/end、tool_submit/start/complete、device_work_complete、artifact_available、model_wait_begin/end、background_job_complete、checkpoint/restore request/complete、first_useful_result_after_resume、cancel、release_begin/end。

事件使用运行内单调时钟，跨主机同时保存时钟对齐方法；不通过两个未校准主机的时间戳直接相减。结果保留所有已提交 session 的有效完成、失败和未完成状态。
