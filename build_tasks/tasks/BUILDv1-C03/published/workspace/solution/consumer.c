/* Standalone MagickWand consumer - compiled outside the source tree. */
#include <stdio.h>
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
    if (MagickResizeImage(wand, 64, 48, LanczosFilter) == MagickFalse) {
        fprintf(stderr, "resize failed\n"); return 4;
    }
    if (MagickSetImageFormat(wand, "PNG") == MagickFalse) {
        fprintf(stderr, "set format failed\n"); return 5;
    }
    if (MagickWriteImage(wand, argv[2]) == MagickFalse) {
        fprintf(stderr, "write failed: %s\n", argv[2]); return 6;
    }
    printf("wrote %s\n", argv[2]);
    wand = DestroyMagickWand(wand);
    MagickWandTerminus();
    return 0;
}
