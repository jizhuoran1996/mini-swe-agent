# libvips 8.16.1 core build

Builds libvips from the frozen source archive at commit
82c7c05cb02a52750251bb4cc69d67f40568cf98 (v8.16.1) using Meson and Ninja.

## Usage

```bash
python3 solution/main.py doctor --input input
python3 solution/main.py run --input input --output output --jobs 4
```

`doctor` checks the source archive checksum, required tools, and
pkg-config dependencies (glib, expat, libjpeg, libpng, libtiff). Exits 78
when anything is missing.

`run` performs:

1. Extract source to `/workspace/src`.
2. Configure with Meson: shared C/C++ library and CLI; introspection and
   ImageMagick disabled; JPEG, PNG, TIFF explicitly enabled. The upstream
   v8.16.1 `meson_options.txt` does not define `tests` or `tools` options,
   so no such flags are passed, and neither feature is disabled.
3. Compile with 4 jobs.
4. Discover the official Meson tests and run the required selectors:
   `cli formats seq stall threading keep token connections descriptors`.
   Configure aborts if any selector is absent from the discovered inventory.
5. Install to `/workspace/output/install`.
6. Compile and run an external C++ consumer outside the source tree that
   writes a TIFF, reads it back, crops, scales, writes a PNG, and verifies
   dimensions and band count.

## Limitations

- Only the core CPU library plus explicitly enabled PNG, JPEG and TIFF
  formats are built. Other optional formats (WebP, HEIF, JXL, SVG, PDF, etc.)
  remain disabled.
- ImageMagick is disabled; GObject introspection is disabled.
- The extended post-install pyvips pytest suite is not run.
- Build parallelism is capped at 4, test parallelism at 2.
