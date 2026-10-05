/* Standalone MagickWand consumer - compiled outside the source tree.
 *
 * ImageMagick 7 installs its public MagickWand API under the
 * ImageMagick-7 include root; the correct include is
 * <MagickWand/MagickWand.h>.  The legacy <wand/MagickWand.h> path is
 * ImageMagick 6 and does not exist in an IM7 install.
 */
#include <stdio.h>
#include <stddef.h>
#include <sys/types.h>
#include <MagickWand/MagickWand.h>

int main(int argc, char **argv) {
    if (argc != 3) { fprintf(stderr, "usage: %s in out\n", argv[0]); return 2; }

    MagickWandGenesis();
    MagickWand *wand = NewMagickWand();

    if (MagickReadImage(wand, argv[1]) == MagickFalse) {
        fprintf(stderr, "read failed: %s\n", argv[1]);
        return 1;
    }

    size_t w = MagickGetImageWidth(wand);
    size_t h = MagickGetImageHeight(wand);
    printf("read %zux%zu from %s\n", w, h, argv[1]);
    if (w != 128 || h != 96) {
        fprintf(stderr, "unexpected geometry %zux%zu\n", w, h);
        return 3;
    }

    MagickSetImageColorspace(wand, sRGBColorspace);

    PixelWand *pw = NewPixelWand();
    MagickGetImagePixelColor(wand, 0, 0, pw);
    printf("top-left pixel: %s\n", PixelGetColorAsString(pw));
    MagickGetImagePixelColor(wand, 0, (ssize_t)h - 1, pw);
    printf("bottom-left pixel: %s\n", PixelGetColorAsString(pw));
    pw = DestroyPixelWand(pw);

    if (MagickResizeImage(wand, 64, 48, LanczosFilter) == MagickFalse) {
        fprintf(stderr, "resize failed\n"); return 4;
    }

    /* Force a true-colour RGBA PNG so the artefact is never palette/grey
       optimised; PNG32: guarantees colour-type 6 on write. */
    char out[4096];
    int n = snprintf(out, sizeof(out), "PNG32:%s", argv[2]);
    if (n < 0 || (size_t)n >= sizeof(out)) {
        fprintf(stderr, "output path too long\n"); return 7;
    }
    if (MagickWriteImage(wand, out) == MagickFalse) {
        fprintf(stderr, "write failed: %s\n", out); return 6;
    }
    printf("wrote %s (%zux%zu RGBA PNG)\n", out,
           MagickGetImageWidth(wand), MagickGetImageHeight(wand));

    wand = DestroyMagickWand(wand);
    MagickWandTerminus();
    return 0;
}
