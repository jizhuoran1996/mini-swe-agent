# BUILDv1-F10 — 构建 ONNX Runtime CPU wheel 与原生运行库

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

{
  "scope": "完整 CPU wheel/shared library + runtime/shared tests。"
}

## Source and execution binding

```json
{
  "task_id": "BUILDv1-F10",
  "project": "ONNX Runtime",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/microsoft/onnxruntime",
    "acquisition_url": "https://codeload.github.com/microsoft/onnxruntime/tar.gz/8f7cce3a49fdbdac96e0868b75b7d0159db7ac7f",
    "release_ref": "v1.21.1",
    "commit": "8f7cce3a49fdbdac96e0868b75b7d0159db7ac7f",
    "filename": "source.tar.gz",
    "bytes": 240808550,
    "sha256": "f867db83cb997f93b45a572ca4a4d409c7dad6f614179d59dd4b08eea5f9df02",
    "submodules_ready": false
  },
  "scope": {
    "scope": "完整 CPU wheel/shared library + runtime/shared tests。"
  },
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false,
  "dependency_caches": [
    {
      "filename": "ort-dependencies.tar.gz",
      "sha256": "939d6b1fe64097d34d48cec2c441059df280da2826059795c516c3861bc09994",
      "bytes": 141350005,
      "target_outputs_exported": false,
      "destination": "/workspace/cache/ort_deps"
    }
  ],
  "cpu_dependency_sources": [
    {
      "name": "abseil_cpp",
      "url": "https://github.com/abseil/abseil-cpp/archive/refs/tags/20240722.0.zip",
      "upstream_url": "https://github.com/abseil/abseil-cpp/archive/refs/tags/20240722.0.zip",
      "upstream_sha1": "36ee53eb1466fb6e593fc5c286680de31f8a494a",
      "observed_original_sha1": "36ee53eb1466fb6e593fc5c286680de31f8a494a",
      "archive_rebound": false,
      "same_commit_file_tree_verified": false,
      "sha256": "95e90be7c3643e658670e0dd3c1b27092349c34b632c6e795686355f67eca89f"
    },
    {
      "name": "cxxopts",
      "url": "https://github.com/jarro2783/cxxopts/archive/3c73d91c0b04e2b59462f0a741be8c07024c1bc0.zip",
      "upstream_url": "https://github.com/jarro2783/cxxopts/archive/3c73d91c0b04e2b59462f0a741be8c07024c1bc0.zip",
      "upstream_sha1": "6c6ca7f8480b26c8d00476e0e24b7184717fe4f0",
      "observed_original_sha1": "6c6ca7f8480b26c8d00476e0e24b7184717fe4f0",
      "archive_rebound": false,
      "same_commit_file_tree_verified": false,
      "sha256": "57b5f012372d4c0e0a975b2e534e9af647cd20530fc72f73a75a61e05e0f997e"
    },
    {
      "name": "date",
      "url": "https://github.com/HowardHinnant/date/archive/refs/tags/v3.0.1.zip",
      "upstream_url": "https://github.com/HowardHinnant/date/archive/refs/tags/v3.0.1.zip",
      "upstream_sha1": "2dac0c81dc54ebdd8f8d073a75c053b04b56e159",
      "observed_original_sha1": "2dac0c81dc54ebdd8f8d073a75c053b04b56e159",
      "archive_rebound": false,
      "same_commit_file_tree_verified": false,
      "sha256": "f4300b96f7a304d4ef9bf6e0fa3ded72159f7f2d0f605bdde3e030a0dba7cf9f"
    },
    {
      "name": "dlpack",
      "url": "https://github.com/dmlc/dlpack/archive/refs/tags/v0.6.zip",
      "upstream_url": "https://github.com/dmlc/dlpack/archive/refs/tags/v0.6.zip",
      "upstream_sha1": "4d565dd2e5b31321e5549591d78aa7f377173445",
      "observed_original_sha1": "4d565dd2e5b31321e5549591d78aa7f377173445",
      "archive_rebound": false,
      "same_commit_file_tree_verified": false,
      "sha256": "cb296b25f1ad5d52aa0efd7553e1aab17ab4561d1068b291fbe14d543d22f381"
    },
    {
      "name": "eigen",
      "url": "https://gitlab.com/libeigen/eigen/-/archive/1d8b82b0740839c0de7f1242a3585e3390ff5f33/eigen-1d8b82b0740839c0de7f1242a3585e3390ff5f33.tar.gz",
      "upstream_url": "https://gitlab.com/libeigen/eigen/-/archive/1d8b82b0740839c0de7f1242a3585e3390ff5f33/eigen-1d8b82b0740839c0de7f1242a3585e3390ff5f33.zip",
      "upstream_sha1": "5ea4d05e62d7f954a46b3213f9b2535bdd866803",
      "observed_original_sha1": "51982be81bbe52572b54180454df11a3ece9a934",
      "archive_rebound": true,
      "same_commit_file_tree_verified": true,
      "sha256": "c8adb6532fbfacd2ec1418c66404159b00c34d855bdc19cefa1f0db0e5e0aa5f"
    },
    {
      "name": "flatbuffers",
      "url": "https://github.com/google/flatbuffers/archive/refs/tags/v23.5.26.zip",
      "upstream_url": "https://github.com/google/flatbuffers/archive/refs/tags/v23.5.26.zip",
      "upstream_sha1": "59422c3b5e573dd192fead2834d25951f1c1670c",
      "observed_original_sha1": "59422c3b5e573dd192fead2834d25951f1c1670c",
      "archive_rebound": false,
      "same_commit_file_tree_verified": false,
      "sha256": "57bd580c0772fd1a726c34ab8bf05325293bc5f9c165060a898afa1feeeb95e1"
    },
    {
      "name": "fp16",
      "url": "https://github.com/Maratyszcza/FP16/archive/0a92994d729ff76a58f692d3028ca1b64b145d91.zip",
      "upstream_url": "https://github.com/Maratyszcza/FP16/archive/0a92994d729ff76a58f692d3028ca1b64b145d91.zip",
      "upstream_sha1": "b985f6985a05a1c03ff1bb71190f66d8f98a1494",
      "observed_original_sha1": "b985f6985a05a1c03ff1bb71190f66d8f98a1494",
      "archive_rebound": false,
      "same_commit_file_tree_verified": false,
      "sha256": "e66e65515fa09927b348d3d584c68be4215cfe664100d01c9dbc7655a5716d70"
    },
    {
      "name": "fxdiv",
      "url": "https://github.com/Maratyszcza/FXdiv/archive/63058eff77e11aa15bf531df5dd34395ec3017c8.zip",
      "upstream_url": "https://github.com/Maratyszcza/FXdiv/archive/63058eff77e11aa15bf531df5dd34395ec3017c8.zip",
      "upstream_sha1": "a5658f4036402dbca7cebee32be57fb8149811e1",
      "observed_original_sha1": "a5658f4036402dbca7cebee32be57fb8149811e1",
      "archive_rebound": false,
      "same_commit_file_tree_verified": false,
      "sha256": "3d7b0e9c4c658a84376a1086126be02f9b7f753caa95e009d9ac38d11da444db"
    },
    {
      "name": "google_benchmark",
      "url": "https://github.com/google/benchmark/archive/refs/tags/v1.8.5.zip",
      "upstream_url": "https://github.com/google/benchmark/archive/refs/tags/v1.8.5.zip",
      "upstream_sha1": "cd47d3d272faf353600c8cc2fdec2b52d6f69177",
      "observed_original_sha1": "cd47d3d272faf353600c8cc2fdec2b52d6f69177",
      "archive_rebound": false,
      "same_commit_file_tree_verified": false,
      "sha256": "39f57865cdbfa06f02ae91ea76465246046cc47d5908aa5a3abeb9026fb73dcc"
    },
    {
      "name": "googletest",
      "url": "https://github.com/google/googletest/archive/refs/tags/v1.15.0.zip",
      "upstream_url": "https://github.com/google/googletest/archive/refs/tags/v1.15.0.zip",
      "upstream_sha1": "9d2d0af8d77ac726ea55d44a8fa727ec98311349",
      "observed_original_sha1": "9d2d0af8d77ac726ea55d44a8fa727ec98311349",
      "archive_rebound": false,
      "same_commit_file_tree_verified": false,
      "sha256": "ed98258b96c6dc8af33eeb03c8d94a05b185866604382e12980f576595bdc509"
    },
    {
      "name": "googlexnnpack",
      "url": "https://github.com/google/XNNPACK/archive/fe98e0b93565382648129271381c14d6205255e3.zip",
      "upstream_url": "https://github.com/google/XNNPACK/archive/fe98e0b93565382648129271381c14d6205255e3.zip",
      "upstream_sha1": "14f61dcf17cec2cde34ba2dcf61d6f24bf6059f3",
      "observed_original_sha1": "14f61dcf17cec2cde34ba2dcf61d6f24bf6059f3",
      "archive_rebound": false,
      "same_commit_file_tree_verified": false,
      "sha256": "7aeeb8c6e134e0866655bbb7a0387166eba36bcd436a0c3e0f4c5286426b785f"
    },
    {
      "name": "json",
      "url": "https://github.com/nlohmann/json/archive/refs/tags/v3.11.3.zip",
      "upstream_url": "https://github.com/nlohmann/json/archive/refs/tags/v3.11.3.zip",
      "upstream_sha1": "5e88795165cc8590138d1f47ce94ee567b85b4d6",
      "observed_original_sha1": "5e88795165cc8590138d1f47ce94ee567b85b4d6",
      "archive_rebound": false,
      "same_commit_file_tree_verified": false,
      "sha256": "04022b05d806eb5ff73023c280b68697d12b93e1b7267a0b22a1a39ec7578069"
    },
    {
      "name": "microsoft_gsl",
      "url": "https://github.com/microsoft/GSL/archive/refs/tags/v4.0.0.zip",
      "upstream_url": "https://github.com/microsoft/GSL/archive/refs/tags/v4.0.0.zip",
      "upstream_sha1": "cf368104cd22a87b4dd0c80228919bb2df3e2a14",
      "observed_original_sha1": "cf368104cd22a87b4dd0c80228919bb2df3e2a14",
      "archive_rebound": false,
      "same_commit_file_tree_verified": false,
      "sha256": "eb91fcb10a6aa5ccb1d224e07a56c8ecffe9a1bb601fa1848276ec46a2200bfb"
    },
    {
      "name": "mimalloc",
      "url": "https://github.com/microsoft/mimalloc/archive/refs/tags/v2.1.1.zip",
      "upstream_url": "https://github.com/microsoft/mimalloc/archive/refs/tags/v2.1.1.zip",
      "upstream_sha1": "d5ee7d34223d0567892db5179849939c8769dc41",
      "observed_original_sha1": "d5ee7d34223d0567892db5179849939c8769dc41",
      "archive_rebound": false,
      "same_commit_file_tree_verified": false,
      "sha256": "23b1bffb2eff57b1e3cb8edc9410d448db2bb43400206a151e107dcabcad773a"
    },
    {
      "name": "mp11",
      "url": "https://github.com/boostorg/mp11/archive/refs/tags/boost-1.82.0.zip",
      "upstream_url": "https://github.com/boostorg/mp11/archive/refs/tags/boost-1.82.0.zip",
      "upstream_sha1": "9bc9e01dffb64d9e0773b2e44d2f22c51aace063",
      "observed_original_sha1": "9bc9e01dffb64d9e0773b2e44d2f22c51aace063",
      "archive_rebound": false,
      "same_commit_file_tree_verified": false,
      "sha256": "81431bdc44c439a324e02c07ed067f8f556419fd86f2d8b486ff568df6aac899"
    },
    {
      "name": "onnx",
      "url": "https://github.com/onnx/onnx/archive/refs/tags/v1.17.0.zip",
      "upstream_url": "https://github.com/onnx/onnx/archive/refs/tags/v1.17.0.zip",
      "upstream_sha1": "13a60ac5217c104139ce0fd024f48628e7bcf5bc",
      "observed_original_sha1": "13a60ac5217c104139ce0fd024f48628e7bcf5bc",
      "archive_rebound": false,
      "same_commit_file_tree_verified": false,
      "sha256": "54ab63aec98693c8a021aa708aad046183a0d166808733429fde7f644c84d637"
    },
    {
      "name": "protobuf",
      "url": "https://github.com/protocolbuffers/protobuf/archive/refs/tags/v21.12.zip",
      "upstream_url": "https://github.com/protocolbuffers/protobuf/archive/refs/tags/v21.12.zip",
      "upstream_sha1": "7cf2733949036c7d52fda017badcab093fe73bfa",
      "observed_original_sha1": "7cf2733949036c7d52fda017badcab093fe73bfa",
      "archive_rebound": false,
      "same_commit_file_tree_verified": false,
      "sha256": "6a31b662deaeb0ac35e6287bda2f3369b19836e6c9f8828d4da444346f420298"
    },
    {
      "name": "psimd",
      "url": "https://github.com/Maratyszcza/psimd/archive/072586a71b55b7f8c584153d223e95687148a900.zip",
      "upstream_url": "https://github.com/Maratyszcza/psimd/archive/072586a71b55b7f8c584153d223e95687148a900.zip",
      "upstream_sha1": "1f5454b01f06f9656b77e4a5e2e31d7422487013",
      "observed_original_sha1": "1f5454b01f06f9656b77e4a5e2e31d7422487013",
      "archive_rebound": false,
      "same_commit_file_tree_verified": false,
      "sha256": "dc615342bcbe51ca885323e51b68b90ed9bb9fa7df0f4419dbfa0297d5e837b7"
    },
    {
      "name": "pthreadpool",
      "url": "https://github.com/google/pthreadpool/archive/4e80ca24521aa0fb3a746f9ea9c3eaa20e9afbb0.zip",
      "upstream_url": "https://github.com/google/pthreadpool/archive/4e80ca24521aa0fb3a746f9ea9c3eaa20e9afbb0.zip",
      "upstream_sha1": "bd4ea65c8292801e9555b527a0ecbb2e0092c917",
      "observed_original_sha1": "bd4ea65c8292801e9555b527a0ecbb2e0092c917",
      "archive_rebound": false,
      "same_commit_file_tree_verified": false,
      "sha256": "6d373fa7e2b899605fc3b6e72171a71bccbaf9d4d596b7f514535c4ffb966b3b"
    },
    {
      "name": "pybind11",
      "url": "https://github.com/pybind/pybind11/archive/refs/tags/v2.13.6.zip",
      "upstream_url": "https://github.com/pybind/pybind11/archive/refs/tags/v2.13.6.zip",
      "upstream_sha1": "f780292da9db273c8ef06ccf5fd4b623624143e9",
      "observed_original_sha1": "f780292da9db273c8ef06ccf5fd4b623624143e9",
      "archive_rebound": false,
      "same_commit_file_tree_verified": false,
      "sha256": "d0a116e91f64a4a2d8fb7590c34242df92258a61ec644b79127951e821b47be6"
    },
    {
      "name": "pytorch_cpuinfo",
      "url": "https://github.com/pytorch/cpuinfo/archive/8a1772a0c5c447df2d18edf33ec4603a8c9c04a6.zip",
      "upstream_url": "https://github.com/pytorch/cpuinfo/archive/8a1772a0c5c447df2d18edf33ec4603a8c9c04a6.zip",
      "upstream_sha1": "85bf8a60dae026b99b6ccd78606c85ed83bfb2cd",
      "observed_original_sha1": "85bf8a60dae026b99b6ccd78606c85ed83bfb2cd",
      "archive_rebound": false,
      "same_commit_file_tree_verified": false,
      "sha256": "4bf314b3f04db2fd984fef38a7e278e702b74297ef0af592b73296edba02b9d4"
    },
    {
      "name": "re2",
      "url": "https://github.com/google/re2/archive/refs/tags/2024-07-02.zip",
      "upstream_url": "https://github.com/google/re2/archive/refs/tags/2024-07-02.zip",
      "upstream_sha1": "646e1728269cde7fcef990bf4a8e87b047882e88",
      "observed_original_sha1": "646e1728269cde7fcef990bf4a8e87b047882e88",
      "archive_rebound": false,
      "same_commit_file_tree_verified": false,
      "sha256": "a835fe55fbdcd8e80f38584ab22d0840662c67f2feb36bd679402da9641dc71e"
    },
    {
      "name": "safeint",
      "url": "https://github.com/dcleblanc/SafeInt/archive/refs/tags/3.0.28.zip",
      "upstream_url": "https://github.com/dcleblanc/SafeInt/archive/refs/tags/3.0.28.zip",
      "upstream_sha1": "23f252040ff6cb9f1fd18575b32fa8fb5928daac",
      "observed_original_sha1": "23f252040ff6cb9f1fd18575b32fa8fb5928daac",
      "archive_rebound": false,
      "same_commit_file_tree_verified": false,
      "sha256": "3ffbd9a2fdff45da77da3e7269e9aa512ea43bed5c38ce8fd8f3d1068a032c3f"
    },
    {
      "name": "tensorboard",
      "url": "https://github.com/tensorflow/tensorboard/archive/373eb09e4c5d2b3cc2493f0949dc4be6b6a45e81.zip",
      "upstream_url": "https://github.com/tensorflow/tensorboard/archive/373eb09e4c5d2b3cc2493f0949dc4be6b6a45e81.zip",
      "upstream_sha1": "67b833913605a4f3f499894ab11528a702c2b381",
      "observed_original_sha1": "67b833913605a4f3f499894ab11528a702c2b381",
      "archive_rebound": false,
      "same_commit_file_tree_verified": false,
      "sha256": "c7c77b30e7056dc77c067ec70fce24e80a927522b973ebefac33888ba18b5a7d"
    },
    {
      "name": "utf8_range",
      "url": "https://github.com/protocolbuffers/utf8_range/archive/72c943dea2b9240cd09efde15191e144bc7c7d38.zip",
      "upstream_url": "https://github.com/protocolbuffers/utf8_range/archive/72c943dea2b9240cd09efde15191e144bc7c7d38.zip",
      "upstream_sha1": "9925739c9debc0efa2adcb194d371a35b6a03156",
      "observed_original_sha1": "9925739c9debc0efa2adcb194d371a35b6a03156",
      "archive_rebound": false,
      "same_commit_file_tree_verified": false,
      "sha256": "dffb52973f0226fe5df6d9ed40b0d1af1bb89f54beec6a64b66d25e7db9c4152"
    }
  ]
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
