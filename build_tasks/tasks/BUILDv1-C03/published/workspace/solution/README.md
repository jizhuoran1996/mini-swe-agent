# BUILDv1-C03 - ImageMagick source build (frozen core profile)

Builds ImageMagick 7.1.1-47 from the frozen tarball (sha256 checked by
`buildkit.Session.prepare`), installs it under `--output/install`, runs the
official `make check` target, and then consumes the install tree from a clean
consumer directory outside the source tree.

## Usage

    python3 solution/main.py --help
    python3 solution/main.py doctor --input /workspace/input        # 0 = ready, 78 = missing
    python3 solution/main.py run --input /workspace/input --output /workspace/output --jobs 4

The `run` command performs, in order:

1. `doctor` gate on the frozen source archive, C toolchain, `pkg-config`
   delegate packages (`libpng`, `libjpeg`, `libtiff-4`, `freetype2`) and
   `ghostscript`.
2. Out-of-tree `configure --prefix=<install> --enable-shared --disable-static
   --without-x --without-perl --with-quantum-depth=16` with PNG/JPEG/TIFF,
   freetype and gslib explicitly enabled.
3. `make -j<BUILD_JOBS>` and `make install` into a private prefix.
4. `magick -list configure` and `magick -list format` capability dumps.
5. Official post-install `make check` (recorded through `Session.test`).
6. A standalone C consumer in `/workspace/consumer` compiled only against the
   freshly-installed MagickWand via `pkg-config`. It includes
   `<MagickWand/MagickWand.h>` (the ImageMagick 7 header layout; the legacy
   `<wand/MagickWand.h>` path does not exist in IM7), reads a TIFF gradient
   produced by the installed CLI, asserts `128x96`, resizes to `64x48`,
   re-emits PNG and prints the top/bottom pixel colours. It is executed with
   `LD_LIBRARY_PATH` pointing only at the new prefix.
7. `magick identify -format '%wx%h %m'` on the consumer PNG asserts the
   written geometry/format.

## Scope / honest limitations

* Only PNG/JPEG/TIFF loaders are asserted end-to-end; other delegates that
  ImageMagick happens to detect in the image are not exercised by the
  consumer, though they remain listed by `magick -list format`.
* Ghostscript is required for the PDF/PS tests inside `make check`. If it is
  not present `doctor` returns 78 and the build is not attempted.
* `make check` is the upstream umbrella target; its log is preserved
  verbatim under `output/logs/`. `buildkit` yields a parsed case count only
  when the upstream summary matches a known pattern - otherwise the raw
  evidence is retained and no counts are invented.
* No system ImageMagick is used anywhere: the compiled consumer links against
  `$INSTALL/lib` and the executed CLI is `$INSTALL/bin/magick`.
