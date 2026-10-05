/* Independent zlib consumer: static-linked against this build's libz.a.
 * Exercises one-shot compression, chunked streaming deflate/inflate, truncated
 * input rejection and gzip file round-trips on a fixed binary fixture.
 */
#include <zlib.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int fails = 0;

static void check(int cond, const char *msg) {
    if (cond) printf("ok - %s\n", msg);
    else { printf("FAIL - %s\n", msg); fails++; }
}

static unsigned char *load(const char *path, size_t *len) {
    FILE *f = fopen(path, "rb");
    unsigned char *buf;
    long n;
    if (f == NULL) return NULL;
    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return NULL; }
    n = ftell(f);
    if (n < 0) { fclose(f); return NULL; }
    rewind(f);
    buf = (unsigned char *)malloc((size_t)n + 1);
    if (buf == NULL) { fclose(f); return NULL; }
    if (fread(buf, 1, (size_t)n, f) != (size_t)n) { free(buf); fclose(f); return NULL; }
    fclose(f);
    *len = (size_t)n;
    return buf;
}

int main(int argc, char **argv) {
    size_t n = 0;
    unsigned char *src, *comp, *dec;
    uLongf bound, clen, dlen;
    int rc;

    if (argc != 3) {
        fprintf(stderr, "usage: %s <fixture> <gzip-output>\n", argv[0]);
        return 2;
    }
    src = load(argv[1], &n);
    if (src == NULL || n == 0) {
        fprintf(stderr, "cannot read non-empty fixture %s\n", argv[1]);
        return 2;
    }
    printf("fixture bytes: %zu\n", n);
    check(strcmp(zlibVersion(), "1.3.1") == 0, "zlibVersion == 1.3.1");

    /* 1. one-shot compress2 / uncompress round-trip */
    bound = compressBound((uLong)n);
    comp = (unsigned char *)malloc(bound ? bound : 1);
    dec = (unsigned char *)malloc(n + 1);
    if (comp == NULL || dec == NULL) { fprintf(stderr, "out of memory\n"); return 2; }
    clen = bound;
    rc = compress2(comp, &clen, src, (uLong)n, 9);
    check(rc == Z_OK, "compress2 returns Z_OK");
    dlen = (uLong)n;
    rc = uncompress(dec, &dlen, comp, clen);
    check(rc == Z_OK, "uncompress returns Z_OK");
    check(dlen == (uLong)n && memcmp(dec, src, n) == 0, "one-shot round-trip matches original");
    printf("compressed %zu -> %lu bytes\n", n, (unsigned long)clen);

    /* 2. truncated stream must be rejected, not silently accepted */
    if (clen > 8) {
        dlen = (uLong)n;
        rc = uncompress(dec, &dlen, comp, clen / 2);
        check(rc != Z_OK, "truncated stream rejected with error");
    }

    /* 3. chunked streaming deflate / inflate */
    {
        z_stream zs;
        unsigned char *sbuf, *out;
        size_t cap, slen = 0, off = 0;
        memset(&zs, 0, sizeof zs);
        check(deflateInit(&zs, 6) == Z_OK, "deflateInit");
        cap = (size_t)bound + 4096;
        sbuf = (unsigned char *)malloc(cap);
        out = (unsigned char *)malloc(n + 1);
        while (sbuf != NULL && out != NULL) {
            int flush;
            zs.next_in = src + off;
            zs.avail_in = (uInt)((n - off) > 4096 ? 4096 : (n - off));
            off += zs.avail_in;
            flush = (off == n) ? Z_FINISH : Z_NO_FLUSH;
            do {
                zs.next_out = sbuf + slen;
                zs.avail_out = (uInt)((cap - slen) > 1024 ? 1024 : (cap - slen));
                rc = deflate(&zs, flush);
                slen = (size_t)zs.total_out;
            } while (zs.avail_out == 0);
            if (flush == Z_FINISH) break;
        }
        check(rc == Z_STREAM_END, "deflate produced a finished stream");
        deflateEnd(&zs);
        memset(&zs, 0, sizeof zs);
        check(inflateInit(&zs) == Z_OK, "inflateInit");
        zs.next_in = sbuf; zs.avail_in = (uInt)slen;
        zs.next_out = out; zs.avail_out = (uInt)(n + 1);
        rc = inflate(&zs, Z_FINISH);
        check(rc == Z_STREAM_END, "inflate reached Z_STREAM_END");
        check(zs.total_out == n && memcmp(out, src, n) == 0, "streaming round-trip matches original");
        inflateEnd(&zs);
        free(sbuf); free(out);
    }

    /* 4. gzip file round-trip through the gz* interface */
    {
        gzFile gz = gzopen(argv[2], "wb6");
        unsigned char magic[2] = {0, 0};
        FILE *raw;
        size_t off = 0;
        check(gz != NULL, "gzopen for write");
        if (gz != NULL) {
            while (off < n) {
                unsigned chunk = (unsigned)((n - off) > 8192 ? 8192 : (n - off));
                if (gzwrite(gz, src + off, chunk) != (int)chunk) { check(0, "gzwrite chunk"); break; }
                off += chunk;
            }
            check(gzclose(gz) == Z_OK, "gzclose after write");
        }
        raw = fopen(argv[2], "rb");
        if (raw != NULL) { size_t r = fread(magic, 1, 2, raw); (void)r; fclose(raw); }
        check(magic[0] == 0x1f && magic[1] == 0x8b, "gzip magic header present (1f 8b)");

        gz = gzopen(argv[2], "rb");
        check(gz != NULL, "gzopen for read");
        if (gz != NULL) {
            unsigned char *back = (unsigned char *)malloc(n + 1);
            int total = 0;
            int hit_eof = 0;
            while (back != NULL && total < (int)n) {
                unsigned want = (unsigned)((n - (size_t)total) > 8192 ? 8192 : (n - (size_t)total));
                int got = gzread(gz, back + total, want);
                if (got <= 0) break;
                total += got;
            }
            /* gzeof() only becomes true after a read attempt past the end, so the
             * byte count is verified first and a zero-length probe triggers EOF. */
            {
                unsigned char probe;
                int got = gzread(gz, &probe, 1);
                if (got == 0) hit_eof = 1;
            }
            check(total == (int)n && back != NULL && memcmp(back, src, n) == 0,
                  "gzread round-trip matches original");
            check(hit_eof && gzeof(gz) != 0, "gzeof reached after full read");
            check(gzclose(gz) == Z_OK, "gzclose after read");
            free(back);
        }
    }

    free(src); free(comp); free(dec);
    printf("consumer failures: %d\n", fails);
    return fails ? 1 : 0;
}
