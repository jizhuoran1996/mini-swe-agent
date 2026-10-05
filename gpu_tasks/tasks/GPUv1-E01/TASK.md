# GPUv1-E01：交付可继续查询的业务分析结果与设备数据集

input/lineitem.npy为官方TPC-H dbgen SF0.1原生行，float64列[quantity,extendedprice,discount,tax,shipdate_days_since1970,ASCII_returnflag,ASCII_linestatus]。CUDA float64完整查询Q1：shipdate<=1998-09-02，按returnflag/linestatus排序group，输出sum_qty/sum_base_price/sum_disc_price/sum_charge/avg_qty/avg_price/avg_disc/count；Q6: shipdate>=1994-01-01且<1995-01-01、discount在[.05,.07]、quantity<24求sum(extendedprice*discount)。筛选和group归约在CUDA执行。入口 python solution/main.py run --input input --output output；输出queries.json、dataset.npy或等价完整可重载data、state.json、run.json。query --state output --start-date YYYY-MM-DD --end-date YYYY-MM-DD --discount-low F --discount-high F --quantity-limit F --output JSON返回Q6同语义新条件，不能读取原始input或固定常量答案。独立DuckDB/CPU完整重算两个查询及新条件，relative error<=1e-8，实际CUDA归约。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
