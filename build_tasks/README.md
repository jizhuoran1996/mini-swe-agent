# 60 个源码构建 agent tasks

本目录对应 `sandbox_build_60_source_based_v1.zip`：六组各10题，包含60份任务规格、60套 DeepSeek Flash 实现、源码/依赖锁定信息、容器执行器、独立验收器和本轮结果。原始任务设计保存在 `source_design/`，实际执行的 core 实例见每题 `TASK.md` 和 `input/manifest.json`。

`results.csv` / `results.json` 区分模型已生成实现、接口检查、真实构建与独立验收。只有真实源码构建、非空且通过的官方测试、新容器中的产物消费都通过，才计为 `core_verified`。`doctor` 正确报告缺项并返回78仅算接口检查。Reference 大规模配置本轮未执行，不能由 core 结果推断已通过。

本提交是执行中的检查点；完整容器回归仍在运行，后续结果会继续更新。

## 任务与证据

- `tasks/BUILDv1-*/published/workspace/solution/`：Flash 返回的完整代码，源文件字节保持原样。
- `tasks/BUILDv1-*/TASK.md`：实际绑定的源版本、core 范围、交付物、验收与规模区别。
- `tasks/BUILDv1-*/code_provenance.json`：提供方、模型和代码 SHA256。
- `tasks/BUILDv1-*/recorded_result.json`：本轮最新实现的实际结果；生成代码不等于通过测试。
- `tasks/BUILDv1-*/recorded_runs/`：实际命令、测试清单、原始日志哈希、压缩日志、资源采样与 cgroup 记录。失败尝试也保留。
- `runtime/`：Dockerfile、官方 bootstrap 工具校验和、资源政策。
- `source_design/`：原始60题与196条来源记录；本轮使用的源版本以实例 manifest 为准。

大型源码包、依赖缓存、已构建 SDK 和超过8MiB的压缩日志保存在本地实施目录，未放入 Git。大日志的公开文件明确标注为诊断前缀，同时保留完整归档哈希；不是完整测试日志。公开代码和证据不包含 API key 或模型思考内容。

## 隔离与限制

目标构建均在普通用户 Docker 容器中执行：只读根文件系统、全部 capability 移除、`no-new-privileges`，不挂宿主 home、Docker socket 或 GPU。输入和验收产物只读挂载；工作区使用有容量上限、允许执行的 tmpfs；禁止容器 swap，限制 CPU、内存、PID、单文件大小与运行时间。每条命令日志最多128MiB，超限会终止其进程组，不能算成功。

调度分为大构建、中构建、小构建、依赖准备、验收、接口检查几个串行通道。通常分别限制32/16/12/8/8/2GiB内存；大/中/小工作区分别24/12/8GiB。TensorFlow 依赖分析的准备通道限制16GiB并占用中构建通道，避免二者并行。宿主至少预留32GiB可用内存和50GiB磁盘，越线仅终止本任务的容器。每次实际限额、CPU亲和性和运行镜像 ID 记录在该次证据中，早期尝试可能使用先前的限额。XGBoost 的完整官方 Linux 测试会创建约4096个 C++线程；该实例单独限制8192个PID和128个 OpenMP线程，CPU与内存上限仍为4核、12GiB。

依赖获取在单独联网准备容器中完成，导出源码和缓存，不导出目标程序。每次运行冻结输入清单和只读归档，并保存清单哈希，避免依赖准备影响正在运行的任务。目标构建默认断网。libevent 官方全套测试需要真实外部 DNS 与带地址的网卡，因此该实例声明 bridge 网络；没有替换 DNS、测试期望值或删去失败用例。XGBoost 的完整官方分布式测试同样声明 bridge 网络，以提供真实地址和本地工作进程通信。

## 复现

需要 Linux、Docker、Python3.12、网络获取官方输入，以及足够的独立资源。环境构建同样限制资源，APT/Python实际版本和镜像 ID 另行记录；跨日期重建环境不承诺字节完全一致。

```bash
cd build_tasks
python3 -m pip install -r requirements.txt
python3 validate_bundle.py
python3 prepare_runtime.py
python3 prepare_sources.py BUILDv1-A01
python3 refresh_tasks.py
python3 run.py BUILDv1-A01
python3 grade.py BUILDv1-A01
```

运行前需要把相应源码与依赖物化到 `tasks/<id>/input/`；源码下载、Gitlink 依赖、语言缓存、Bazel仓库和 ONNX Runtime 依赖分别由 `prepare_sources.py`、`prepare_submodules.py`、`prepare_dependencies.py`、`prepare_bazel_dependencies.py`、`prepare_ort_dependencies.py` 准备。Rust 官方完整源包使用 `prepare_rust_source.py`；Ruby 官方 gem、Blender 官方库和 LFS 测试素材、OpenCV 测试素材、JDK 的 jtreg harness 分别由 `prepare_ruby_gems.py`、`prepare_blender_inputs.py`、`prepare_opencv_testdata.py`、`prepare_jtreg.py` 准备。SWC 的固定 nightly 编译器与源码依赖分别锁定，不能用 bootstrap 编译器冒充目标产物。准备器会记录新的归档校验和；组合 tar 包或缓存归档重建的字节可能不同，须保留新实例锁和原始锁的区别。对于本轮仍缺项的任务，先按记录补齐，不能把缺项退出算为构建通过。

若要重新调用 Flash，可运行 `author.py` 或 `repair_batch.py`，通过不回显的 stdin 输入凭证；最多同时3个请求。凭证仅保留在宿主进程内存，不传入任务容器。NumPy和SciPy各有专用的清理镜像，移除对应预装包与预构建wheel，再进行源码构建；早期通用镜像含bootstrap数值包，独立验收使用新提交wheel的隔离环境。仓库中的 `latest_run.json` 初始化为未执行状态，避免把本轮历史结果冒充新一轮完成。
