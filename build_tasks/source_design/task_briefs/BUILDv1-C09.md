# BUILDv1-C09 · 构建栅格与矢量数据开发发行包

Build a raster and vector geospatial development distribution

**主工程**：[GDAL](https://github.com/OSGeo/gdal)  
**组别**：多媒体、图形与地理计算工程　**规划规模**：大型　**实施优先级**：standard

**语言**：C；C++；Python  
**构建系统**：CMake；Ninja；SWIG  
**Canonical goal**：`engineering.build_install_test.gdal.linux_cpu`

## Agent 任务目标

为地理数据处理工具交付支持指定本地栅格与矢量格式的 GDAL SDK、CLI 和 Python bindings，并验证坐标、数据读写和安装后的开发接口。

## 官方工作流与派生方式

GDAL CMake 指定驱动构建、C++ test-unit 和 Python autotest 流程。

## 初始环境

- 已冻结的目标源码、声明的离线依赖和工具链；目标工程没有预编译产物、对象文件或对象缓存。
- SRC_ROOT、BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为实例内独立路径；默认完整干净构建。

## 需要完成的工作

- 明确 GTiff/COG/VRT/MEM/GeoJSON/Shapefile 及 SQLite/GeoPackage 等目标驱动。
- 构建 libgdal、CLI、Python bindings 与 C++ tests，安装后完成外部数据 consumer。

## 目标范围

本地 GeoTIFF/COG/VRT、GeoJSON/Shapefile/SQLite/GeoPackage 和坐标变换；不要求外部数据库、云对象服务或 proprietary drivers。

## 构建与测试入口

### Configure / Generate

```bash
cmake -S "$SRC_ROOT" -B "$BUILD_ROOT" -G Ninja -DCMAKE_INSTALL_PREFIX="$INSTALL_ROOT" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DBUILD_PYTHON_BINDINGS=ON -DGDAL_BUILD_OPTIONAL_DRIVERS=OFF -DOGR_BUILD_OPTIONAL_DRIVERS=OFF -DOGR_ENABLE_DRIVER_SQLITE=ON -DOGR_ENABLE_DRIVER_GPKG=ON -DGDAL_DOWNLOAD_TEST_DATA=OFF -DGDAL_SLOW_TESTS=OFF
```

- 为目标格式加入必要 driver flags，配置 Python/SWIG 和 PROJ 数据；本地固定网格，关闭 PROJ 网络获取。

- 检查生成的 pytest.ini，并冻结 GDAL_DOWNLOAD_TEST_DATA/GDAL_RUN_SLOW_TESTS 运行期环境；不继承宿主的启用下载/慢测试配置。

### Build

```bash
cmake --build "$BUILD_ROOT" --parallel "$BUILD_JOBS"
```

### Package / Install

```bash
cmake --build "$BUILD_ROOT" --target install
```

- 归档 libgdal、CLI、头文件、GDAL CMake package、Python bindings 与数据资源。

### Official Tests

```bash
ctest --test-dir "$BUILD_ROOT" -R "^(test-unit|autotest_alg|autotest_osr)$" --output-on-failure
```

- 使用官方 development 环境和生成的 pytest.ini，执行 autotest/gcore/vrt_read.py。

- reference 增加目标栅格/矢量驱动对应的固定本地 Python test files；网络/数据库服务测试不混入此范围。

## 官方测试选择

- **selectors**：test-unit；autotest_alg；autotest_osr；autotest/gcore/vrt_read.py
- **driver_policy**：所需 optional-driver 测试必须匹配实际驱动清单和数据；冻结目标文件/节点，记录 skipped 原因。
- **rationale**：同时验证 C++ API、栅格算法、空间参考及真实文件格式；不能误用系统 Python GDAL。

## 独立消费者验收

- 在外部目录通过 GDAL::GDAL CMake target 编译 consumer，读取已知栅格、裁剪或变换并写成 GeoTIFF/COG。
- 另建干净 Python consumer 环境只加载本轮 osgeo bindings，核对空间参考、geotransform、像元 checksum 和矢量要素数。

## 交付物

- GDAL SDK/CLI/Python 安装包
- 驱动/PROJ/依赖清单
- C++ 与 Python 测试报告
- 独立 consumer 和地理数据产物

## 后续使用

从上轮产生的数据建立新 VRT 或 GeoPackage 并重新打开，验证工作空间和本轮格式驱动持续可用。

## 可选增量变化

- **enabled**：True
- **type**：optional_driver_enablement
- **delta**：启用源码文档支持的 JP2OPENJPEG 驱动，使用已预置 OpenJPEG 依赖。
- **acceptance**：新驱动显示在实际能力清单，官方 driver tests 和外部数据转换通过；妥善更新缓存选项。

## 同一任务的规模配置

### Core：最小完整交付

不可禁用核心 raster/vector drivers 加 CLI/SDK 和 test-unit/VRT tests。

### Reference：正式参考配置

加入 SQLite/GeoPackage、Python bindings 和所列本地算法/空间参考/driver tests。

### Extended：扩展范围

增加已锁定的 netCDF/HDF5/OpenJPEG 等真实 drivers、其本地测试及开发 consumer。

## 可控变量

- 模块和测试范围随实例冻结；编译并行数 BUILD_JOBS 与测试并行数 TEST_JOBS 独立记录。
- 冷/热依赖缓存、ccache/sccache、优化等级和 clean/incremental 是场景变量，不增加任务 ID。

## 预期资源形态

- compiler_cpu
- linker_memory
- process_fanout
- filesystem_metadata
- build_workspace

## 后端能力要求

- Linux x86_64、声明的 CPU 指令集与 ABI；可在任务私有前缀执行和加载本轮产物。
- 不要求 root、KVM、外网或物理 GPU；特殊测试能力在实例准入时显式检查。

## 离线依赖准备

- 固定 PROJ 数据库/网格、SQLite、TIFF、zlib、SWIG/Python/NumPy/pytest、GTest。
- 预置源码 autotest 数据，GDAL_DOWNLOAD_TEST_DATA=OFF；Python bindings 从本轮源代码构建，禁止系统包替代。
- 锁定并预置该 revision 的 autotest/requirements.txt，另显式包含 pytest-xdist；核对 pytest-env、pytest-xdist 和其他生成 pytest.ini 所需插件版本。

## 回放与状态

- 依赖真实 configure、编译、链接、安装和测试完成事件；不能用记录的退出码或日志替代执行。
- 完整保留构建树、生成文件、测试临时目录和进程状态；退出码、测试结果及未完成工作都记录。
- GDAL driver cache、测试数据目录和 PROJ grid 搜索路径绑定本轮配置；不在回放中改变坐标数据源。

## 最终 oracle

- 独立核验源码标识、目标功能、安装清单及本轮构建来源。
- 报告测试发现/选择/实际执行/跳过/失败数；空套件或缺失强制测试不通过。
- 在源码树之外的干净 consumer 目录只使用本轮安装产物完成验收，排除系统预装版本。

## 应拒绝的负例

- 复制系统预装二进制冒充本轮构建。
- 修改筛选器使测试数为零或以大范围 skip 隐藏缺失功能。
- 安装包遗漏运行所需的动态库、插件、资源或开发文件。

## Builder 实施工作

- 固定可执行源码 revision、工具链和全部依赖摘要。
- 实现安装产物来源检查、非空测试清单和独立 consumer 验证器。
- 完成一次真实构建与回放，测量资源画像后确定资源规模标签。

## 源码血缘

- GDAL

## 与已有任务的关系

可能与现有 I/O 数据转换任务共享 GDAL 来源；此处增加源码编译、driver 功能与安装 API 验证。

## 范围说明

- 规模等级为设计预估；当前未构建或实测耗时、内存、I/O 与进程数量。

## 官方来源

- [C_GDAL_BUILD] [Building GDAL from source](https://gdal.org/en/stable/development/building_from_source.html) — 检查位置：CMake build/install; optional driver selection; install prefix
- [C_GDAL_TESTS] [GDAL automated testing](https://gdal.org/en/stable/development/testing.html) — 检查位置：CTest, pytest file selectors, development environment and C++ tests
- [C_GDAL_AUTOTEST] [GDAL autotest CMake registration](https://github.com/OSGeo/gdal/blob/master/autotest/CMakeLists.txt) — 检查位置：autotest/CMakeLists.txt: active GDAL_DOWNLOAD_TEST_DATA and GDAL_SLOW_TESTS conditions, CTest registration; old AUTOTEST options are commented out
- [C_GDAL_CPP] [GDAL C++ unit-test registration](https://github.com/OSGeo/gdal/blob/master/autotest/cpp/CMakeLists.txt) — 检查位置：gdal_unit_test and register_test(test-unit ...)
- [C_GDAL_SWIG] [GDAL SWIG bindings build](https://github.com/OSGeo/gdal/blob/master/swig/CMakeLists.txt) — 检查位置：BUILD_PYTHON_BINDINGS and python subdirectory
- [C_GDAL_PYTEST_TEMPLATE] [GDAL generated pytest configuration](https://github.com/OSGeo/gdal/blob/master/cmake/template/pytest.ini.in) — 检查位置：env configuration and addopts --strict-markers --dist=loadgroup
- [C_GDAL_REQUIREMENTS] [GDAL autotest requirements](https://github.com/OSGeo/gdal/blob/master/autotest/requirements.txt) — 检查位置：Python testing dependency list

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
