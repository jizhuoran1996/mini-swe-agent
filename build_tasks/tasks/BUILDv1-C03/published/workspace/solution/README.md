# BUILDv1-C03 - ImageMagick source build (frozen core profile)

Builds ImageMagick 7.1.1-47 from the frozen tarball (sha256 verified by
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
   freshly-installed MagickWand via `pkg-config`.
7. `magick identify -format '%wx%h %m %[colorspace]'` verifying geometry,
   format and colorspace of the consumer PNG. The consumer's PNG path is
   pre-verified to exist before identification runs, so a missing artefact is
   reported at the consumer step rather than as a misleading identify error.

## Header layout note

ImageMagick 7 installs its public MagickWand API under the `ImageMagick-7`
include root and the header is:

    #include <MagickWand/MagickWand.h>

`<wand/MagickWand.h>` is the legacy ImageMagick 6 path and is **not** present
in an IM7 install. Both the compiled consumer and the canonical copy of the
consumer source under `solution/consumer.c` use the IM7 layout.

## The PNG32: path bug

The prior revision built the output path in the consumer with
`snprintf(out, sizeof(out), "PNG32:%%s", argv[2])`. Because the C format
string was emitted with the escape for a literal percent, the resulting path
was the fixed byte sequence `PNG32:%s`, so ImageMagick wrote into a literal
file named `%s` (or, with `%s` interpreted as a scene substitution, some
other non-canonical name) and `output.png` never appeared. The consumer now
uses `"PNG32:%s"` with a normal `%s` conversion, so the requested output path
is honoured and `output.png` is produced.

## Consumer semantics

The consumer:

* reads a TIFF gradient produced by the installed CLI,
* asserts the geometry is `128x96`,
* prints the top-left and bottom-left pixel colours,
* resizes to `64x48` with the Lanczos filter,
* normalises the image to `sRGBColorspace`,
* writes the result with the `PNG32:` pseudo-format so the artefact is always
  a true-colour RGBA PNG (never palette/grey optimised), and
* exits non-zero on any failed step.

It is executed with `LD_LIBRARY_PATH` pointing only at the new prefix, so no
system ImageMagick can be picked up.

## Scope / honest limitations

* Only PNG/JPEG/TIFF loaders are asserted end-to-end; other delegates that
  ImageMagick happens to detect in the image are not exercised by the
  consumer, though they remain listed by `magick -list format`.
* Ghostscript is required for the PDF/PS tests inside `make check`. If it is
  not present `doctor` returns 78 and the build is not attempted.
* `make check` is the upstream umbrella target; its log is preserved verbatim
  under `output/logs/`. `buildkit` yields a parsed case count only when the
  upstream summary matches a known pattern - otherwise the raw evidence is
  retained and no counts are invented.
* No system ImageMagick is used anywhere: the compiled consumer links against
  `$INSTALL/lib` and the executed CLI is `$INSTALL/bin/magick`.
