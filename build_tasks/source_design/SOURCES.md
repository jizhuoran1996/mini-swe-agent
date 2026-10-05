# 官方来源和检查位置

核查日期：2026-10-05。源码与文档的检查版本逐项记录；可执行实例进一步冻结内容 hash。相同 URL 的多条检查记录不计为不同工程。

## A_ARCHIVE_BUILD · libarchive build instructions

- 发布者：libarchive
- 检查位置：CMake variables and Git checkout build instructions
- 支持内容：ENABLE_TEST, ENABLE_TAR, ENABLE_CPIO, ACL/XATTR options and test/install pathway.
- 检查版本：current-page
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/libarchive/libarchive/wiki/BuildInstructions](https://github.com/libarchive/libarchive/wiki/BuildInstructions)

## A_ARCHIVE_TEST · libarchive CMake regression registration

- 发布者：libarchive
- 检查位置：libarchive_test source list, DISCOVER_TESTS, run_libarchive_test
- 支持内容：Official regression executable, source fixtures, and generated test inventory.
- 检查版本：master
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/libarchive/libarchive/blob/master/libarchive/test/CMakeLists.txt](https://github.com/libarchive/libarchive/blob/master/libarchive/test/CMakeLists.txt)

## A_CURL_BUILD · curl CMake installation guide

- 发布者：curl
- 检查位置：Build options, consumer linking, Useful build targets
- 支持内容：BUILD_TESTING, CURL_USE_OPENSSL, testdeps, tests with TFLAGS, installable libcurl.
- 检查版本：master
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/curl/curl/blob/master/docs/INSTALL-CMAKE.md](https://github.com/curl/curl/blob/master/docs/INSTALL-CMAKE.md)

## A_CURL_CASE · curl HTTP GET fixture

- 发布者：curl
- 检查位置：HTTP keyword, HTTP server, request and response oracle
- 支持内容：Concrete upstream local HTTP functional test.
- 检查版本：master
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/curl/curl/blob/master/tests/data/test1](https://github.com/curl/curl/blob/master/tests/data/test1)

## A_CURL_TEST · curl test harness selection

- 发布者：curl
- 检查位置：enabled/disabled keyword parsing, test selection and result accounting
- 支持内容：Keyword and numeric test selection; local harness produces per-test failures and skips.
- 检查版本：master
- 不可变 revision：null
- 许可/访问：curl license SPDX in source
- 来源：[https://github.com/curl/curl/blob/master/tests/runtests.pl](https://github.com/curl/curl/blob/master/tests/runtests.pl)

## A_EVENT_BUILD · libevent build overview

- 发布者：libevent
- 检查位置：README: CMake Unix and verify
- 支持内容：Official CMake build and verify target.
- 检查版本：master
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/libevent/libevent](https://github.com/libevent/libevent)

## A_EVENT_CMAKE · libevent CMake options and tests

- 发布者：libevent
- 检查位置：EVENT__LIBRARY_TYPE, EVENT__DISABLE_TESTS, EVENT__DISABLE_OPENSSL, verify, install
- 支持内容：Actual shared/static, test and TLS controls; official regression target.
- 检查版本：master
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/libevent/libevent/blob/master/CMakeLists.txt](https://github.com/libevent/libevent/blob/master/CMakeLists.txt)

## A_GIT_CLAR · libgit2 CTest naming helper

- 发布者：libgit2
- 检查位置：ADD_CLAR_TEST function
- 支持内容：CTest registers literal name offline for libgit2_tests.
- 检查版本：main
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/libgit2/libgit2/blob/main/cmake/AddClarTest.cmake](https://github.com/libgit2/libgit2/blob/main/cmake/AddClarTest.cmake)

## A_GIT_CMAKE · libgit2 top-level CMake configuration

- 发布者：libgit2
- 检查位置：BUILD_TESTS, BUILD_CLI, BUILD_EXAMPLES, USE_HTTP and USE_HTTPS
- 支持内容：Explicit build scope and target registration.
- 检查版本：main
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/libgit2/libgit2/blob/main/CMakeLists.txt](https://github.com/libgit2/libgit2/blob/main/CMakeLists.txt)

## A_GIT_README · libgit2 build and feature guide

- 发布者：libgit2
- 检查位置：CMake build, BUILD_EXAMPLES, dependencies and initialization
- 支持内容：Library build and source-consumer integration; HTTPS/SSH are optional features.
- 检查版本：main
- 不可变 revision：null
- 许可/访问：GPLv2 with linking exception stated in README
- 来源：[https://github.com/libgit2/libgit2/blob/main/README.md](https://github.com/libgit2/libgit2/blob/main/README.md)

## A_GIT_TEST · libgit2 offline regression suite

- 发布者：libgit2
- 检查位置：Clar generator, add_clar_test offline/invasive/online
- 支持内容：Offline test suite excludes online; invasive suite kept separate.
- 检查版本：main
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/libgit2/libgit2/blob/main/tests/libgit2/CMakeLists.txt](https://github.com/libgit2/libgit2/blob/main/tests/libgit2/CMakeLists.txt)

## A_NGHTTP_OPTIONS · nghttp2 CMake feature options

- 发布者：nghttp2
- 检查位置：ENABLE_APP, ENABLE_LIB_ONLY, BUILD_STATIC_LIBS, BUILD_TESTING
- 支持内容：BUILD_TESTING depends on BUILD_STATIC_LIBS; explicit app and HTTP/3 capabilities.
- 检查版本：master
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/nghttp2/nghttp2/blob/master/CMakeOptions.txt](https://github.com/nghttp2/nghttp2/blob/master/CMakeOptions.txt)

## A_NGHTTP_README · nghttp2 build and test guide

- 发布者：nghttp2
- 检查位置：Requirements, source build, --enable-app, unit and integration tests
- 支持内容：Library and app scopes, C++23 toolchain for current applications and make check.
- 检查版本：master
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/nghttp2/nghttp2/blob/master/README.rst](https://github.com/nghttp2/nghttp2/blob/master/README.rst)

## A_NGHTTP_TEST · nghttp2 CMake unit tests

- 发布者：nghttp2
- 检查位置：main, failmalloc, add_dependencies(check)
- 支持内容：Concrete CTest names and EXCLUDE_FROM_ALL test build dependencies.
- 检查版本：master
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/nghttp2/nghttp2/blob/master/tests/CMakeLists.txt](https://github.com/nghttp2/nghttp2/blob/master/tests/CMakeLists.txt)

## A_OPENSSL_BUILD · OpenSSL installation guide

- 发布者：openssl
- 检查位置：Configure, Out of Tree Builds, build_sw, install_sw, prefix and openssldir
- 支持内容：Complete native software build and private installation.
- 检查版本：master
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/openssl/openssl/blob/master/INSTALL.md](https://github.com/openssl/openssl/blob/master/INSTALL.md)

## A_OPENSSL_INSTALL_TARGETS · OpenSSL Unix installation targets

- 发布者：OpenSSL
- 检查位置：install_sw and install_ssldirs targets
- 支持内容：install_sw 安装软件，install_ssldirs 安装配置目录和 openssl.cnf。
- 检查版本：current main/master inspected for this design
- 不可变 revision：null
- 许可/访问：Public upstream source; exact terms frozen with the instance
- 来源：[https://github.com/openssl/openssl/blob/master/Configurations/unix-Makefile.tmpl](https://github.com/openssl/openssl/blob/master/Configurations/unix-Makefile.tmpl)

## A_OPENSSL_TEST · OpenSSL test guide

- 发布者：openssl
- 检查位置：Running Selected Tests / list-tests / TESTS / HARNESS_JOBS
- 支持内容：Official test recipe discovery, selected groups, full tests, unprivileged test requirement.
- 检查版本：master
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/openssl/openssl/blob/master/test/README.md](https://github.com/openssl/openssl/blob/master/test/README.md)

## A_PCRE_BUILD · PCRE2 non-Autotools build guide

- 发布者：PCRE2Project
- 检查位置：CMake tests and Python runner section
- 支持内容：CMake / CTest and RunTest / RunGrepTest fixture execution.
- 检查版本：main
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/PCRE2Project/pcre2/blob/main/NON-AUTOTOOLS-BUILD](https://github.com/PCRE2Project/pcre2/blob/main/NON-AUTOTOOLS-BUILD)

## A_PCRE_CMAKE · PCRE2 character widths and test targets

- 发布者：PCRE2Project
- 检查位置：PCRE2_BUILD_PCRE2_8/16/32, PCRE2_SUPPORT_JIT and add_test
- 支持内容：Three widths, JIT, pcre2_test, pcre2_grep_test, pcre2_jit_test and POSIX test.
- 检查版本：main
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/PCRE2Project/pcre2/blob/main/CMakeLists.txt](https://github.com/PCRE2Project/pcre2/blob/main/CMakeLists.txt)

## A_PCRE_README · PCRE2 quickstart and consumer API

- 发布者：PCRE2Project
- 检查位置：Quickstart / pcre2_compile consumer / JIT submodule
- 支持内容：Source build, JIT requirements and matching API.
- 检查版本：main
- 不可变 revision：null
- 许可/访问：BSD 3-clause with PCRE2 Exception stated in README
- 来源：[https://github.com/PCRE2Project/pcre2/blob/main/README.md](https://github.com/PCRE2Project/pcre2/blob/main/README.md)

## A_UV_README · libuv build and test instructions

- 发布者：libuv
- 检查位置：Build Instructions / Running tests / Run one test
- 支持内容：BUILD_TESTING, CTest and uv_run_tests_a TEST_NAME; timeout controls.
- 检查版本：v1.x
- 不可变 revision：null
- 许可/访问：MIT library license and separate documentation license stated in README
- 来源：[https://github.com/libuv/libuv/blob/v1.x/README.md](https://github.com/libuv/libuv/blob/v1.x/README.md)

## A_UV_TESTLIST · libuv registered tests

- 发布者：libuv
- 检查位置：timer, spawn, fs_event, threadpool, TCP and poll entries
- 支持内容：Concrete local OS interaction test names with helpers and platform guards.
- 检查版本：v1.x
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/libuv/libuv/blob/v1.x/test/test-list.h](https://github.com/libuv/libuv/blob/v1.x/test/test-list.h)

## A_ZLIB_CONFIG · zlib configure switches

- 发布者：madler
- 检查位置：option parser: --prefix, --static, --64, --zprefix
- 支持内容：Unprivileged prefix and supported feature configuration.
- 检查版本：develop
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/madler/zlib/blob/develop/configure](https://github.com/madler/zlib/blob/develop/configure)

## A_ZLIB_MAKE · zlib Makefile targets

- 发布者：madler
- 检查位置：all, static, shared, teststatic, testshared, test64, install
- 支持内容：Static/shared library outputs and official checks.
- 检查版本：develop
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/madler/zlib/blob/develop/Makefile.in](https://github.com/madler/zlib/blob/develop/Makefile.in)

## A_ZLIB_README · zlib build overview

- 发布者：madler
- 检查位置：README: Unix build, examples and license
- 支持内容：Official configure / make test / make install; complete library and example programs.
- 检查版本：develop
- 不可变 revision：null
- 许可/访问：zlib license stated in README; preserve pinned notice
- 来源：[https://github.com/madler/zlib](https://github.com/madler/zlib)

## A_ZSTD_README · Zstandard build instructions

- 发布者：facebook
- 检查位置：Build instructions / Makefile / Testing
- 支持内容：make builds libzstd and CLI; make install/check and staged installation.
- 检查版本：dev
- 不可变 revision：null
- 许可/访问：BSD or GPLv2 dual license stated in README
- 来源：[https://github.com/facebook/zstd/blob/dev/README.md](https://github.com/facebook/zstd/blob/dev/README.md)

## A_ZSTD_TESTDOC · Zstandard testing organization

- 发布者：facebook
- 检查位置：Short, medium and long tests
- 支持内容：Official test families; runtime fuzz durations differ from compiling the project.
- 检查版本：dev
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/facebook/zstd/blob/dev/TESTING.md](https://github.com/facebook/zstd/blob/dev/TESTING.md)

## A_ZSTD_TESTMAKE · Zstandard concrete regression targets

- 发布者：facebook
- 检查位置：check, test-cli-tests, test-invalidDictionaries, test-legacy, test-pool, test-zstream, test-fuzzer
- 支持内容：Separately selectable CLI, dictionary, legacy, pool and streaming checks.
- 检查版本：dev
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/facebook/zstd/blob/dev/tests/Makefile](https://github.com/facebook/zstd/blob/dev/tests/Makefile)

## B_BINUTILS_HOME · GNU Binutils

- 发布者：GNU Binutils / Sourceware
- 检查位置：Tool descriptions and obtaining source
- 支持内容：binutils、gas、ld 的项目范围和官方源码入口
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：公开可读的官方文档或上游源码；锁定 revision 的许可和依赖再分发声明 needs_verification
- 来源：[https://sourceware.org/binutils/](https://sourceware.org/binutils/)

## B_BINUTILS_WORKFLOW · Lightning talk notes on binutils

- 发布者：Binutils developer mailing list / Fangrui Song
- 检查位置：Build; Test
- 支持内容：out-of-tree configure、关闭 gdb、all-* 与 check-binutils/check-gas/check-ld
- 检查版本：developer message, January 2021; exact locked release requires target revalidation
- 不可变 revision：null
- 许可/访问：公开可读的官方文档或上游源码；锁定 revision 的许可和依赖再分发声明 needs_verification
- 来源：[https://sourceware.org/pipermail/binutils/2021-January/115029.html](https://sourceware.org/pipermail/binutils/2021-January/115029.html)

## B_GCC_BUILD · Installing GCC: Building

- 发布者：GNU GCC
- 检查位置：Building a native compiler
- 支持内容：默认三阶段 bootstrap；--disable-bootstrap 的不同语义
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：公开可读的官方文档或上游源码；锁定 revision 的许可和依赖再分发声明 needs_verification
- 来源：[https://gcc.gnu.org/install/build.html](https://gcc.gnu.org/install/build.html)

## B_GCC_CONFIG · Installing GCC: Configuration

- 发布者：GNU GCC
- 检查位置：--enable-languages; --disable-multilib; installation prefix
- 支持内容：本机构建语言、ABI 范围和安装前缀配置
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：公开可读的官方文档或上游源码；锁定 revision 的许可和依赖再分发声明 needs_verification
- 来源：[https://gcc.gnu.org/install/configure.html](https://gcc.gnu.org/install/configure.html)

## B_GCC_TEST · Installing GCC: Testing

- 发布者：GNU GCC
- 检查位置：Running the testsuite; selective tests; RUNTESTFLAGS
- 支持内容：DejaGnu、execute.exp、dg.exp 与语言测试选择
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：公开可读的官方文档或上游源码；锁定 revision 的许可和依赖再分发声明 needs_verification
- 来源：[https://gcc.gnu.org/install/test.html](https://gcc.gnu.org/install/test.html)

## B_GO_BUILD · Installing Go from source

- 发布者：Go project
- 检查位置：Bootstrap toolchain; Install Go; Testing; environment variables
- 支持内容：make.bash/all.bash、GOROOT_BOOTSTRAP 和本机构建
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：公开可读的官方文档或上游源码；锁定 revision 的许可和依赖再分发声明 needs_verification
- 来源：[https://go.dev/doc/install/source](https://go.dev/doc/install/source)

## B_GO_RUN · Go src/run.bash

- 发布者：Go project
- 检查位置：run.bash body
- 支持内容：已构建 Go 工具链运行官方测试的入口
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：公开可读的官方文档或上游源码；锁定 revision 的许可和依赖再分发声明 needs_verification
- 来源：[https://go.dev/src/run.bash](https://go.dev/src/run.bash)

## B_GO_TEST · Go command: Test packages

- 发布者：Go project
- 检查位置：Test packages; Testing flags
- 支持内容：go test -json；-count=1 关闭已成功测试的复用
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：公开可读的官方文档或上游源码；锁定 revision 的许可和依赖再分发声明 needs_verification
- 来源：[https://pkg.go.dev/cmd/go](https://pkg.go.dev/cmd/go)

## B_JDK_BUILD · Building the JDK

- 发布者：OpenJDK
- 检查位置：TL;DR; boot JDK; Run configure; Running make/tests
- 支持内容：make images、boot JDK、jtreg/gtest 与 JVM 变体
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：公开可读的官方文档或上游源码；锁定 revision 的许可和依赖再分发声明 needs_verification
- 来源：[https://github.com/openjdk/jdk/blob/master/doc/building.md](https://github.com/openjdk/jdk/blob/master/doc/building.md)

## B_JDK_TEST · Testing the JDK

- 发布者：OpenJDK
- 检查位置：Configuration; TEST selection; JTReg; test tiers
- 支持内容：TEST=jdk_lang、明确目录测试、tier1 与非交互 failure-handler 配置
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：公开可读的官方文档或上游源码；锁定 revision 的许可和依赖再分发声明 needs_verification
- 来源：[https://github.com/openjdk/jdk/blob/master/doc/testing.md](https://github.com/openjdk/jdk/blob/master/doc/testing.md)

## B_LLVM_BUILD · Getting Started with LLVM

- 发布者：LLVM
- 检查位置：Getting the Source Code and Building LLVM; CMake options; install and check-subproject targets
- 支持内容：LLVM_ENABLE_PROJECTS/TARGETS_TO_BUILD、CMake/Ninja 构建与 install
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：公开可读的官方文档或上游源码；锁定 revision 的许可和依赖再分发声明 needs_verification
- 来源：[https://llvm.org/docs/GettingStarted.html](https://llvm.org/docs/GettingStarted.html)

## B_LLVM_TEST · LLVM Testing Infrastructure Guide

- 发布者：LLVM
- 检查位置：Unit and Regression tests
- 支持内容：check-llvm-unit、check-llvm 与 lit 测试结构
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：公开可读的官方文档或上游源码；锁定 revision 的许可和依赖再分发声明 needs_verification
- 来源：[https://llvm.org/docs/TestingGuide.html](https://llvm.org/docs/TestingGuide.html)

## B_NODE_BUILD · Building Node.js

- 发布者：Node.js
- 检查位置：Unix build/install/test; ICU options; Temporal support
- 支持内容：configure/make/install、子系统与目录测试、本地 ICU、Temporal 依赖
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：公开可读的官方文档或上游源码；锁定 revision 的许可和依赖再分发声明 needs_verification
- 来源：[https://github.com/nodejs/node/blob/main/BUILDING.md](https://github.com/nodejs/node/blob/main/BUILDING.md)

## B_NODE_CONFIG · Node.js configure.py

- 发布者：Node.js
- 检查位置：--prefix and Intl/Temporal configuration parser
- 支持内容：安装前缀及功能配置入口
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：公开可读的官方文档或上游源码；锁定 revision 的许可和依赖再分发声明 needs_verification
- 来源：[https://github.com/nodejs/node/blob/main/configure.py](https://github.com/nodejs/node/blob/main/configure.py)

## B_PHP_BUILD · PHP source README

- 发布者：PHP
- 检查位置：Building PHP source code; Testing PHP source code; Installing PHP built from source
- 支持内容：buildconf/configure/make/install、默认依赖及 TESTS 目录选择
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：公开可读的官方文档或上游源码；锁定 revision 的许可和依赖再分发声明 needs_verification
- 来源：[https://github.com/php/php-src](https://github.com/php/php-src)

## B_PHP_SQLITE · PHP PDO SQLite build configuration

- 发布者：PHP
- 检查位置：PDO SQLite option and SQLite dependency checks
- 支持内容：pdo_sqlite 的构建功能与外部 SQLite 依赖
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：公开可读的官方文档或上游源码；锁定 revision 的许可和依赖再分发声明 needs_verification
- 来源：[https://github.com/php/php-src/blob/master/ext/pdo_sqlite/config.m4](https://github.com/php/php-src/blob/master/ext/pdo_sqlite/config.m4)

## B_PYTHON_BUILD · CPython setup and building

- 发布者：Python Developer's Guide
- 检查位置：Unix build; build dependencies
- 支持内容：configure、make、源码构建依赖
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：公开可读的官方文档或上游源码；锁定 revision 的许可和依赖再分发声明 needs_verification
- 来源：[https://devguide.python.org/getting-started/setup-building/](https://devguide.python.org/getting-started/setup-building/)

## B_PYTHON_README · CPython README

- 发布者：Python / CPython
- 检查位置：Build instructions; Testing; Installing multiple versions
- 支持内容：独立构建、make install/altinstall、默认资源受限测试
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：公开可读的官方文档或上游源码；锁定 revision 的许可和依赖再分发声明 needs_verification
- 来源：[https://github.com/python/cpython/blob/main/README.rst](https://github.com/python/cpython/blob/main/README.rst)

## B_PYTHON_TEST · Running and writing CPython tests

- 发布者：Python Developer's Guide
- 检查位置：Running tests; selecting tests; parallel tests
- 支持内容：构建出的 python -m test 接口与显式测试选择
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：公开可读的官方文档或上游源码；锁定 revision 的许可和依赖再分发声明 needs_verification
- 来源：[https://devguide.python.org/testing/run-write-tests/](https://devguide.python.org/testing/run-write-tests/)

## B_RUBY_BUILD · Building Ruby

- 发布者：Ruby
- 检查位置：Quick start; dependencies; out-of-tree build and installation
- 支持内容：autogen.sh、configure、make/install 和 Ruby 扩展依赖
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：公开可读的官方文档或上游源码；锁定 revision 的许可和依赖再分发声明 needs_verification
- 来源：[https://docs.ruby-lang.org/en/master/contributing/building_ruby_md.html](https://docs.ruby-lang.org/en/master/contributing/building_ruby_md.html)

## B_RUBY_TEST · Testing Ruby

- 发布者：Ruby
- 检查位置：Test suites 1–3; TESTS and SPECOPTS
- 支持内容：bootstrap、test-all、test-spec 及目录级选择
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：公开可读的官方文档或上游源码；锁定 revision 的许可和依赖再分发声明 needs_verification
- 来源：[https://docs.ruby-lang.org/en/master/contributing/testing_ruby_md.html](https://docs.ruby-lang.org/en/master/contributing/testing_ruby_md.html)

## B_RUST_BUILD · How to build and run rustc

- 发布者：Rust project
- 检查位置：bootstrap.toml; stage builds; specific components
- 支持内容：真实 rustc/std 构建、stage 与主机工具链路径
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：公开可读的官方文档或上游源码；锁定 revision 的许可和依赖再分发声明 needs_verification
- 来源：[https://rustc-dev-guide.rust-lang.org/building/how-to-build-and-run.html](https://rustc-dev-guide.rust-lang.org/building/how-to-build-and-run.html)

## B_RUST_CONFIG · Rust bootstrap.example.toml

- 发布者：Rust project
- 检查位置：rust.download-rustc; LLVM build options; install settings
- 支持内容：禁止目标编译器下载、固定 bootstrap/LLVM/安装配置
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：公开可读的官方文档或上游源码；锁定 revision 的许可和依赖再分发声明 needs_verification
- 来源：[https://github.com/rust-lang/rust/blob/main/bootstrap.example.toml](https://github.com/rust-lang/rust/blob/main/bootstrap.example.toml)

## B_RUST_INSTALL · Building and installing Rust from source

- 发布者：Rust project
- 检查位置：Build steps; configure and make
- 支持内容：install.prefix、build.extended=false、x.py build/install
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：公开可读的官方文档或上游源码；锁定 revision 的许可和依赖再分发声明 needs_verification
- 来源：[https://github.com/rust-lang/rust/blob/main/INSTALL.md](https://github.com/rust-lang/rust/blob/main/INSTALL.md)

## B_RUST_TEST · Running rustc tests

- 发布者：Rust project
- 检查位置：Running a subset; standard library; force-rerun
- 支持内容：UI 子目录、library/std、测试缓存和 stage 语义
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：公开可读的官方文档或上游源码；锁定 revision 的许可和依赖再分发声明 needs_verification
- 来源：[https://rustc-dev-guide.rust-lang.org/tests/running.html](https://rustc-dev-guide.rust-lang.org/tests/running.html)

## COMMON-BAZEL-CACHE · Bazel remote caching

- 发布者：Official project documentation
- 检查位置：Remote caching overview; Disk cache
- 支持内容：Action/output caching changes actual build execution and is distinct from dependency preparation.
- 检查版本：current official documentation
- 不可变 revision：null
- 许可/访问：Public documentation; redistribution of source/assets resolved per instance
- 来源：[https://bazel.build/remote/caching](https://bazel.build/remote/caching)

## COMMON-BAZEL-DEPS · Bazel external dependencies overview

- 发布者：Official project documentation
- 检查位置：External repositories and dependency handling
- 支持内容：External source and toolchain dependencies need preparation and version control.
- 检查版本：current official documentation
- 不可变 revision：null
- 许可/访问：Public documentation; redistribution of source/assets resolved per instance
- 来源：[https://bazel.build/external/overview](https://bazel.build/external/overview)

## COMMON-CCACHE · ccache manual

- 发布者：Official project documentation
- 检查位置：Description; Statistics; Cache configuration
- 支持内容：Compiler output reuse, cache state and actual cache statistics.
- 检查版本：current official documentation
- 不可变 revision：null
- 许可/访问：Public documentation; redistribution of source/assets resolved per instance
- 来源：[https://ccache.dev/manual/latest.html](https://ccache.dev/manual/latest.html)

## COMMON-CTEST · CTest command-line manual

- 发布者：Official project documentation
- 检查位置：Run Tests; --show-only, --no-tests, --parallel, --output-junit
- 支持内容：Test discovery, nonempty selection checks, parallel test settings and structured reports.
- 检查版本：current official documentation
- 不可变 revision：null
- 许可/访问：Public documentation; redistribution of source/assets resolved per instance
- 来源：[https://cmake.org/cmake/help/latest/manual/ctest.1.html](https://cmake.org/cmake/help/latest/manual/ctest.1.html)

## COMMON-NINJA · The Ninja build system manual

- 发布者：Official project documentation
- 检查位置：Introduction; Running Ninja; Job pools
- 支持内容：Dependency-driven incremental execution and explicit parallel build control.
- 检查版本：current official documentation
- 不可变 revision：null
- 许可/访问：Public documentation; redistribution of source/assets resolved per instance
- 来源：[https://ninja-build.org/manual.html](https://ninja-build.org/manual.html)

## C_BLENDER_CONFIG · Blender CMake options

- 发布者：Blender
- 检查位置：WITH_GTESTS; WITH_CYCLES; device options; CYCLES_TEST_DEVICES
- 支持内容：CPU Cycles, gtests and GPU-test configuration.
- 检查版本：main
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://github.com/blender/blender/blob/main/CMakeLists.txt](https://github.com/blender/blender/blob/main/CMakeLists.txt)

## C_BLENDER_GTEST · Blender C/C++ tests

- 发布者：Blender
- 检查位置：WITH_GTESTS and make test
- 支持内容：Official gtest enabling and CTest integration; indexed official documentation inspected.
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://developer.blender.org/docs/handbook/testing/gtest/](https://developer.blender.org/docs/handbook/testing/gtest/)

## C_BLENDER_HEADLESS · Blender headless CMake preset

- 发布者：Blender
- 检查位置：WITH_HEADLESS and disabled audio/windowing preset
- 支持内容：Official headless preset; direct source inspection, GPL-2.0-or-later SPDX header.
- 检查版本：main
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://github.com/blender/blender/blob/main/build_files/cmake/config/blender_headless.cmake](https://github.com/blender/blender/blob/main/build_files/cmake/config/blender_headless.cmake)

## C_BLENDER_TESTS · Blender Python and render test definitions

- 发布者：Blender
- 检查位置：bmesh_bevel, bmesh_boolean, mesh_join, mesh_validate, blendfile tests; cycles_<group>_<device>
- 支持内容：Concrete non-GUI regression and CPU-render selections.
- 检查版本：main
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://github.com/blender/blender/blob/main/tests/python/CMakeLists.txt](https://github.com/blender/blender/blob/main/tests/python/CMakeLists.txt)

## C_FFMPEG_BUILD · FFmpeg installation instructions

- 发布者：FFmpeg
- 检查位置：INSTALL: out-of-tree configure, make, make install
- 支持内容：Official build and install commands; external libraries are not all enabled by default.
- 检查版本：8.0 documentation
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://www.ffmpeg.org/doxygen/8.0/md_INSTALL.html](https://www.ffmpeg.org/doxygen/8.0/md_INSTALL.html)

## C_FFMPEG_FATE · FFmpeg Automated Testing Environment

- 发布者：FFmpeg
- 检查位置：Using FATE; fate-list, fate, SAMPLES, subset selection
- 支持内容：Frozen local sample directory and official regression-test target discovery.
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://www.ffmpeg.org/fate.html](https://www.ffmpeg.org/fate.html)

## C_FFMPEG_OPTIONS · FFmpeg configure options

- 发布者：FFmpeg
- 检查位置：Configuration and program options; --disable-autodetect, shared/static, ffplay and docs
- 支持内容：Exact CPU-oriented build flags; direct official raw-source inspection.
- 检查版本：master
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://github.com/FFmpeg/FFmpeg/blob/master/configure](https://github.com/FFmpeg/FFmpeg/blob/master/configure)

## C_GDAL_AUTOTEST · GDAL autotest CMake registration

- 发布者：OSGeo GDAL
- 检查位置：autotest/CMakeLists.txt: active GDAL_DOWNLOAD_TEST_DATA and GDAL_SLOW_TESTS conditions, CTest registration; old AUTOTEST options are commented out
- 支持内容：实际有效的下载/慢测试控制与 CTest/pytest 环境生成；应核对运行期 GDAL_DOWNLOAD_TEST_DATA/GDAL_RUN_SLOW_TESTS。
- 检查版本：master
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://github.com/OSGeo/gdal/blob/master/autotest/CMakeLists.txt](https://github.com/OSGeo/gdal/blob/master/autotest/CMakeLists.txt)

## C_GDAL_BUILD · Building GDAL from source

- 发布者：OSGeo GDAL
- 检查位置：CMake build/install; optional driver selection; install prefix
- 支持内容：Concrete minimal/selected driver build and dependency discovery.
- 检查版本：stable documentation
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://gdal.org/en/stable/development/building_from_source.html](https://gdal.org/en/stable/development/building_from_source.html)

## C_GDAL_CPP · GDAL C++ unit-test registration

- 发布者：OSGeo GDAL
- 检查位置：gdal_unit_test and register_test(test-unit ...)
- 支持内容：Exact C++ artifact and test-unit CTest name; GoogleTest prerequisite.
- 检查版本：master
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://github.com/OSGeo/gdal/blob/master/autotest/cpp/CMakeLists.txt](https://github.com/OSGeo/gdal/blob/master/autotest/cpp/CMakeLists.txt)

## C_GDAL_PYTEST_TEMPLATE · GDAL generated pytest configuration

- 发布者：OSGeo / GDAL
- 检查位置：env configuration and addopts --strict-markers --dist=loadgroup
- 支持内容：生成配置需要 pytest-env 与 pytest-xdist，并使用声明的 development 环境。
- 检查版本：master
- 不可变 revision：null
- 许可/访问：Public upstream source; exact redistribution terms locked with the instance
- 来源：[https://github.com/OSGeo/gdal/blob/master/cmake/template/pytest.ini.in](https://github.com/OSGeo/gdal/blob/master/cmake/template/pytest.ini.in)

## C_GDAL_REQUIREMENTS · GDAL autotest requirements

- 发布者：OSGeo / GDAL
- 检查位置：Python testing dependency list
- 支持内容：锁定官方测试依赖，包括 pytest-env、pytest-benchmark 和所选套件的配套依赖。
- 检查版本：master
- 不可变 revision：null
- 许可/访问：Public upstream source; exact redistribution terms locked with the instance
- 来源：[https://github.com/OSGeo/gdal/blob/master/autotest/requirements.txt](https://github.com/OSGeo/gdal/blob/master/autotest/requirements.txt)

## C_GDAL_SWIG · GDAL SWIG bindings build

- 发布者：OSGeo GDAL
- 检查位置：BUILD_PYTHON_BINDINGS and python subdirectory
- 支持内容：Source-built Python bindings for official autotests.
- 检查版本：master
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://github.com/OSGeo/gdal/blob/master/swig/CMakeLists.txt](https://github.com/OSGeo/gdal/blob/master/swig/CMakeLists.txt)

## C_GDAL_TESTS · GDAL automated testing

- 发布者：OSGeo GDAL
- 检查位置：CTest, pytest file selectors, development environment and C++ tests
- 支持内容：Non-empty official local test selection and correct library binding.
- 检查版本：stable documentation
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://gdal.org/en/stable/development/testing.html](https://gdal.org/en/stable/development/testing.html)

## C_GODOT_BUILD · Godot Linux/BSD compilation

- 发布者：Godot Engine
- 检查位置：Editor build, headless run, template_debug/template_release builds
- 支持内容：Exact SCons target forms and CPU headless execution.
- 检查版本：stable documentation
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://docs.godotengine.org/en/stable/engine_details/development/compiling/compiling_for_linuxbsd.html](https://docs.godotengine.org/en/stable/engine_details/development/compiling/compiling_for_linuxbsd.html)

## C_GODOT_CLI · Godot command-line tutorial

- 发布者：Godot Engine
- 检查位置：--headless, --path, --export-release and --test
- 支持内容：Fresh consumer project export/run pathway.
- 检查版本：master
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://github.com/godotengine/godot-docs/blob/master/tutorials/editor/command_line_tutorial.rst](https://github.com/godotengine/godot-docs/blob/master/tutorials/editor/command_line_tutorial.rst)

## C_GODOT_TESTS · Godot unit testing

- 发布者：Godot Engine
- 检查位置：tests=yes; --test; doctest filtering; GDScript integration; mock servers
- 支持内容：Official unit-test selection, result reporters and headless-compatible engine test infrastructure.
- 检查版本：stable documentation
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://docs.godotengine.org/en/stable/engine_details/architecture/unit_testing.html](https://docs.godotengine.org/en/stable/engine_details/architecture/unit_testing.html)

## C_GST_BASE_OPTIONS · GStreamer base plugin options

- 发布者：GStreamer
- 检查位置：app/audio/video/playback and external codec plugin features
- 支持内容：Exact CPU media plugin option names; direct raw-source inspection.
- 检查版本：main
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://github.com/GStreamer/gstreamer/blob/main/subprojects/gst-plugins-base/meson.options](https://github.com/GStreamer/gstreamer/blob/main/subprojects/gst-plugins-base/meson.options)

## C_GST_BASE_TESTS · GStreamer base check tests

- 发布者：GStreamer
- 检查位置：elements/appsink.c, appsrc.c, audioconvert.c, audioresample.c, videoconvert.c; underscorify test naming
- 支持内容：Specific headless unit-test selectors and plugin-specific prerequisites.
- 检查版本：main
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://github.com/GStreamer/gstreamer/blob/main/subprojects/gst-plugins-base/tests/check/meson.build](https://github.com/GStreamer/gstreamer/blob/main/subprojects/gst-plugins-base/tests/check/meson.build)

## C_GST_BUILD · GStreamer monorepo README

- 发布者：GStreamer
- 检查位置：Build GStreamer and its modules; external dependencies; run tests; optional installation
- 支持内容：Meson setup/compile/install and suite/test selectors.
- 检查版本：main
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://github.com/GStreamer/gstreamer/blob/main/README.md](https://github.com/GStreamer/gstreamer/blob/main/README.md)

## C_GST_CORE_OPTIONS · GStreamer core options

- 发布者：GStreamer
- 检查位置：check, ptp-helper, tools/tests and registry options
- 支持内容：Enable test library and disable privileged helper; direct raw-source inspection.
- 检查版本：main
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://github.com/GStreamer/gstreamer/blob/main/subprojects/gstreamer/meson.options](https://github.com/GStreamer/gstreamer/blob/main/subprojects/gstreamer/meson.options)

## C_GST_GOOD_OPTIONS · GStreamer good plugin options

- 发布者：GStreamer
- 检查位置：wavenc/wavparse, matroska, isomp4, jpeg/png and device backends
- 支持内容：Exact container/image plugin names; direct raw-source inspection.
- 检查版本：main
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://github.com/GStreamer/gstreamer/blob/main/subprojects/gst-plugins-good/meson.options](https://github.com/GStreamer/gstreamer/blob/main/subprojects/gst-plugins-good/meson.options)

## C_GST_OPTIONS · GStreamer top-level options

- 发布者：GStreamer
- 检查位置：base/good/bad/ugly, tests/tools and inherited feature options
- 支持内容：Exact monorepo feature controls; direct official raw-source inspection.
- 检查版本：main
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://github.com/GStreamer/gstreamer/blob/main/meson.options](https://github.com/GStreamer/gstreamer/blob/main/meson.options)

## C_IM_BUILD · ImageMagick advanced Linux source installation

- 发布者：ImageMagick
- 检查位置：Configure options; build, install and make check; delegates
- 支持内容：Source build, private prefix, headless setting, installed tests and Ghostscript/Freetype prerequisites.
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://imagemagick.org/advanced-linux-installation/](https://imagemagick.org/advanced-linux-installation/)

## C_IM_INSTALL · ImageMagick source installation

- 发布者：ImageMagick
- 检查位置：Unix source build and make check
- 支持内容：Official primary source/install workflow.
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://imagemagick.org/install-source/](https://imagemagick.org/install-source/)

## C_MESA_BUILD · Mesa compiling and installing

- 发布者：Mesa
- 检查位置：Meson build; local install; llvmpipe/swrast; installed-driver environment
- 支持内容：Actual CPU software drivers and installed artifact use.
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://docs.mesa3d.org/install.html](https://docs.mesa3d.org/install.html)

## C_MESA_LLVMPIPE · Mesa LLVMpipe documentation

- 发布者：Mesa
- 检查位置：Software rasterizer, LLVM requirement and tests
- 支持内容：CPU software rendering rather than physical GPU requirement.
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://docs.mesa3d.org/drivers/llvmpipe.html](https://docs.mesa3d.org/drivers/llvmpipe.html)

## C_MESA_LP_TESTS · LLVMpipe test definitions

- 发布者：Mesa
- 检查位置：lp_test_format, lp_test_arit, lp_test_blend, lp_test_lerp, lp_test_conv, lp_test_printf
- 支持内容：Specific software shader/JIT tests with LLVM dependencies.
- 检查版本：main
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://gitlab.freedesktop.org/mesa/mesa/-/blob/main/src/gallium/drivers/llvmpipe/meson.build](https://gitlab.freedesktop.org/mesa/mesa/-/blob/main/src/gallium/drivers/llvmpipe/meson.build)

## C_MESA_OPTIONS · Mesa Meson options

- 发布者：Mesa
- 检查位置：platforms, gallium-drivers, vulkan-drivers, glx, egl, llvm, build-tests
- 支持内容：Exact software-rendering and unit-test options; official raw-source inspection.
- 检查版本：main
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://gitlab.freedesktop.org/mesa/mesa/-/blob/main/meson.options](https://gitlab.freedesktop.org/mesa/mesa/-/blob/main/meson.options)

## C_MESA_UTIL_TESTS · Mesa utility test definitions

- 发布者：Mesa
- 检查位置：util_tests, process, process_with_overrides and util suite
- 支持内容：Exact CPU-only data-structure/process test targets.
- 检查版本：main
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://gitlab.freedesktop.org/mesa/mesa/-/blob/main/src/util/meson.build](https://gitlab.freedesktop.org/mesa/mesa/-/blob/main/src/util/meson.build)

## C_OPENCV_CONFIG · OpenCV configuration reference

- 发布者：OpenCV
- 检查位置：Build tests and limited modules; downloaded dependencies; CPU/GPU backends
- 支持内容：BUILD_LIST, BUILD_TESTS, OPENCV_DOWNLOAD_PATH and explicit CPU scope.
- 检查版本：4.13.0 documentation
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://docs.opencv.org/4.13.0/db/d05/tutorial_config_reference.html](https://docs.opencv.org/4.13.0/db/d05/tutorial_config_reference.html)

## C_OPENCV_INSTALL · OpenCV Linux installation

- 发布者：OpenCV
- 检查位置：Build/install; opencv_test_core and test-data setup
- 支持内容：Established build/install/test binary invocation form; match options to pinned release.
- 检查版本：4.1.2 documentation
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://docs.opencv.org/4.1.2/d7/d9f/tutorial_linux_install.html](https://docs.opencv.org/4.1.2/d7/d9f/tutorial_linux_install.html)

## C_OPENCV_TESTS · OpenCV quality-assurance guide

- 发布者：OpenCV
- 检查位置：Accuracy tests in modules/<module>/test and OPENCV_TEST_DATA_PATH
- 支持内容：Official module test organization and locked opencv_extra fixtures.
- 检查版本：current wiki
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://github.com/opencv/opencv/wiki/QA_in_OpenCV](https://github.com/opencv/opencv/wiki/QA_in_OpenCV)

## C_VIPS_BUILD · libvips source installation

- 发布者：libvips
- 检查位置：Building libvips from source
- 支持内容：Meson configure/build/test/install and explicit dependencies.
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://www.libvips.org/install.html](https://www.libvips.org/install.html)

## C_VIPS_CI · libvips official CI

- 发布者：libvips
- 检查位置：Configure/build/check/install and test/test-suite invocation
- 支持内容：Extended installed-library Python test route.
- 检查版本：master
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://github.com/libvips/libvips/blob/master/.github/workflows/ci.yml](https://github.com/libvips/libvips/blob/master/.github/workflows/ci.yml)

## C_VIPS_OPTIONS · libvips Meson options

- 发布者：libvips
- 检查位置：tests/tools/cplusplus booleans; introspection and image-format features
- 支持内容：Exact build options and optional codec scope.
- 检查版本：master
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://github.com/libvips/libvips/blob/master/meson_options.txt](https://github.com/libvips/libvips/blob/master/meson_options.txt)

## C_VIPS_TESTS · libvips Meson test definitions

- 发布者：libvips
- 检查位置：script_tests plus token, connections and descriptors tests
- 支持内容：Exact CLI, formats, seq, stall, threading, keep and descriptor test targets.
- 检查版本：master
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://github.com/libvips/libvips/blob/master/test/meson.build](https://github.com/libvips/libvips/blob/master/test/meson.build)

## C_VTK_BUILD · Building VTK

- 发布者：VTK / Kitware
- 检查位置：Sources, optional dependencies, out-of-tree CMake configure/build
- 支持内容：Native SDK build and existing data/module dependencies.
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://docs.vtk.org/en/latest/build_instructions/build.html](https://docs.vtk.org/en/latest/build_instructions/build.html)

## C_VTK_CONFIG · VTK build settings

- 发布者：VTK / Kitware
- 检查位置：VTK_BUILD_TESTING; SDK; EGL/headless; MESA software rendering
- 支持内容：Real CPU headless rendering and selective testing settings.
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://docs.vtk.org/en/latest/build_instructions/build_settings.html](https://docs.vtk.org/en/latest/build_instructions/build_settings.html)

## C_VTK_CORE_TESTS · VTK CommonCore C++ tests

- 发布者：VTK / Kitware
- 检查位置：vtkCommonCoreCxxTests; TestArray*, TestSmartPointer, TestNew
- 支持内容：Specific C++ API and lifetime test targets.
- 检查版本：master
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://github.com/Kitware/VTK/blob/master/Common/Core/Testing/Cxx/CMakeLists.txt](https://github.com/Kitware/VTK/blob/master/Common/Core/Testing/Cxx/CMakeLists.txt)

## C_VTK_FILTER_TESTS · VTK FiltersCore C++ tests

- 发布者：VTK / Kitware
- 检查位置：vtkFiltersCoreCxxTests; TestCleanPolyData*, TestThreshold*
- 支持内容：Specific geometry/filter tests with MPI variants distinguished.
- 检查版本：master
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://github.com/Kitware/VTK/blob/master/Filters/Core/Testing/Cxx/CMakeLists.txt](https://github.com/Kitware/VTK/blob/master/Filters/Core/Testing/Cxx/CMakeLists.txt)

## C_VTK_GL_TESTS · VTK OpenGL2 C++ tests

- 发布者：VTK / Kitware
- 检查位置：TestOffscreenRenderingResize and EGL-gated TestEGLRenderWindowResize
- 支持内容：Concrete software/offscreen renderer verification targets.
- 检查版本：master
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://github.com/Kitware/VTK/blob/master/Rendering/OpenGL2/Testing/Cxx/CMakeLists.txt](https://github.com/Kitware/VTK/blob/master/Rendering/OpenGL2/Testing/Cxx/CMakeLists.txt)

## C_VTK_MODULE_CONFIG · VTK module selection implementation

- 发布者：VTK / Kitware
- 检查位置：vtk_module_scan and VTK_MODULE_ENABLE_/VTK_GROUP_ENABLE_ configuration states
- 支持内容：YES/WANT/DONT_WANT/NO and module-scoped CMake flags; read with CMakePresets.json mini configuration.
- 检查版本：master
- 不可变 revision：null
- 许可/访问：Public official repository; record source and bundled-dependency license files when pinning.
- 来源：[https://github.com/Kitware/VTK/blob/master/CMake/vtkModule.cmake](https://github.com/Kitware/VTK/blob/master/CMake/vtkModule.cmake)

## C_VTK_XML_TESTS · VTK IOXML C++ tests

- 发布者：VTK / Kitware
- 检查位置：vtkIOXMLCxxTests, TestXMLWriteRead and TestXMLCInterface
- 支持内容：Actual serialization and C interface test targets.
- 检查版本：master
- 不可变 revision：null
- 许可/访问：Public official source/documentation; exact pinned source, fixtures and dependency licenses remain to be recorded.
- 来源：[https://github.com/Kitware/VTK/blob/master/IO/XML/Testing/Cxx/CMakeLists.txt](https://github.com/Kitware/VTK/blob/master/IO/XML/Testing/Cxx/CMakeLists.txt)

## D_ARROW_BUILD · Building Arrow C++

- 发布者：Apache Arrow
- 检查位置：Building and running tests; component options; offline dependency builds
- 支持内容：CMake components, make unittest/ctest, install and local third-party sources
- 检查版本：current-page
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://arrow.apache.org/docs/developers/cpp/building.html](https://arrow.apache.org/docs/developers/cpp/building.html)

## D_ARROW_CORE_CMAKE · Arrow C++ test prefix wrapper

- 发布者：Apache Arrow
- 检查位置：ADD_ARROW_TEST function lines 262–290; default prefix arrow and delegation to add_test_case
- 支持内容：Verifies arrow-csv-test default prefix together with BuildUtils hyphen normalization
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://raw.githubusercontent.com/apache/arrow/main/cpp/src/arrow/CMakeLists.txt](https://raw.githubusercontent.com/apache/arrow/main/cpp/src/arrow/CMakeLists.txt)

## D_ARROW_CSV · Arrow CSV test target

- 发布者：Apache Arrow
- 检查位置：add_arrow_test(csv-test) and installed headers
- 支持内容：Compiled CSV parser/writer test target
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://raw.githubusercontent.com/apache/arrow/main/cpp/src/arrow/csv/CMakeLists.txt](https://raw.githubusercontent.com/apache/arrow/main/cpp/src/arrow/csv/CMakeLists.txt)

## D_ARROW_IPC · Arrow IPC test targets

- 发布者：Apache Arrow
- 检查位置：ADD_ARROW_IPC_TEST and read_write_test
- 支持内容：IPC serialization test target and naming
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://raw.githubusercontent.com/apache/arrow/main/cpp/src/arrow/ipc/CMakeLists.txt](https://raw.githubusercontent.com/apache/arrow/main/cpp/src/arrow/ipc/CMakeLists.txt)

## D_ARROW_PARQUET · Arrow Parquet test targets

- 发布者：Apache Arrow
- 检查位置：ADD_PARQUET_TEST and arrow-reader-writer-test
- 支持内容：Parquet/Arrow roundtrip test target
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://raw.githubusercontent.com/apache/arrow/main/cpp/src/parquet/CMakeLists.txt](https://raw.githubusercontent.com/apache/arrow/main/cpp/src/parquet/CMakeLists.txt)

## D_ARROW_TESTUTIL · Arrow test naming and registration

- 发布者：Apache Arrow
- 检查位置：ADD_TEST_CASE, prefix joining, underscore-to-hyphen conversion, unittest label
- 支持内容：CTest target names and test-label registration
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://raw.githubusercontent.com/apache/arrow/main/cpp/cmake_modules/BuildUtils.cmake](https://raw.githubusercontent.com/apache/arrow/main/cpp/cmake_modules/BuildUtils.cmake)

## D_CLICK_BUILD · How to Build ClickHouse on Linux

- 发布者：ClickHouse
- 检查位置：CMake/Ninja build, clickhouse target, Rust option and programs output
- 支持内容：Full monolithic executable build, local binary output and optional Rust disable
- 检查版本：current-page
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://clickhouse.com/docs/resources/develop-contribute/build/build](https://clickhouse.com/docs/resources/develop-contribute/build/build)

## D_CLICK_CMAKE · ClickHouse DBMS unit-test build

- 发布者：ClickHouse
- 检查位置：ENABLE_TESTS; grep_gtest_sources; unit_tests_dbms
- 支持内容：Real aggregated unit-test target and its compile/link dependencies
- 检查版本：master branch
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://raw.githubusercontent.com/ClickHouse/ClickHouse/master/src/CMakeLists.txt](https://raw.githubusercontent.com/ClickHouse/ClickHouse/master/src/CMakeLists.txt)

## D_CLICK_TEST · ClickHouse ColumnObject tests

- 发布者：ClickHouse
- 检查位置：TEST(ColumnObject, ...) cases
- 支持内容：Bounded official ColumnObject.* suite for JSON column behavior
- 检查版本：master branch
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://raw.githubusercontent.com/ClickHouse/ClickHouse/master/src/Columns/tests/gtest_column_object.cpp](https://raw.githubusercontent.com/ClickHouse/ClickHouse/master/src/Columns/tests/gtest_column_object.cpp)

## D_DUCK_BUILD · DuckDB v1.4.3 build wrapper

- 发布者：DuckDB
- 检查位置：release rule, BUILD_EXTENSIONS and CMake wrapper
- 支持内容：Release build and explicit in-tree extension set
- 检查版本：v1.4.3 tag
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://raw.githubusercontent.com/duckdb/duckdb/v1.4.3/Makefile](https://raw.githubusercontent.com/duckdb/duckdb/v1.4.3/Makefile)

## D_DUCK_CMAKE · DuckDB v1.4.3 root CMake build

- 发布者：DuckDB
- 检查位置：BUILD_SHELL, BUILD_UNITTESTS, BUILD_EXTENSIONS and install/export rules
- 支持内容：Compiled shell/library/test targets and installed CMake SDK
- 检查版本：v1.4.3 tag
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://raw.githubusercontent.com/duckdb/duckdb/v1.4.3/CMakeLists.txt](https://raw.githubusercontent.com/duckdb/duckdb/v1.4.3/CMakeLists.txt)

## D_DUCK_TEST · DuckDB C API regression tests

- 发布者：DuckDB
- 检查位置：TEST_CASE entries tagged [capi]
- 支持内容：Existing test selector [capi], configuration, type, error and API cases
- 检查版本：v1.4.3 tag
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://raw.githubusercontent.com/duckdb/duckdb/v1.4.3/test/api/capi/test_capi.cpp](https://raw.githubusercontent.com/duckdb/duckdb/v1.4.3/test/api/capi/test_capi.cpp)

## D_ENVOY_BUILD · Envoy Bazel developer guide

- 发布者：Envoy authors
- 检查位置：Building envoy, envoy-static path, individual tests, cached tests and IPv4/IPv6 selection
- 支持内容：Binary build, bounded Bazel tests, toolchain preload, network and sandbox requirements
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://raw.githubusercontent.com/envoyproxy/envoy/main/bazel/README.md](https://raw.githubusercontent.com/envoyproxy/envoy/main/bazel/README.md)

## D_ENVOY_TEST · Envoy HTTP unit-test build targets

- 发布者：Envoy authors
- 检查位置：header_map_impl_test, codec_client_test, async_client_impl_test and utility targets
- 支持内容：Verified official unit-test labels
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://raw.githubusercontent.com/envoyproxy/envoy/main/test/common/http/BUILD](https://raw.githubusercontent.com/envoyproxy/envoy/main/test/common/http/BUILD)

## D_ETCD_ADT · etcd interval-tree tests

- 发布者：etcd authors
- 检查位置：TestIntervalTree* cases
- 支持内容：Existing local data-structure tests for extended package coverage
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://raw.githubusercontent.com/etcd-io/etcd/main/pkg/adt/interval_tree_test.go](https://raw.githubusercontent.com/etcd-io/etcd/main/pkg/adt/interval_tree_test.go)

## D_ETCD_BUILD · etcd build entry point

- 发布者：etcd authors
- 检查位置：run_build etcd_build entrypoint
- 支持内容：Current supported source build script
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://raw.githubusercontent.com/etcd-io/etcd/main/scripts/build.sh](https://raw.githubusercontent.com/etcd-io/etcd/main/scripts/build.sh)

## D_ETCD_BUILDLIB · etcd binary compilation

- 发布者：etcd authors
- 检查位置：etcd_build, server/etcdctl/etcdutl compilation and source stamping
- 支持内容：Three real binary artifacts and module-local compilation
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://raw.githubusercontent.com/etcd-io/etcd/main/scripts/build_lib.sh](https://raw.githubusercontent.com/etcd-io/etcd/main/scripts/build_lib.sh)

## D_ETCD_RUNNER · etcd official test runner

- 发布者：etcd authors
- 检查位置：PASSES=unit and unit_pass; run_for_all_workspace_modules
- 支持内容：Official broader unit-suite extension and package/time limits
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://raw.githubusercontent.com/etcd-io/etcd/main/scripts/test.sh](https://raw.githubusercontent.com/etcd-io/etcd/main/scripts/test.sh)

## D_ETCD_TEST · etcd MVCC unit tests

- 发布者：etcd authors
- 检查位置：TestStoreRev, TestStorePut, TestStoreRange, TestStoreDeleteRange, TestStoreCompact, TestStoreRestore
- 支持内容：Bounded local-backend MVCC unit-test selection
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://raw.githubusercontent.com/etcd-io/etcd/main/server/storage/mvcc/kvstore_test.go](https://raw.githubusercontent.com/etcd-io/etcd/main/server/storage/mvcc/kvstore_test.go)

## D_MARIA_BUILD · Get the code, build it, test it

- 发布者：MariaDB Foundation
- 检查位置：Compile; Testing the server; Starting mariadbd after build
- 支持内容：CMake build/install, MTR syntax, private data directory and local server initialization
- 检查版本：current-page
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://mariadb.org/get-involved/getting-started-for-developers/get-code-build-test/](https://mariadb.org/get-involved/getting-started-for-developers/get-code-build-test/)

## D_MARIA_CMAKE · MariaDB 11.8 CMake build configuration

- 发布者：MariaDB
- 检查位置：WITH_UNIT_TESTS; ENABLE_TESTING; bundled client library build
- 支持内容：Unit-test option and build graph; source branch declared explicitly
- 检查版本：11.8 branch
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://raw.githubusercontent.com/MariaDB/server/11.8/CMakeLists.txt](https://raw.githubusercontent.com/MariaDB/server/11.8/CMakeLists.txt)

## D_MARIA_INSERT · MariaDB insert regression fixture

- 发布者：MariaDB
- 检查位置：main.insert SQL regression, inserts, defaults, keys and old-value references
- 支持内容：Existing bounded MTR test and its SQL semantics
- 检查版本：11.8 branch
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://raw.githubusercontent.com/MariaDB/server/11.8/mysql-test/main/insert.test](https://raw.githubusercontent.com/MariaDB/server/11.8/mysql-test/main/insert.test)

## D_MARIA_SELECT · MariaDB select regression fixture

- 发布者：MariaDB
- 检查位置：main.select SQL regression and required include files
- 支持内容：Existing MTR selection and query regression semantics
- 检查版本：11.8 branch
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://raw.githubusercontent.com/MariaDB/server/11.8/mysql-test/main/select.test](https://raw.githubusercontent.com/MariaDB/server/11.8/mysql-test/main/select.test)

## D_NGINX_BUILD · Building nginx from Sources

- 发布者：NGINX
- 检查位置：configure prefix/builddir; http_ssl, http_v2, stream; make installation
- 支持内容：Source feature selection and unprivileged prefix build
- 检查版本：current-page
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://nginx.org/en/docs/configure.html](https://nginx.org/en/docs/configure.html)

## D_NGINX_PROXY · nginx-tests proxy regression

- 发布者：NGINX
- 检查位置：http/proxy feature prerequisites and 28-test TAP plan
- 支持内容：Bounded official local proxy test
- 检查版本：master branch
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://raw.githubusercontent.com/nginx/nginx-tests/master/proxy.t](https://raw.githubusercontent.com/nginx/nginx-tests/master/proxy.t)

## D_NGINX_RUNNER · nginx-tests usage

- 发布者：NGINX
- 检查位置：TEST_NGINX_BINARY, prove, ports 8000..8999, module path
- 支持内容：Official test runner and local port requirements
- 检查版本：master branch
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://raw.githubusercontent.com/nginx/nginx-tests/master/README](https://raw.githubusercontent.com/nginx/nginx-tests/master/README)

## D_NGINX_SSI · nginx-tests SSI regression

- 发布者：NGINX
- 检查位置：http/ssi/cache/proxy/rewrite prerequisites and 30-test plan
- 支持内容：Existing server-side-include and proxy-cache local test
- 检查版本：master branch
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://raw.githubusercontent.com/nginx/nginx-tests/master/ssi.t](https://raw.githubusercontent.com/nginx/nginx-tests/master/ssi.t)

## D_NGINX_SSL · nginx-tests SSL regression

- 发布者：NGINX
- 检查位置：http_ssl, socket_ssl, openssl daemon and 21-test plan
- 支持内容：Bounded TLS test and required Perl/OpenSSL dependencies
- 检查版本：master branch
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://raw.githubusercontent.com/nginx/nginx-tests/master/ssl.t](https://raw.githubusercontent.com/nginx/nginx-tests/master/ssl.t)

## D_PG_BUILD · PostgreSQL: Building and Installation with Autoconf and Make

- 发布者：PostgreSQL Global Development Group
- 检查位置：17.3.2 installation procedure; 17.3.3 prefix, SSL and compression options
- 支持内容：VPATH configure, make/all/world-bin, private-prefix installation and initdb/pg_ctl workflow
- 检查版本：current PostgreSQL 18 documentation
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://www.postgresql.org/docs/current/install-make.html](https://www.postgresql.org/docs/current/install-make.html)

## D_PG_TEST · PostgreSQL: Running the Tests

- 发布者：PostgreSQL Global Development Group
- 检查位置：31.1.1 make check; 31.1.3 isolation, check-world and TAP; 31.1.4 locale
- 支持内容：Temporary unprivileged test servers, core and additional suites, test-process concurrency and locale requirements
- 检查版本：current PostgreSQL 18 documentation
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://www.postgresql.org/docs/current/regress-run.html](https://www.postgresql.org/docs/current/regress-run.html)

## D_REDIS_BUILD · Redis 7.2 build and install instructions

- 发布者：Redis
- 检查位置：Building Redis, TLS, dependency cleanup, tests and PREFIX installation
- 支持内容：make, BUILD_TLS=yes, test certificates, runtest --tls, private PREFIX; bundled deps are compiled
- 检查版本：7.2 branch
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://raw.githubusercontent.com/redis/redis/7.2/README.md](https://raw.githubusercontent.com/redis/redis/7.2/README.md)

## D_REDIS_TEST · Redis test runner selectors

- 发布者：Redis
- 检查位置：all_tests, --single, --list-tests, --clients, --baseport, --portcount
- 支持内容：Source-defined unit/integration selection and port-range control
- 检查版本：7.2 branch
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://raw.githubusercontent.com/redis/redis/7.2/tests/test_helper.tcl](https://raw.githubusercontent.com/redis/redis/7.2/tests/test_helper.tcl)

## D_ROCKS_BUILD · RocksDB Makefile

- 发布者：RocksDB / Meta
- 检查位置：static_lib, shared_lib, db_basic_test, table_test, install-static/install-shared, PREFIX
- 支持内容：Concrete library/test targets and installation rules
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://raw.githubusercontent.com/facebook/rocksdb/main/Makefile](https://raw.githubusercontent.com/facebook/rocksdb/main/Makefile)

## D_ROCKS_TEST · RocksDB Contribution Guide

- 发布者：RocksDB / Meta
- 检查位置：Running individual tests, gtest_filter and TEST_TMPDIR
- 支持内容：db_basic_test execution, subset discovery and sandbox-local temporary databases
- 检查版本：current-page
- 不可变 revision：null
- 许可/访问：public official source; exact selected revision and dependency licenses require verification
- 来源：[https://github.com/facebook/rocksdb/wiki/RocksDB-Contribution-Guide](https://github.com/facebook/rocksdb/wiki/RocksDB-Contribution-Guide)

## E_BABEL_CONTRIB · Babel build and test guide

- 发布者：babel
- 检查位置：Developing / Setup; make build; package tests
- 支持内容：Real Babel build emits packages/*/lib; package-filtered Jest tests
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://github.com/babel/babel/blob/main/CONTRIBUTING.md](https://github.com/babel/babel/blob/main/CONTRIBUTING.md)

## E_BABEL_CORE · Babel core package metadata

- 发布者：babel
- 检查位置：package entry points/files and workspace dependencies
- 支持内容：Fresh consumer must receive local built core and its intended Babel dependency closure
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://github.com/babel/babel/blob/main/packages/babel-core/package.json](https://github.com/babel/babel/blob/main/packages/babel-core/package.json)

## E_BABEL_MAKE · Babel Makefile

- 发布者：babel
- 检查位置：build, build-dist, bootstrap-only, test-only, build-standalone
- 支持内容：Exact build/test task meanings; build-dist alone is not the whole monorepo build
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://github.com/babel/babel/blob/main/Makefile](https://github.com/babel/babel/blob/main/Makefile)

## E_ESBUILD_INSTALL · esbuild build and test installation script

- 发布者：evanw
- 检查位置：buildBinary; buildNeutralLib; installForTests
- 支持内容：Official tests pack/install locally and bind ESBUILD_BINARY_PATH to source-built binary
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://github.com/evanw/esbuild/blob/main/scripts/esbuild.js](https://github.com/evanw/esbuild/blob/main/scripts/esbuild.js)

## E_ESBUILD_MAKE · esbuild Makefile

- 发布者：evanw
- 检查位置：esbuild; test-go; js-api-tests; end-to-end-tests; plugin-tests; test-common
- 支持内容：Actual Go build and bounded local official test targets
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://github.com/evanw/esbuild/blob/main/Makefile](https://github.com/evanw/esbuild/blob/main/Makefile)

## E_ES_BUILD · Elasticsearch Gradle build structure

- 发布者：elastic
- 检查位置：Build logic organisation; module types; dependency verification
- 支持内容：Composite Gradle build, server/module distribution and explicit dependency lock
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://github.com/elastic/elasticsearch/blob/main/BUILDING.md](https://github.com/elastic/elasticsearch/blob/main/BUILDING.md)

## E_ES_QUERY_TEST · Elasticsearch MatchQueryBuilderTests

- 发布者：elastic
- 检查位置：org.elasticsearch.index.query test package
- 支持内容：Existing query-builder unit suite suitable for server:test selection
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://github.com/elastic/elasticsearch/blob/main/server/src/test/java/org/elasticsearch/index/query/MatchQueryBuilderTests.java](https://github.com/elastic/elasticsearch/blob/main/server/src/test/java/org/elasticsearch/index/query/MatchQueryBuilderTests.java)

## E_ES_TEST · Elasticsearch testing and packages

- 发布者：elastic
- 检查位置：Creating packages; Test case filtering; randomized seed
- 支持内容：localDistro/linux-tar:assemble and server:test package filtering; global assemble builds all platforms
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://github.com/elastic/elasticsearch/blob/main/TESTING.asciidoc](https://github.com/elastic/elasticsearch/blob/main/TESTING.asciidoc)

## E_FLINK_CORE · Flink core POM

- 发布者：apache
- 检查位置：test dependencies and Maven module configuration
- 支持内容：Core module is a real Java build/test target; scope its official tests
- 检查版本：master
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://github.com/apache/flink/blob/master/flink-core/pom.xml](https://github.com/apache/flink/blob/master/flink-core/pom.xml)

## E_FLINK_DIST · Flink distribution POM

- 发布者：apache
- 检查位置：distribution dependencies and assembly
- 支持内容：Distribution closure includes core, runtime, clients, streaming and state backends
- 检查版本：master
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://github.com/apache/flink/blob/master/flink-dist/pom.xml](https://github.com/apache/flink/blob/master/flink-dist/pom.xml)

## E_FLINK_README · Flink source build README

- 发布者：apache
- 检查位置：Building Apache Flink from Source; Java 17 profile; build-target
- 支持内容：mvnw clean package with jdk17/java17-target and produced distribution
- 检查版本：master
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://github.com/apache/flink/blob/master/README.md](https://github.com/apache/flink/blob/master/README.md)

## E_KAFKA_QUICKSTART · Apache Kafka Quickstart

- 发布者：Apache Software Foundation
- 检查位置：Quickstart steps 2–5 and 8: standalone KRaft start, topic creation, producing/consuming events, shutdown
- 支持内容：Independent producer/consumer acceptance follows official standalone workflow
- 检查版本：current-page
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://kafka.apache.org/quickstart](https://kafka.apache.org/quickstart)

## E_KAFKA_README · Kafka build, test, release and KRaft instructions

- 发布者：apache
- 检查位置：Build a JAR; Run unit/integration tests; Building a binary release; Running a Kafka broker; Common build options
- 支持内容：jar/releaseTarGz, clients:test filters, local standalone broker, maxParallelForks/maxScalacThreads
- 检查版本：trunk
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://github.com/apache/kafka/blob/trunk/README.md](https://github.com/apache/kafka/blob/trunk/README.md)

## E_LUCENE_README · Lucene build prerequisites

- 发布者：apache
- 检查位置：Building / Basic steps
- 支持内容：Use project Gradle wrapper and JDK declared by chosen revision
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://github.com/apache/lucene/blob/main/README.md](https://github.com/apache/lucene/blob/main/README.md)

## E_LUCENE_TESTS · Lucene testing guide

- 发布者：apache
- 检查位置：Generic test commands; module tests; seed control
- 支持内容：core test target and declared randomized-test seed
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://github.com/apache/lucene/blob/main/help/tests.md](https://github.com/apache/lucene/blob/main/help/tests.md)

## E_LUCENE_WORKFLOW · Lucene build workflow

- 发布者：apache
- 检查位置：assemble, module build, mavenLocal
- 支持内容：Build JARs and stage local Maven repository, without public publishing
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://github.com/apache/lucene/blob/main/help/workflow.md](https://github.com/apache/lucene/blob/main/help/workflow.md)

## E_ROLLUP_CONTRIB · Rollup contributor build guide

- 发布者：rollup
- 检查位置：Rust setup; build vs build:quick; test categories
- 支持内容：Native toolchain and full build are needed for full artifact/test coverage
- 检查版本：master
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://github.com/rollup/rollup/blob/master/CONTRIBUTING.md](https://github.com/rollup/rollup/blob/master/CONTRIBUTING.md)

## E_ROLLUP_PACKAGE · Rollup build and test scripts

- 发布者：rollup
- 检查位置：build, build:napi, build:wasm, build:js, build:copy-native, test:only, files
- 支持内容：Rust native/WASM plus JS build; resulting package includes dist/*.node
- 检查版本：master
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://github.com/rollup/rollup/blob/master/package.json](https://github.com/rollup/rollup/blob/master/package.json)

## E_ROLLUP_PACKAGE_TEST · Rollup package test script

- 发布者：rollup
- 检查位置：Entire short script
- 支持内容：Package test only compares fsevents dependency metadata; independent installed consumer is additionally required
- 检查版本：master
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://github.com/rollup/rollup/blob/master/scripts/test-package.js](https://github.com/rollup/rollup/blob/master/scripts/test-package.js)

## E_ROLLUP_WASM_TOOLCHAIN · Rollup WASM binding build configuration

- 发布者：Rollup
- 检查位置：wasm-bindgen dependency and release wasm-opt configuration
- 支持内容：WASM 构建依赖的版本匹配与优化工具链。
- 检查版本：current main/master inspected for this design
- 不可变 revision：null
- 许可/访问：Public upstream source; exact terms frozen with the instance
- 来源：[https://github.com/rollup/rollup/blob/master/rust/bindings_wasm/Cargo.toml](https://github.com/rollup/rollup/blob/master/rust/bindings_wasm/Cargo.toml)

## E_SPARK_BUILD · Spark 3.5.7 source build documentation

- 发布者：apache
- 检查位置：Apache Maven; Runnable Distribution; Hive/JDBC; submodules
- 支持内容：build/mvn and dev/make-distribution.sh, scoped JVM distribution profiles
- 检查版本：v3.5.7
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://github.com/apache/spark/blob/v3.5.7/docs/building-spark.md](https://github.com/apache/spark/blob/v3.5.7/docs/building-spark.md)

## E_SPARK_DIST · Spark 3.5.7 distribution script

- 发布者：apache
- 检查位置：argument parsing and BUILD_COMMAND clean package
- 支持内容：--tgz/name and Maven profile forwarding; packaging internally runs clean package with tests deferred
- 检查版本：v3.5.7
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://github.com/apache/spark/blob/v3.5.7/dev/make-distribution.sh](https://github.com/apache/spark/blob/v3.5.7/dev/make-distribution.sh)

## E_SPARK_TEST · Spark DAGSchedulerSuite

- 发布者：apache
- 检查位置：DAGSchedulerSuite class and local test fixture
- 支持内容：Concrete official local scheduler suite
- 检查版本：v3.5.7
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://github.com/apache/spark/blob/v3.5.7/core/src/test/scala/org/apache/spark/scheduler/DAGSchedulerSuite.scala](https://github.com/apache/spark/blob/v3.5.7/core/src/test/scala/org/apache/spark/scheduler/DAGSchedulerSuite.scala)

## E_SPARK_TOOLS · Spark developer tools

- 发布者：Apache Software Foundation
- 检查位置：Running Individual Tests
- 支持内容：build/mvn -Dtest=none -DwildcardSuites=org.apache.spark.scheduler.DAGSchedulerSuite test
- 检查版本：current-page
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://spark.apache.org/developer-tools.html](https://spark.apache.org/developer-tools.html)

## E_SWC_CONTRIB · SWC contributor workflow

- 发布者：swc-project
- 检查位置：submodules; JS dependencies; per-package cargo tests
- 支持内容：Pinned ECMAScript fixtures and scoped cargo test -p swc_ecma_transforms --all-features
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://github.com/swc-project/swc/blob/main/CONTRIBUTING.md](https://github.com/swc-project/swc/blob/main/CONTRIBUTING.md)

## E_SWC_CORE · SWC core native package

- 发布者：swc-project
- 检查位置：build/build:dev/build:ts/test; files
- 支持内容：pnpm build invokes tsc plus napi release build of binding_core_node; plain pack excludes .node
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://github.com/swc-project/swc/blob/main/packages/core/package.json](https://github.com/swc-project/swc/blob/main/packages/core/package.json)

## E_SWC_LOADER · SWC native binding loader

- 发布者：swc-project
- 检查位置：Linux native-binding resolution branches
- 支持内容：Installed acceptance must bind locally built platform binary, not a cached npm native release
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://github.com/swc-project/swc/blob/main/packages/core/binding.js](https://github.com/swc-project/swc/blob/main/packages/core/binding.js)

## E_SWC_TRANSFORMS · SWC transforms crate configuration

- 发布者：SWC project
- 检查位置：features compat/module/optimization/proposal/react/typescript and test dependencies
- 支持内容：Scoped transforms --all-features selects concrete transformation families rather than the complete workspace
- 检查版本：main
- 不可变 revision：null
- 许可/访问：public_source; verify workspace license at frozen revision
- 来源：[https://github.com/swc-project/swc/blob/main/crates/swc_ecma_transforms/Cargo.toml](https://github.com/swc-project/swc/blob/main/crates/swc_ecma_transforms/Cargo.toml)

## E_TS_HEREBY · TypeScript v5.9.3 Hereby tasks

- 发布者：microsoft
- 检查位置：local, runtests, runtests-parallel, LKG, clean
- 支持内容：Build actual compiler/server/declarations; LKG stages freshly built files for packaging
- 检查版本：v5.9.3
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://github.com/microsoft/TypeScript/blob/v5.9.3/Herebyfile.mjs](https://github.com/microsoft/TypeScript/blob/v5.9.3/Herebyfile.mjs)

## E_TS_LKG · TypeScript release-layout staging

- 发布者：Microsoft
- 检查位置：source=built/local, dest=lib; copyScriptOutputs and copyDeclarationOutputs
- 支持内容：LKG removes old lib and copies freshly built compiler, server and declarations into the npm package layout
- 检查版本：v5.9.3
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependencies
- 来源：[https://github.com/microsoft/TypeScript/blob/v5.9.3/scripts/produceLKG.mjs](https://github.com/microsoft/TypeScript/blob/v5.9.3/scripts/produceLKG.mjs)

## E_TS_PACKAGE · TypeScript v5.9.3 package scripts

- 发布者：microsoft
- 检查位置：scripts, files and packageManager
- 支持内容：build:compiler, build:tests, test and package include layout
- 检查版本：v5.9.3
- 不可变 revision：null
- 许可/访问：public_source; verify pinned LICENSE/NOTICE and dependency redistribution terms
- 来源：[https://github.com/microsoft/TypeScript/blob/v5.9.3/package.json](https://github.com/microsoft/TypeScript/blob/v5.9.3/package.json)

## E_WASM_PACK_BUILD · wasm-pack build implementation

- 发布者：wasm-pack
- 检查位置：step_install_wasm_bindgen and step_run_wasm_opt
- 支持内容：构建会查找/获取 wasm-bindgen CLI 并运行 wasm-opt，需要预置固定工具。
- 检查版本：current main/master inspected for this design
- 不可变 revision：null
- 许可/访问：Public upstream source; exact terms frozen with the instance
- 来源：[https://github.com/rustwasm/wasm-pack/blob/master/src/command/build.rs](https://github.com/rustwasm/wasm-pack/blob/master/src/command/build.rs)

## F_JAX_BUILD · JAX developer build and test documentation

- 发布者：JAX
- 检查位置：Building jaxlib; Managing hermetic Python; Running tests
- 支持内容：CPU jaxlib/XLA 真实编译、Bazel dependency lock、lax_numpy 及 CPU suites。
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://docs.jax.dev/en/latest/developer.html](https://docs.jax.dev/en/latest/developer.html)

## F_JAX_PACKAGE · JAX pyproject

- 发布者：JAX
- 检查位置：build-system and test configuration
- 支持内容：JAX Python frontend 的 setuptools wheel；与 jaxlib 配套交付。
- 检查版本：main
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/jax-ml/jax/blob/main/pyproject.toml](https://github.com/jax-ml/jax/blob/main/pyproject.toml)

## F_LGB_BUILD · LightGBM installation and unit-test guide

- 发布者：LightGBM
- 检查位置：Linux CPU build; C++ unit tests; options
- 支持内容：本地 CLI、共享库和 BUILD_CPP_TEST/testlightgbm。
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://lightgbm.readthedocs.io/en/latest/Installation-Guide.html](https://lightgbm.readthedocs.io/en/latest/Installation-Guide.html)

## F_LGB_CMAKE · LightGBM CMake targets

- 发布者：LightGBM
- 检查位置：BUILD_CLI; BUILD_CPP_TEST; install; GoogleTest dependency
- 支持内容：可安装 CLI/SDK、真实测试及离线 GTest 源。
- 检查版本：main
- 不可变 revision：null
- 许可/访问：文件声明 MIT；第三方依赖另行随实例核对
- 来源：[https://github.com/lightgbm-org/LightGBM/blob/main/CMakeLists.txt](https://github.com/lightgbm-org/LightGBM/blob/main/CMakeLists.txt)

## F_NP_BUILD · NumPy build from source

- 发布者：NumPy
- 检查位置：Building NumPy; dependencies; pip source builds
- 支持内容：源码、Meson、Cython 和固定 BLAS/LAPACK 构建。
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://numpy.org/devdocs/building/](https://numpy.org/devdocs/building/)

## F_NP_PACKAGE · NumPy pyproject and wheel testing

- 发布者：NumPy
- 检查位置：build-system; cibuildwheel; Meson install tags
- 支持内容：wheel 包含测试及开发文件；官方 --pyargs numpy 测试形式。
- 检查版本：main
- 不可变 revision：null
- 许可/访问：主源码 BSD-3-Clause；pyproject 列出随包第三方许可证
- 来源：[https://raw.githubusercontent.com/numpy/numpy/main/pyproject.toml](https://raw.githubusercontent.com/numpy/numpy/main/pyproject.toml)

## F_NP_TEST · NumPy test environment

- 发布者：NumPy
- 检查位置：Testing; spin; f2py script test example
- 支持内容：官方数值和接口测试体系；F2PY 消费端扩展示例方向。
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://numpy.org/devdocs/dev/development_environment.html](https://numpy.org/devdocs/dev/development_environment.html)

## F_ORT_BUILD · ONNX Runtime inference build

- 发布者：ONNX Runtime
- 检查位置：Linux; Common Build Instructions; Python build_wheel
- 支持内容：CPU 共享库、Python wheel 与可选 execution providers。
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://onnxruntime.ai/docs/build/inferencing.html](https://onnxruntime.ai/docs/build/inferencing.html)

## F_ORT_RUNNER · ONNX Runtime build/test orchestrator

- 发布者：ONNX Runtime
- 检查位置：run_onnxruntime_tests; build stages; wheel packaging
- 支持内容：实际 onnxruntime_test_all/provider/shared library 测试程序和配置目录。
- 检查版本：main
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/microsoft/onnxruntime/blob/main/tools/ci_build/build.py](https://github.com/microsoft/onnxruntime/blob/main/tools/ci_build/build.py)

## F_ORT_TEST · ONNX Runtime Python tests

- 发布者：ONNX Runtime
- 检查位置：CPU Python API and ONNX fixture tests
- 支持内容：本地产物的 InferenceSession 和结果核验路径。
- 检查版本：main
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/microsoft/onnxruntime/blob/main/onnxruntime/test/python/onnxruntime_test_python.py](https://github.com/microsoft/onnxruntime/blob/main/onnxruntime/test/python/onnxruntime_test_python.py)

## F_PD_BUILD · pandas build environment

- 发布者：pandas
- 检查位置：Step 3 build/install; Meson build directories
- 支持内容：C/Cython 编译与 Meson 构建树保留。
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://pandas.pydata.org/docs/development/contributing_environment.html](https://pandas.pydata.org/docs/development/contributing_environment.html)

## F_PD_PACKAGE · pandas pyproject

- 发布者：pandas
- 检查位置：build-system; optional-dependencies; license
- 支持内容：mesonpy wheel 和 NumPy ABI / test 依赖。
- 检查版本：main
- 不可变 revision：null
- 许可/访问：主项目 BSD-3-Clause；随包许可证清单由 pyproject 明确列出
- 来源：[https://github.com/pandas-dev/pandas/blob/main/pyproject.toml](https://github.com/pandas-dev/pandas/blob/main/pyproject.toml)

## F_PD_TEST · pandas test contribution guide

- 发布者：pandas
- 检查位置：Test locations; Running test suite; network/db markers
- 支持内容：groupby、tslibs 和 indexing 官方测试范围与选择规则。
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://pandas.pydata.org/docs/development/contributing_codebase.html](https://pandas.pydata.org/docs/development/contributing_codebase.html)

## F_PT_BUILD · PyTorch pyproject build backend

- 发布者：PyTorch
- 检查位置：build-system; tool.scikit-build; MAX_JOBS forwarding
- 支持内容：main 使用 scikit-build-core / CMake，输出 wheel；构建并发控制。
- 检查版本：main
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/pytorch/pytorch/blob/main/pyproject.toml](https://github.com/pytorch/pytorch/blob/main/pyproject.toml)

## F_PT_README · PyTorch source installation

- 发布者：PyTorch
- 检查位置：From Source; CPU accelerator-disable variables; prerequisites
- 支持内容：源码和 submodule、C++ 编译及 CPU-only 配置。
- 检查版本：main
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/pytorch/pytorch/blob/main/README.md](https://github.com/pytorch/pytorch/blob/main/README.md)

## F_PT_TEST · PyTorch contribution and testing guide

- 发布者：PyTorch
- 检查位置：Testing; Python Unit Testing; build options
- 支持内容：pytest/test runner、test_nn Linear 选择和真实可选编译功能。
- 检查版本：main
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://raw.githubusercontent.com/pytorch/pytorch/main/CONTRIBUTING.md](https://raw.githubusercontent.com/pytorch/pytorch/main/CONTRIBUTING.md)

## F_PYPA_BUILD · PyPA build frontend

- 发布者：PyPA
- 检查位置：CLI: wheel and no-isolation options
- 支持内容：PEP 517 源码构建 wheel 的通用前端；下列命令是按各项目 backend 组合的实施配方。
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://build.pypa.io/en/stable/reference/cli.html](https://build.pypa.io/en/stable/reference/cli.html)

## F_SK_BUILD · scikit-learn development setup

- 发布者：scikit-learn
- 检查位置：Linux; editable build; testing
- 支持内容：C/C++、Cython、OpenMP、Meson 与 pytest 的官方流程。
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://scikit-learn.org/stable/developers/development_setup.html](https://scikit-learn.org/stable/developers/development_setup.html)

## F_SK_PACKAGE · scikit-learn pyproject

- 发布者：scikit-learn
- 检查位置：build-system; pytest testpaths and import mode
- 支持内容：mesonpy backend 和 sklearn 测试目录、Python/ABI 依赖。
- 检查版本：main
- 不可变 revision：null
- 许可/访问：源码声明 BSD-3-Clause；锁定实例仍须核对随附依赖
- 来源：[https://github.com/scikit-learn/scikit-learn/blob/main/pyproject.toml](https://github.com/scikit-learn/scikit-learn/blob/main/pyproject.toml)

## F_SK_TEST · scikit-learn KD-tree tests

- 发布者：scikit-learn
- 检查位置：KDTree official test module
- 支持内容：原生树扩展的官方测试文件与测试数据辅助模块。
- 检查版本：main
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/scikit-learn/scikit-learn/blob/main/sklearn/neighbors/tests/test_kd_tree.py](https://github.com/scikit-learn/scikit-learn/blob/main/sklearn/neighbors/tests/test_kd_tree.py)

## F_SP_BUILD · SciPy build from source

- 发布者：SciPy
- 检查位置：Linux dependencies; source package build
- 支持内容：C/C++/Fortran、BLAS/LAPACK、Cython/Pythran/pybind11 与 Meson。
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://docs.scipy.org/doc/scipy/building/](https://docs.scipy.org/doc/scipy/building/)

## F_SP_PACKAGE · SciPy pyproject

- 发布者：SciPy
- 检查位置：build-system; wheel/development test settings
- 支持内容：PEP 517/Meson 构建和数值测试依赖配置。
- 检查版本：main
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/scipy/scipy/blob/main/pyproject.toml](https://github.com/scipy/scipy/blob/main/pyproject.toml)

## F_SP_TEST · Running SciPy tests locally

- 发布者：SciPy
- 检查位置：Selecting submodules and individual test cases
- 支持内容：linalg 和 optimize 官方子模块测试选择及 pytest 参数传递。
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://docs.scipy.org/doc/scipy/dev/contributor/devpy_test.html](https://docs.scipy.org/doc/scipy/dev/contributor/devpy_test.html)

## F_TF_BUILD · TensorFlow build from source

- 发布者：TensorFlow
- 检查位置：Build the package; CPU wheel; configuration
- 支持内容：Bazel CPU wheel target、USE_PYWRAP_RULES、离线依赖需冻结。
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://www.tensorflow.org/install/source](https://www.tensorflow.org/install/source)

## F_TF_TEST · TensorFlow contribution guide

- 发布者：TensorFlow
- 检查位置：Running unit tests; softmax_op_test; SavedModel load_test
- 支持内容：CPU 本地 Bazel 测试选择；SavedModel 变量重载验收来源。
- 检查版本：master
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/tensorflow/tensorflow/blob/master/CONTRIBUTING.md](https://github.com/tensorflow/tensorflow/blob/master/CONTRIBUTING.md)

## F_XGB_BUILD · XGBoost build from source

- 发布者：XGBoost
- 检查位置：Shared library; Python source package
- 支持内容：CPU CMake、Python 包重用本轮 libxgboost.so 和 GPU 可选配置。
- 检查版本：main/current-page
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://xgboost.readthedocs.io/en/stable/build.html](https://xgboost.readthedocs.io/en/stable/build.html)

## F_XGB_CMAKE · XGBoost CMake build targets

- 发布者：XGBoost
- 检查位置：USE_CUDA; USE_OPENMP; GOOGLE_TEST; testxgboost
- 支持内容：原生共享库和 C++ 单元测试构建。
- 检查版本：master
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/dmlc/xgboost/blob/master/CMakeLists.txt](https://github.com/dmlc/xgboost/blob/master/CMakeLists.txt)

## F_XGB_TEST · XGBoost basic Python tests

- 发布者：XGBoost
- 检查位置：tests/python/test_basic.py
- 支持内容：Python binding 基础训练、预测及序列化的现有测试模块。
- 检查版本：master
- 不可变 revision：null
- 许可/访问：needs_verification
- 来源：[https://github.com/dmlc/xgboost/blob/master/tests/python/test_basic.py](https://github.com/dmlc/xgboost/blob/master/tests/python/test_basic.py)

