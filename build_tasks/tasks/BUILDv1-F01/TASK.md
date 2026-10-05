# BUILDv1-F01 — 构建并交付 CPU PyTorch 发行包及扩展开发环境

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

{
  "scope": "CPU wheel，按官方选项关闭 distributed 和未需要的 CPU 加速 backend；执行 Linear 验收。"
}

## Source and execution binding

```json
{
  "task_id": "BUILDv1-F01",
  "project": "PyTorch",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/pytorch/pytorch",
    "acquisition_url": "https://codeload.github.com/pytorch/pytorch/tar.gz/e2d141dbde55c2a4370fac5165b0561b6af4798b",
    "release_ref": "v2.7.1",
    "commit": "e2d141dbde55c2a4370fac5165b0561b6af4798b",
    "filename": "source-all-submodules.tar.gz",
    "bytes": 330654645,
    "sha256": "f7358d125936e3374e8abfea058dbf4a3c9c800799ce1d911c82321e77ed18a9",
    "submodules_ready": true,
    "submodules_vendored": true,
    "submodules": [
      {
        "path": "third_party/pybind11",
        "repo": "https://github.com/pybind/pybind11.git",
        "commit": "a2e59f0e7065404b44dfe92a28aca47ba1378dc4",
        "archive_sha256": "1da0a5c38950e4f49329e9de10c59b2527840a1b963113f1c53b455971cd6aef"
      },
      {
        "path": "third_party/eigen",
        "repo": "https://gitlab.com/libeigen/eigen.git",
        "commit": "3147391d946bb4b6c68edd901f2add6ac1f31f8c",
        "archive_sha256": "0c8c490764f9c2a793133491adca0cd073b73e0bde965c68cbe58d91b5ed4261"
      },
      {
        "path": "third_party/googletest",
        "repo": "https://github.com/google/googletest.git",
        "commit": "b514bdc898e2951020cbdca1304b75f5950d1f59",
        "archive_sha256": "9257316d65d6259f6596bc4fa5464092305ab3f3d9dc6d7e5780ab462d8baa64"
      },
      {
        "path": "third_party/benchmark",
        "repo": "https://github.com/google/benchmark.git",
        "commit": "0d98dba29d66e93259db7daa53a9327df767a415",
        "archive_sha256": "39fa5d2b71845e39cd308eb05026fb851b4aa801d654970aa31532f2f6b04d69"
      },
      {
        "path": "third_party/protobuf",
        "repo": "https://github.com/protocolbuffers/protobuf.git",
        "commit": "d1eca4e4b421cd2997495c4b4e65cea6be4e9b8a",
        "archive_sha256": "4579f7792b5ac9a2db2ad60409565f694a52b202078efbd36de066b6f2232992"
      },
      {
        "path": "third_party/protobuf/third_party/benchmark",
        "repo": "https://github.com/google/benchmark.git",
        "commit": "5b7683f49e1e9223cf9927b24f6fd3d6bd82e3f8",
        "archive_sha256": "5dc92703f811f94e2aa63bdab07ab749f28a094befa6cdfd5fe177f947590a48"
      },
      {
        "path": "third_party/protobuf/third_party/googletest",
        "repo": "https://github.com/google/googletest.git",
        "commit": "5ec7f0c4a113e2f18ac2c6cc7df51ad6afc24081",
        "archive_sha256": "0e2f36e8e403c125fd0ab02171bdb786d3b6b3875b6ccf3b2eb7969be8faecd0"
      },
      {
        "path": "third_party/NNPACK",
        "repo": "https://github.com/Maratyszcza/NNPACK.git",
        "commit": "c07e3a0400713d546e0dea2d5466dd22ea389c73",
        "archive_sha256": "7af7792ba33873fd8c0ca80f261c565e254ffb1348497da74541bf2909bf013d"
      },
      {
        "path": "third_party/gloo",
        "repo": "https://github.com/facebookincubator/gloo",
        "commit": "5354032ea08eadd7fc4456477f7f7c6308818509",
        "archive_sha256": "5759a06e6c8863c58e8ceadeb56f7c701fec89b2559ba33a103a447207bf69c7"
      },
      {
        "path": "third_party/pthreadpool",
        "repo": "https://github.com/Maratyszcza/pthreadpool.git",
        "commit": "4fe0e1e183925bf8cfa6aae24237e724a96479b8",
        "archive_sha256": "9e8fb6a8ce03616b84f773d7b50ebe0ea2fe3af5b7df6c6f96fa6b3f049a3303"
      },
      {
        "path": "third_party/FXdiv",
        "repo": "https://github.com/Maratyszcza/FXdiv.git",
        "commit": "b408327ac2a15ec3e43352421954f5b1967701d1",
        "archive_sha256": "9ccf554541666b5c089ad5dd465141d671c99971f36d72f313652f5c49ffce14"
      },
      {
        "path": "third_party/FP16",
        "repo": "https://github.com/Maratyszcza/FP16.git",
        "commit": "4dfe081cf6bcd15db339cf2680b9281b8451eeb3",
        "archive_sha256": "90f20492621d5ed80b442aa682ff92d7ccf333ac8fac4a10e7e02afb159f3c13"
      },
      {
        "path": "third_party/psimd",
        "repo": "https://github.com/Maratyszcza/psimd.git",
        "commit": "072586a71b55b7f8c584153d223e95687148a900",
        "archive_sha256": "f6c4dab91ae9a03b3019e7cab0572743afd0e1b6e75b97fcca50259c737c924e"
      },
      {
        "path": "third_party/cpuinfo",
        "repo": "https://github.com/pytorch/cpuinfo.git",
        "commit": "1e83a2fdd3102f65c6f1fb602c1b320486218a99",
        "archive_sha256": "fe2ffde402c3ea46743ac73544a9a32c2f8a6d32edccabde508622ea3e53d7aa"
      },
      {
        "path": "third_party/python-peachpy",
        "repo": "https://github.com/malfet/PeachPy.git",
        "commit": "f45429b087dd7d5bc78bb40dc7cf06425c252d67",
        "archive_sha256": "e57182725e856db7751df5a4546fbc4fee9dd7a59ea2285ae4b3452b0dc7bc5c"
      },
      {
        "path": "third_party/onnx",
        "repo": "https://github.com/onnx/onnx.git",
        "commit": "b8baa8446686496da4cc8fda09f2b6fe65c2a02c",
        "archive_sha256": "b741da9ecd0021df2d5bcd5ee73c5b9d88f8d870df7b489fa4b15ef6951e9a13"
      },
      {
        "path": "third_party/onnx/third_party/pybind11",
        "repo": "https://github.com/pybind/pybind11.git",
        "commit": "3e9dfa2866941655c56877882565e7577de6fc7b",
        "archive_sha256": "9a7d245f405f470798b9d2a48912cc97230658024775299eac203f7c9c9ae37c"
      },
      {
        "path": "third_party/sleef",
        "repo": "https://github.com/shibatch/sleef",
        "commit": "56e1f79cb140fb9326d612d0be06b5250565cade",
        "archive_sha256": "d51c477ae25bead879e8fc869fb3740e66c18b431f45ed0598ec4ba4985023a0"
      },
      {
        "path": "third_party/ideep",
        "repo": "https://github.com/intel/ideep",
        "commit": "719d8e6cd7f7a0e01b155657526d693acf97c2b3",
        "archive_sha256": "cea5fbec1ab7c1bb041f2b239b7ce489ab60f6f297a03ee4437c09ea4b74f1ee"
      },
      {
        "path": "third_party/ideep/mkl-dnn",
        "repo": "https://github.com/intel/mkl-dnn.git",
        "commit": "8d263e693366ef8db40acc569cc7d8edf644556d",
        "archive_sha256": "3098858a97dc657425b61eb07c3a71862ad561dc7c6ce910408006c9befd1e97"
      },
      {
        "path": "third_party/gemmlowp/gemmlowp",
        "repo": "https://github.com/google/gemmlowp.git",
        "commit": "3fb5c176c17c765a3492cd2f0321b0dab712f350",
        "archive_sha256": "fdd6f08bdb33d33f4df516ffb91730fdb163479c19502cfc983083fd9cf43bfa"
      },
      {
        "path": "third_party/fbgemm",
        "repo": "https://github.com/pytorch/fbgemm",
        "commit": "dbc3157bf256f1339b3fa1fef2be89ac4078be0e",
        "archive_sha256": "9852e0190a26ad899a5a1136d97f2df534102d39aecc592151d7c620c023931a"
      },
      {
        "path": "third_party/fbgemm/third_party/asmjit",
        "repo": "https://github.com/asmjit/asmjit.git",
        "commit": "d3fbf7c9bc7c1d1365a94a45614b91c5a3706b81",
        "archive_sha256": "bd19e308b30f0c8c8b0d34be356422b4ccce12f9dc590f77ecb886c21bcfedab"
      },
      {
        "path": "third_party/fbgemm/third_party/cpuinfo",
        "repo": "https://github.com/pytorch/cpuinfo",
        "commit": "ed8b86a253800bafdb7b25c5c399f91bff9cb1f3",
        "archive_sha256": "f4d856b143041697d1780065040e863264c84282963edb4cab1e4bbb7f7b6ce4"
      },
      {
        "path": "third_party/fbgemm/third_party/googletest",
        "repo": "https://github.com/google/googletest",
        "commit": "cbf019de22c8dd37b2108da35b2748fd702d1796",
        "archive_sha256": "8b160748c057ea013fdc1969cf2ab2ea0c6ed0bac029734b1a43806676422585"
      },
      {
        "path": "third_party/fbgemm/third_party/hipify_torch",
        "repo": "https://github.com/ROCmSoftwarePlatform/hipify_torch.git",
        "commit": "23f53b025b466d8ec3c45d52290d3442f7fbe6b1",
        "archive_sha256": "70c7d5056cbc9298cfb501710be43de3f81c39076fd59a97396ca0587403c9b8"
      },
      {
        "path": "third_party/fbgemm/third_party/cutlass",
        "repo": "https://github.com/NVIDIA/cutlass.git",
        "commit": "fc9ebc645b63f3a6bc80aaefde5c063fb72110d6",
        "archive_sha256": "26e27f86c08709be3db7ef748e4e207504541465809a4e8de1f93b790e55f155"
      },
      {
        "path": "android/libs/fbjni",
        "repo": "https://github.com/facebookincubator/fbjni.git",
        "commit": "7e1e1fe3858c63c251c637ae41a20de425dde96f",
        "archive_sha256": "221024505fa31647a1bce58ffeeeefc761b93f3b9ee7a8a9e0608268fb068611"
      },
      {
        "path": "third_party/XNNPACK",
        "repo": "https://github.com/google/XNNPACK.git",
        "commit": "51a0103656eff6fc9bfd39a4597923c4b542c883",
        "archive_sha256": "3ff271a4f41e798616950b0c690d127afcc530a6180f78c78c4b2932920911aa"
      },
      {
        "path": "third_party/fmt",
        "repo": "https://github.com/fmtlib/fmt.git",
        "commit": "123913715afeb8a437e6388b4473fcc4753e1c9a",
        "archive_sha256": "95f89f1eb3b53478417185afc0b7e3d40ec889687af86e890da20068534d29f7"
      },
      {
        "path": "third_party/tensorpipe",
        "repo": "https://github.com/pytorch/tensorpipe.git",
        "commit": "52791a2fd214b2a9dc5759d36725909c1daa7f2e",
        "archive_sha256": "7ff0b84c0623f3360ec7c34b8c4fe02e7f9a87f8fa559c303f9574e44be0bc56"
      },
      {
        "path": "third_party/tensorpipe/third_party/pybind11",
        "repo": "https://github.com/pybind/pybind11.git",
        "commit": "a23996fce38ff6ccfbcdc09f1e63f2c4be5ea2ef",
        "archive_sha256": "fd73796d5d0c0a2d0f780b7b5a16e694241c30e637df15a4ee632cb55f63d5e4"
      },
      {
        "path": "third_party/tensorpipe/third_party/pybind11/tools/clang",
        "repo": "https://github.com/wjakob/clang-cindex-python3",
        "commit": "6a00cbc4a9b8e68b71caf7f774b3f9c753ae84d5",
        "archive_sha256": "828e0d6238e2129a9e08071750dc16ba10e38eacf96f21b8a71e501c2085b282"
      },
      {
        "path": "third_party/tensorpipe/third_party/libuv",
        "repo": "https://github.com/libuv/libuv.git",
        "commit": "1dff88e5161cba5c59276d2070d2e304e4dcb242",
        "archive_sha256": "c66c8a024bb31c6134347a0d5630f6275c0bfe94d4144504d45099412fd7a054"
      },
      {
        "path": "third_party/tensorpipe/third_party/googletest",
        "repo": "https://github.com/google/googletest.git",
        "commit": "aee0f9d9b5b87796ee8a0ab26b7587ec30e8858e",
        "archive_sha256": "89e40180b66e6629d1dd80c3ca3ab036524ed4d6fda8544980e2d16a2d5cb4b0"
      },
      {
        "path": "third_party/tensorpipe/third_party/libnop",
        "repo": "https://github.com/google/libnop.git",
        "commit": "910b55815be16109f04f4180e9adee14fb4ce281",
        "archive_sha256": "ec3604671f8ea11aed9588825f9098057ebfef7a8908e97459835150eea9f63a"
      },
      {
        "path": "third_party/cudnn_frontend",
        "repo": "https://github.com/NVIDIA/cudnn-frontend.git",
        "commit": "91b7532f3386768bba4f444ee7672b497f34da8a",
        "archive_sha256": "8e701561a8c1ae4dfef8e6dd35680a456f2ddb955c1c542e272aaabe0cc520c6"
      },
      {
        "path": "third_party/kineto",
        "repo": "https://github.com/pytorch/kineto",
        "commit": "a054a4be0db117c579a21747debf19c863631f26",
        "archive_sha256": "0d6d94bb8b19ac22fd99a0d87a83aecbd4080d96ba487155d9cc2b7cf471e82d"
      },
      {
        "path": "third_party/kineto/libkineto/third_party/googletest",
        "repo": "https://github.com/google/googletest.git",
        "commit": "7aca84427f224eeed3144123d5230d5871e93347",
        "archive_sha256": "3a33f9092002723f893eb8679907d44ac3f2a908c295b963d4d42eee53b876a5"
      },
      {
        "path": "third_party/kineto/libkineto/third_party/fmt",
        "repo": "https://github.com/fmtlib/fmt.git",
        "commit": "0041a40c1350ba702d475b9c4ad62da77caea164",
        "archive_sha256": "8f9b5c11096b9475710d2e2d5a411d3b004624de48a8a823aab96c5c44ccd277"
      },
      {
        "path": "third_party/kineto/libkineto/third_party/dynolog",
        "repo": "https://github.com/facebookincubator/dynolog.git",
        "commit": "7d04a0053a845370ae06ce317a22a48e9edcc74e",
        "archive_sha256": "073f6e8fbde10242f773a51ce1c95f82dd75cc545ca0d1f1aa2c3f574c2223fd"
      },
      {
        "path": "third_party/kineto/libkineto/third_party/dynolog/third_party/glog",
        "repo": "https://github.com/google/glog.git",
        "commit": "b33e3bad4c46c8a6345525fd822af355e5ef9446",
        "archive_sha256": "a4cd355a2cfed97becab504a177839c9067901900434e91bc375e292d92206f7"
      },
      {
        "path": "third_party/kineto/libkineto/third_party/dynolog/third_party/gflags",
        "repo": "https://github.com/gflags/gflags.git",
        "commit": "e171aa2d15ed9eb17054558e0b3a6a413bb01067",
        "archive_sha256": "b20f58e7f210ceb0e768eb1476073d0748af9b19dfbbf53f4fd16e3fb49c5ac8"
      },
      {
        "path": "third_party/kineto/libkineto/third_party/dynolog/third_party/gflags/doc",
        "repo": "https://github.com/gflags/gflags.git",
        "commit": "8411df715cf522606e3b1aca386ddfc0b63d34b4",
        "archive_sha256": "d355bc878311356f363dc3f9126f438a7f293f54d7fb9d8f5abe1644f1213e8a"
      },
      {
        "path": "third_party/kineto/libkineto/third_party/dynolog/third_party/fmt",
        "repo": "https://github.com/fmtlib/fmt.git",
        "commit": "cd4af11efc9c622896a3e4cb599fa28668ca3d05",
        "archive_sha256": "0654ea5a1899f373fee87ae00ca3478aef227c3cf23916572421c6ce25d274bc"
      },
      {
        "path": "third_party/kineto/libkineto/third_party/dynolog/third_party/json",
        "repo": "https://github.com/nlohmann/json.git",
        "commit": "4f8fba14066156b73f1189a2b8bd568bde5284c5",
        "archive_sha256": "4a8265a62a356698a37b5b1aa4fce3a0146e317bc70ef954ca0d179276cb9cdb"
      },
      {
        "path": "third_party/kineto/libkineto/third_party/dynolog/third_party/pfs",
        "repo": "https://github.com/dtrugman/pfs.git",
        "commit": "f68a2fa8ea36c783bdd760371411fcb495aa3150",
        "archive_sha256": "43e9eea18697f79b7d0bcb404e78e8bdd5a65d3466aeaff588367d3dfcbac15f"
      },
      {
        "path": "third_party/kineto/libkineto/third_party/dynolog/third_party/googletest",
        "repo": "https://github.com/google/googletest.git",
        "commit": "58d77fa8070e8cec2dc1ed015d66b454c8d78850",
        "archive_sha256": "c6ab3b6b33f51ef7465921f8f8c10c15d7cbc510761a15a18ad85babf6d73278"
      },
      {
        "path": "third_party/kineto/libkineto/third_party/dynolog/third_party/cpr",
        "repo": "https://github.com/libcpr/cpr.git",
        "commit": "871ed52d350214a034f6ef8a3b8f51c5ce1bd400",
        "archive_sha256": "836f338f3ffbdcc29a53ec5fa016facaed238b3faeca1a596acdac7d4c46b424"
      },
      {
        "path": "third_party/kineto/libkineto/third_party/dynolog/third_party/DCGM",
        "repo": "https://github.com/NVIDIA/DCGM.git",
        "commit": "ffde4e54bc7249a6039a5e6b45b395141e1217f9",
        "archive_sha256": "a319e31d087e466ed19acf0a5c8614dfd3208c87891576c60cf7ad421333c3aa"
      },
      {
        "path": "third_party/pocketfft",
        "repo": "https://github.com/mreineck/pocketfft",
        "commit": "9d3ab05a7fffbc71a492bc6a17be034e83e8f0fe",
        "archive_sha256": "28fca6494e7f28f3ddfe08c53afec9e5f873f7924d9ac0ea7b3b9f90405b137b"
      },
      {
        "path": "third_party/ittapi",
        "repo": "https://github.com/intel/ittapi.git",
        "commit": "5b8a7d7422611c3a0d799fb5fc5dd4abfae35b42",
        "archive_sha256": "9b3b14b4f80171b362a94ffcb195f906187a743a81f7cef824513f1fa1a2943a"
      },
      {
        "path": "third_party/flatbuffers",
        "repo": "https://github.com/google/flatbuffers.git",
        "commit": "01834de25e4bf3975a9a00e816292b1ad0fe184b",
        "archive_sha256": "5a1f2a116b49a1aaa3563c3d9e3baf6ea256eebf57c7bc144a2d28aa73deba7b"
      },
      {
        "path": "third_party/nlohmann",
        "repo": "https://github.com/nlohmann/json.git",
        "commit": "87cda1d6646592ac5866dc703c8e1839046a6806",
        "archive_sha256": "6edd378b82bd4f141a37b945af53d2c7458e8e516ed6296fbc5b6ce4176cb6be"
      },
      {
        "path": "third_party/VulkanMemoryAllocator",
        "repo": "https://github.com/GPUOpen-LibrariesAndSDKs/VulkanMemoryAllocator.git",
        "commit": "a6bfc237255a6bac1513f7c1ebde6d8aed6b5191",
        "archive_sha256": "7444a78beeb01ee3baca58721b2b7c936521f05df1f6e322bbafe3c2d4114704"
      },
      {
        "path": "third_party/cutlass",
        "repo": "https://github.com/NVIDIA/cutlass.git",
        "commit": "afa1772203677c5118fcd82537a9c8fefbcc7008",
        "archive_sha256": "e62fb320c2b61e7e0c7a1163c9c5a58f6dd86025adf7df4d124933152482997f"
      },
      {
        "path": "third_party/mimalloc",
        "repo": "https://github.com/microsoft/mimalloc.git",
        "commit": "b66e3214d8a104669c2ec05ae91ebc26a8f5ab78",
        "archive_sha256": "922d76a09976148b98be17de830c21c3672bd08ba8fdb6eb6c43c0089895c784"
      },
      {
        "path": "third_party/opentelemetry-cpp",
        "repo": "https://github.com/open-telemetry/opentelemetry-cpp.git",
        "commit": "a799f4aed9c94b765dcdaabaeab7d5e7e2310878",
        "archive_sha256": "44e028ef77d55dd4582c7a370135f2cb0f87205c9d8e25efac5d2434f000af57"
      },
      {
        "path": "third_party/opentelemetry-cpp/third_party/prometheus-cpp",
        "repo": "https://github.com/jupp0r/prometheus-cpp",
        "commit": "c9ffcdda9086ffd9e1283ea7a0276d831f3c8a8d",
        "archive_sha256": "71bfb49c94da173bb1ef8e89af707a144e98d0fa97d764a74af4a9f532f17978"
      },
      {
        "path": "third_party/opentelemetry-cpp/third_party/prometheus-cpp/3rdparty/googletest",
        "repo": "https://github.com/google/googletest.git",
        "commit": "e2239ee6043f73722e7aa812a459f54a28552929",
        "archive_sha256": "2765fbfaa978e90d1c8477bc2f2b9705be65b1b562bb215dbfaa76567d508fe1"
      },
      {
        "path": "third_party/opentelemetry-cpp/third_party/prometheus-cpp/3rdparty/civetweb",
        "repo": "https://github.com/civetweb/civetweb.git",
        "commit": "eefb26f82b233268fc98577d265352720d477ba4",
        "archive_sha256": "71f951a6d7a0666112ef570de109470d8e25bd3867a9557d1f3fe160f4a33eee"
      },
      {
        "path": "third_party/opentelemetry-cpp/tools/vcpkg",
        "repo": "https://github.com/Microsoft/vcpkg",
        "commit": "8eb57355a4ffb410a2e94c07b4dca2dffbee8e50",
        "archive_sha256": "4fef34ddcd9952c15d493696a70a6e01c62c21f402f70713097aae9978c7d456"
      },
      {
        "path": "third_party/opentelemetry-cpp/third_party/ms-gsl",
        "repo": "https://github.com/microsoft/GSL",
        "commit": "6f4529395c5b7c2d661812257cd6780c67e54afa",
        "archive_sha256": "9ed721e38ad823b4ec66331c9c4fac912d7d7dea26bee3c42d26188666d2cfcc"
      },
      {
        "path": "third_party/opentelemetry-cpp/third_party/googletest",
        "repo": "https://github.com/google/googletest",
        "commit": "b796f7d44681514f58a683a3a71ff17c94edb0c1",
        "archive_sha256": "2681de8c0930b0610dc52a2602fad41d0dafa3d7ff1030da6575d56fc1f4ca46"
      },
      {
        "path": "third_party/opentelemetry-cpp/third_party/benchmark",
        "repo": "https://github.com/google/benchmark",
        "commit": "d572f4777349d43653b21d6c2fc63020ab326db2",
        "archive_sha256": "5467caa302752e1f4911b08759364c7d572325d4bf3893bd6b9e09ae7789770d"
      },
      {
        "path": "third_party/opentelemetry-cpp/third_party/opentelemetry-proto",
        "repo": "https://github.com/open-telemetry/opentelemetry-proto",
        "commit": "4ca4f0335c63cda7ab31ea7ed70d6553aee14dce",
        "archive_sha256": "eb0bc2ae01c6395097f3e3fb583f5793f3fd0136d04cccc5a27b5c0cbfffcd6b"
      },
      {
        "path": "third_party/opentelemetry-cpp/third_party/nlohmann-json",
        "repo": "https://github.com/nlohmann/json",
        "commit": "bc889afb4c5bf1c0d8ee29ef35eaaf4c8bef8a5d",
        "archive_sha256": "a064b06ae82cdf425e67f1b9aa34f2ba8cda2559ab0d54ac08d36a8ecd4b8000"
      },
      {
        "path": "third_party/opentelemetry-cpp/third_party/opentracing-cpp",
        "repo": "https://github.com/opentracing/opentracing-cpp.git",
        "commit": "06b57f48ded1fa3bdd3d4346f6ef29e40e08eaf5",
        "archive_sha256": "d544e60bc2a6287693702f66944a4054d3249f43896754b20900eb84d7c52055"
      },
      {
        "path": "third_party/cpp-httplib",
        "repo": "https://github.com/yhirose/cpp-httplib.git",
        "commit": "3b6597bba913d51161383657829b7e644e59c006",
        "archive_sha256": "a7ff918af7370d47b67e3d731616821ced6bbba55e1fc09580e37308cbde6ca6"
      },
      {
        "path": "third_party/NVTX",
        "repo": "https://github.com/NVIDIA/NVTX.git",
        "commit": "e170594ac7cf1dac584da473d4ca9301087090c1",
        "archive_sha256": "93cf1e4c1661c1905afe647fe0e037798460a0f9b85768e43f3a95ee5855be83"
      },
      {
        "path": "third_party/composable_kernel",
        "repo": "https://github.com/ROCm/composable_kernel.git",
        "commit": "8086bbe3a78d931eb96fe12fdc014082e18d18d3",
        "archive_sha256": "153d6884965d63d00ce934f950f18f75fa0748a1e2142869881f6b73549514a7"
      },
      {
        "path": "third_party/kleidiai",
        "repo": "https://github.com/ARM-software/kleidiai.git",
        "commit": "ef685a13cfbe8d418aa2ed34350e21e4938358b6",
        "archive_sha256": "e5d58f6d6b6e17db2f76bdcb445c6d70edbbf89261e67cc31a9c96d87ebf7f43"
      },
      {
        "path": "third_party/flash-attention",
        "repo": "https://github.com/Dao-AILab/flash-attention.git",
        "commit": "979702c87a8713a8e0a5e9fee122b90d2ef13be5",
        "archive_sha256": "ea1ec2e43422a2b910ecad9df7d4fd58f09ff39036e03d037888147f784ca407"
      },
      {
        "path": "third_party/flash-attention/csrc/cutlass",
        "repo": "https://github.com/NVIDIA/cutlass.git",
        "commit": "c506e16788cb08416a4a57e11a9067beeee29420",
        "archive_sha256": "7112cce1b9ad758402778d297a4406b047fcdf8e79311397699445a4e7037703"
      },
      {
        "path": "third_party/flash-attention/csrc/composable_kernel",
        "repo": "https://github.com/ROCm/composable_kernel.git",
        "commit": "888317e698e9803c62bd38568abc9e05d7709f33",
        "archive_sha256": "2a0df9addb1fd3acd8a0bcfd4e3fc650e384ae922a88874f7bf0fb7195ee47ed"
      }
    ],
    "base_archive": {
      "upstream_repo": "https://github.com/pytorch/pytorch",
      "acquisition_url": "https://codeload.github.com/pytorch/pytorch/tar.gz/e2d141dbde55c2a4370fac5165b0561b6af4798b",
      "release_ref": "v2.7.1",
      "commit": "e2d141dbde55c2a4370fac5165b0561b6af4798b",
      "filename": "source.tar.gz",
      "bytes": 50229902,
      "sha256": "6b1ea1c824e0663df2bb24781d70d8781acd0c753d64fac52f520b4ccb3fc0f3",
      "submodules_ready": false
    }
  },
  "scope": {
    "scope": "CPU wheel，按官方选项关闭 distributed 和未需要的 CPU 加速 backend；执行 Linear 验收。"
  },
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
