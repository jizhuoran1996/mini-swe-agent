# BUILDv1-C02 — GStreamer 1.26.2 frozen CORE build

## What this builds

From the mounted read-only source archive it produces, into a fully private
prefix (default `output/install`):

* `libgstreamer-1.0`, `libgstbase-1.0`, `libgstapp-1.0`, `libgstaudio-1.0`,
  `libgstvideo-1.0`, the plugin scanner and the `gst-launch-1.0` /
  `gst-inspect-1.0` tools.
* The CPU plugin set frozen by the CORE profile: appsrc/appsink, audioconvert,
  audioresample, videoconvert/videoscale, typefind, playback, wavenc/wavparse,
  png/jpeg, matroska, isomp4 (GPU/GUI/PTP/device plugins explicitly disabled).

## Usage

```sh
python3 solution/main.py --help
python3 solution/main.py doctor --input input          # exit 78 if not ready, 0 if ready
python3 solution/main.py run --input input --output output --jobs 4
```

`doctor` prints the exact list of missing source subprojects, tools or
pkg-config dependencies. `run` refuses to start (exit 78) if `doctor` is not
clean, so it is never called on a missing-input path.

## How the build runs

1. `meson setup <build> <src> --prefix <install> --wrap-mode=nodownload` plus the
   frozen `-D` option set, `meson compile -j$JOBS`, `meson install`.
2. `meson test --list` output is saved verbatim to `output/test_inventory.txt`
   and normalised to `(project, test)` pairs in `output/test_inventory.json`.
   The frozen selectors are then resolved to the **exact upstream registered
   names** and executed as `meson test <project>:<name>` (falling back to
   `--suite <project> <name>` when a project prefix is unavailable), with
   `--print-errorlogs`; real, non-empty upstream logs are written under
   `output/logs/`.
3. An independent C consumer (embedded in `solution/main.py`) is compiled
   **outside the source tree** against `pkg-config gstreamer-1.0 gstreamer-app-1.0`
   resolved from `<install>/lib/pkgconfig`, and run with
   `GST_PLUGIN_PATH=<install>/lib/gstreamer-1.0`, `GST_PLUGIN_SYSTEM_PATH=''` and
   a private `GST_REGISTRY`, so no system GStreamer can leak in.
4. File pipelines (audiotestsrc→wavenc, wavparse roundtrip, videotestsrc→pngenc,
   pngdec→jpegenc) are run through the newly built `gst-launch-1.0`; the
   produced media files are asserted non-empty.

Meson's `--list` display strings look like `gstreamer / gst_gstbuffer`; these
are *not* valid CLI selectors. They are parsed into `project` and `name` and
re-emitted as the `project:name` selector Meson accepts. A test that is not
present in the frozen inventory raises an error with the full list of
registered tests — it is never silently skipped or counted as passing.

Every command goes through `buildkit.Session.run/test`, so exit codes, argv,
log digests and per-test raw logs are recorded in `output/commands.json` and
`output/tests.json`.

## Honest limitations

* The frozen archive is a *GitHub codeload* tarball of the GStreamer monorepo.
  GStreamer keeps `gstreamer/`, `gst-plugins-base/` and `gst-plugins-good/` as
  git **submodules** under `subprojects/`. If those submodule trees are not
  vendored into the archive, `subprojects/gstreamer/meson.build` etc. are
  absent and the project simply cannot be configured offline with
  `--wrap-mode=nodownload`. In that case `doctor` reports each missing
  subproject **by name** and `run` exits 78 rather than fabricating a build.
* No network, no sudo and no package installation is performed. Declared
  bootstrap tools (meson/ninja/pkg-config/cc) and system `glib-2.0` /
  `gobject-2.0` / `zlib` are treated as legitimate dependency inputs; the
  delivered target products are the freshly compiled GStreamer libraries,
  plugins and tools under the private prefix.
* `buildkit.Session.test` only auto-parses a known set of upstream summary
  formats. Meson's own output is not one of them, so `parsed_count` is left
  `null` and the raw upstream logs (with per-test Ok/Fail lines and the meson
  summary) are preserved verbatim instead of a manufactured case count.
* `submodules_ready:false` / `offline_dependencies_ready:false` in the frozen
  contract are respected as reported conditions, not silently ignored.
