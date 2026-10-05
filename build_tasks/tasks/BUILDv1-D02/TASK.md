# BUILDv1-D02 — 构建并验证 MariaDB 事务数据库发行包

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"完整默认 server/client + CTest；消费者只做本地事务。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-D02",
  "project": "MariaDB",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/MariaDB/server",
    "acquisition_url": "https://codeload.github.com/MariaDB/server/tar.gz/0771110266ff5c04216af4bf1243c65f8c67ccf4",
    "release_ref": "mariadb-11.4.5",
    "commit": "0771110266ff5c04216af4bf1243c65f8c67ccf4",
    "filename": "source-with-submodules.tar.gz",
    "bytes": 134446148,
    "sha256": "ae4cb73c94dc9ec430a709c040749ad9797eb5c6e2d35dad51cc32d0ef00c6ea",
    "submodules_ready": true,
    "submodules_vendored": true,
    "submodules": [
      {
        "path": "libmariadb",
        "repo": "https://github.com/MariaDB/mariadb-connector-c.git",
        "commit": "93e420621a9b367081dcfab17fd1a8340c411cf2",
        "archive_sha256": "dc257985a1c37d160da7870c444eeaf4cb053be66dd0242fb54c570c4480940a"
      },
      {
        "path": "libmariadb/docs",
        "repo": "https://github.com/mariadb-corporation/mariadb-connector-c.wiki.git",
        "commit": "7e12bcea26c8a7fe5ee77f5e5341011bb9d7e084",
        "archive_sha256": "91c5ba7eaee20a4597a59fd82a873b6fd8cfebaeead4260a19beced8f81f8e3d"
      },
      {
        "path": "storage/rocksdb/rocksdb",
        "repo": "https://github.com/facebook/rocksdb.git",
        "commit": "bba5e7bc21093d7cfa765e1280a7c4fdcd284288",
        "archive_sha256": "1a998e7474e07c8f1a14b0333102aa863e9d05bb68f6c6a4feefd49fa1e5068f"
      },
      {
        "path": "wsrep-lib",
        "repo": "https://github.com/codership/wsrep-lib.git",
        "commit": "70cd967f5e249b53d6cce90e2e4198641c564381",
        "archive_sha256": "bd44ee719f8fb303e8f90aaab105db836edc44cd8bb73004f20810248a0e6758"
      },
      {
        "path": "wsrep-lib/wsrep-API/v26",
        "repo": "https://github.com/codership/wsrep-API.git",
        "commit": "12c02f5fdafec70e55d52536b4068e7728675f01",
        "archive_sha256": "611a2f920a9eb1fab51ed31334903ac153b6182dff1521ff7b2e2008226df7e2"
      },
      {
        "path": "extra/wolfssl/wolfssl",
        "repo": "https://github.com/wolfSSL/wolfssl.git",
        "commit": "239b85c80438bf60d9a5b9e0ebe9ff097a760d0d",
        "archive_sha256": "03107dd8f4108e868c7d65d4e1aa281ef3f5df9cb9fb86339377713ec607af84"
      },
      {
        "path": "storage/maria/libmarias3",
        "repo": "https://github.com/mariadb-corporation/libmarias3.git",
        "commit": "0d5babbe46f17147ed51efd1f05a0001017a2aad",
        "archive_sha256": "6a190a80c210fc68b6590703ccbd5c68199c366786242c4b51b3a011cf7c10cd"
      },
      {
        "path": "storage/columnstore/columnstore",
        "repo": "https://github.com/mariadb-corporation/mariadb-columnstore-engine.git",
        "commit": "9763b126517c8efb716e767fd5ba4eb2b5b405fc",
        "archive_sha256": "f5379d1df6163d25bcf1373bc1d55a4aa172f10df7a7d9e08b89dc076d340345"
      },
      {
        "path": "storage/columnstore/columnstore/utils/libmarias3/libmarias3",
        "repo": "https://github.com/mariadb-corporation/libmarias3.git",
        "commit": "f74150b05693440d35f93c43e2d2411cc66fee19",
        "archive_sha256": "67c0ca2763c4cfa3b77727e1ba1f355d100c62c3025ffa939040562d28ea691b"
      }
    ],
    "base_archive": {
      "upstream_repo": "https://github.com/MariaDB/server",
      "acquisition_url": "https://codeload.github.com/MariaDB/server/tar.gz/0771110266ff5c04216af4bf1243c65f8c67ccf4",
      "release_ref": "mariadb-11.4.5",
      "commit": "0771110266ff5c04216af4bf1243c65f8c67ccf4",
      "filename": "source.tar.gz",
      "bytes": 46619761,
      "sha256": "72fd296e3ebc73641f6148db613aeb273ad34eeb3764a7bfc79709490ae073b7",
      "submodules_ready": false
    }
  },
  "scope": "完整默认 server/client + CTest；消费者只做本地事务。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
