# BUILDv1-C07 (core) — Godot `tests=yes` editor + headless consumer

## What this builds

From the frozen source archive (Godot `4.4.1-stable`, commit
`49a5bc7b616bd04689a2c89e89bda41f50241464`) this solution:

1. builds a Linux/BSD **editor** binary with the in-tree test harness
   (`scons platform=linuxbsd target=editor arch=x86_64 tests=yes -jN`),
2. installs that binary plus licenses and a provenance manifest into a private
   prefix,
3. runs the **official doctest unit suite** (documented `[Stress]` cases
   excluded) and the **official GDScript script suite**, preserving the raw
   logs and generating `doctest.xml`,
4. creates an independent consumer project under `/workspace/consumer` and runs
   it headless with the *installed* binary, asserting real script and scene-tree
   output.

## Usage

```
python3 solution/main.py doctor --input input
python3 solution/main.py run --input input --output output --jobs 4
python3 solution/main.py --help
```

`doctor` lists exact missing items as `MISSING source/<file>`, `MISSING tool:<x>`
or `MISSING pkg-config:<y>` and exits `78` when anything is absent, `0` when
ready. `run` performs the same preflight check first and returns `78` instead of
starting an impossible build. `--help` never triggers any build.

## Artifacts

* `output/install/bin/godot` — newly built editor binary
* `output/install/{LICENSE.txt,COPYRIGHT.txt,AUTHORS.md,version.json}`
* `output/install.tar.gz` and `output/install_manifest.json`
* `output/logs/*.log` — every build/install/test/consumer command log
* `output/commands.json`, `output/tests.json`
* `output/doctest.xml`, `output/test_summary.json`, `output/scons_config.json`

## Consumer

The consumer is a three-file Godot project (`project.godot`, `main.tscn`,
`main.gd`) run as

```
<installed>/bin/godot --headless --path <consumer> --quit-after 300
```

The `Node._ready()` script computes a checksum, prints
`CONSUMER_SUM=55` / `CONSUMER_NODE=Main` / `CONSUMER_OK` and quits. The session
fails hard if any of those markers is absent, so a silently broken engine or a
missing scene-tree load cannot pass.

## Honest limitations

* Profile `core` deliberately does **not** build `template_release`; no
  standalone `.x86_64` export is produced. Only the editor + headless consumer
  path is covered. Template building is the `reference` scope.
* Doctest and GDScript suites run against headless/mock display and audio
  servers. Passing them does **not** demonstrate physical GPU or audio hardware
  correctness.
* The buildkit auto-parser does not understand doctest summary lines, so
  `tests.json` records `parsed_count: null`. Real counters are extracted from the
  preserved console logs into `test_summary.json`; counts are never fabricated.
* Upstream `*.out` reference files are used as-is and are never regenerated.
* Requires Linux x86_64 with X11/xkbcommon/GL development headers, `scons`,
  `gcc`/`g++` and `pkg-config`; these are dependency inputs, not delivered
  products. No network access is used.
