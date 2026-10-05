# 实施交接

## 目标

将本包60个来源已定位的候选逐步构建为THENAME可采集、验证和回放的GPU任务。优先完成README中的pilot，形成不同资源形态后再扩展。不要只按六组各十题并行复制目录。

## 每题实施顺序

1. 读取task card及其具体source unit；固定源码/model/data/评价器版本。来源页面核查是实现入口，源码实际运行还需完成。
2. 准备debug输入及完整获取配方，填写asset manifest、许可/访问状态、对象哈希、split与selection IDs。
3. 跑源参考流程，确认GPU路径、原输出和源码所支持的能力；继承测试不能代替正式产物oracle。
4. 编写任务环境与薄adapter：初始化、逻辑句柄、结果出口、状态查询。允许一个官方CLI或薄adapter完成真实工作；它必须实际执行声明的计算并交付产物，不能直接返回参考答案、仅包装评分器，或把主要GPU工作移到grader。无需人为增加agent步骤。
5. 实现独立oracle和必要负例（错误输入版本、缺失输出、错ID、无实际状态、错误checkpoint等）；对数值/生成任务校准质量规则。
6. 交付agent任务说明、初态和工具接口，实际采集决策模型的输出/等待与真实工具执行。无需虚构bug、固定调用轮数或额外sleep。
7. 用同一轨迹真实重放，处理GPU异步完成、动态句柄和输入身份；独立验证产物。
8. 运行reference_large，采集完整session画像，填写built/verified/replayed/profiled/resource_admitted状态与证据路径。
9. 冻结manifest后，在已通过能力检查的后端执行；失败、未完成和不支持分别记录。

## 工程组织

六组是目录组织，不等于六张万能镜像。建议共享任务接口、事件日志、数据清单和验证设施，按依赖兼容性拆环境。模型加载器、框架、编解码器和科学软件可能需要独立版本。

共享接口应能表示同步作业和后台service/job，返回本轮逻辑句柄与真实状态。文件输出、GPU计算和服务回复都需要明确完成边界。具体字段示例见templates。

## 限定实现范围

首版先支持GPU独占参考、长驻再访问、少量混部场景。GPU共享/抢占由既有后端能力或简单策略提供；本项目不需要新写GPU调度器。应用checkpoint先于GPU-context/VM透明snapshot扩展。

## 校验程序

`python validate_plan.py`检查任务包结构、60个唯一ID、引用、必填设计字段和文档一致性。它不安装依赖、不下载权重、不启动GPU任务，也不把结构通过写成GPU验证成功。

未来进入built/verified/profiled/admitted状态时，补齐相应artifact/evidence字段；校验器允许状态前进，并检查证据，不要求任务永远保持未构建。
