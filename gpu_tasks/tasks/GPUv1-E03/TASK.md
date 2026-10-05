# GPUv1-E03：交付可重载的 HIGGS 事件分类模型

为一批真实高能物理事件训练二分类模型，预测事件是否属于 signal。输入来自 UCI HIGGS 原生数据；需要交付模型和验证预测，以便以后处理新的事件。

本实例是 **100K 训练 / 10K 独立验证的小规模真实 GPU 版本**。它使用源文件前 110K 个互异记录，训练为源行 `[0,100000)`，验证为 `[100000,110000)`。这不是原包全 11M 行及其正式 split；不能声称完成 reference-large。

输入只读放在 `input/`：

- `train_features.npy`：(100000,28)，float32。
- `train_labels.npy`：(100000,)，0/1。
- `validation_features.npy`：(10000,28)，float32。没有提供验证标签。
- `manifest.json`：来源、源行范围及数据哈希。

环境为一张 RTX 5090，PyTorch 2.11、NumPy、XGBoost 3.0.5（CUDA 12.8 编译版本）已提供，并且已经在同样隔离环境里验证 CUDA hist 可运行。实际 GPU 测试在受限容器里，最多 24 GiB 主机 RAM、6 CPU、8 GiB 写入工作区、无网络；PyTorch 分配器保留设备余量。使用 `python`，工作目录 `/workspace`。输入、框架目录和根文件系统只读，写源码和产物到 `solution/`、`output/`。

请使用 **XGBoost CUDA histogram** 训练，参数为 `device=cuda:0`、`tree_method=hist`，目标 `binary:logistic`，至少 32 棵树。batch/QuantileDMatrix、深度、学习率等可以自行选择；固定 seed 并记录参数。主训练必须真实在 GPU 上执行，不得改为 CPU 训练后只放一个无用 CUDA tensor。不得读取或搜索验证标签、评价器或容器外主机文件。

实现并实际运行：

```bash
python solution/main.py train --input input --output output
python solution/main.py predict --model output/model.json --features input/validation_features.npy --output output/validation_predictions.npy
```

交付：

1. `solution/main.py`、`solution/README.md` 以及必要源码。支持上面命令。
2. `output/model.json`：可用 XGBoost 标准接口独立重载的完整模型。
3. `output/validation_predictions.npy`：`(10000,)` 的有限概率，范围 `[0,1]`，顺序与验证输入一致；不使用 pickle。
4. `output/training_manifest.json`：实际参数、框架/设备版本、输入哈希、训练行数、树数、同步后的阶段耗时。

评价器会在独立进程中用隐藏验证标签检查 **AUC ≥ 0.65**，并用标准 XGBoost CPU 预测重算同一模型结果（容差 `atol=1e-6, rtol=1e-5`）。随后移走原始输入，只提供你保存的模型和新的真实事件，检查重载预测。只复制初始化模型、常数概率、伪造标签、缓存验证结果或漏掉样本均不通过。

GPU 工作会从宿主采样和独立 profiler 检查，质量与资源强度分别报告。无需人为制造等待、重复记录或占满显存。请完成训练、预测和基本自检，清理后台进程，再给出简短交付说明。
