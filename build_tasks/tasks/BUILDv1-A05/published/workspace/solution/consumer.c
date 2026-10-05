#include <openssl/evp.h>
#include <openssl/pem.h>
#include <openssl/opensslv.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Standalone EVP digest + RSA signature verifier, compiled against the
 * freshly installed OpenSSL prefix. Return 0 on successful verification. */

static unsigned char *slurp(const char *p, size_t *n)
{
    FILE *f = fopen(p, "rb");
    unsigned char *b;
    long s;
    if (!f) return NULL;
    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return NULL; }
    s = ftell(f);
    if (s < 0) { fclose(f); return NULL; }
    rewind(f);
    b = malloc((size_t)s + 1);
    if (!b) { fclose(f); return NULL; }
    if (fread(b, 1, (size_t)s, f) != (size_t)s) { fclose(f); free(b); return NULL; }
    fclose(f);
    *n = (size_t)s;
    return b;
}

int main(int argc, char **argv)
{
    static const unsigned char want[32] = {
        0xb9,0x4d,0x27,0xb9,0x93,0x4d,0x3e,0x08,0xa5,0x2e,0x52,0xd7,0xda,0x7d,0xab,0xfa,
        0xc4,0x84,0xef,0xe3,0x7a,0x53,0x80,0xee,0x90,0x88,0xf7,0xac,0xe2,0xef,0xcd,0xe9};
    unsigned char md[32];
    unsigned int mdlen = 0;
    EVP_MD_CTX *c, *v;
    EVP_PKEY *pk;
    FILE *kf;
    size_t mlen = 0, slen = 0;
    unsigned char *msg, *sig;
    int ok = 0;

    printf("OpenSSL %s\n", OpenSSL_version(OPENSSL_VERSION));
    if (argc != 4) { fprintf(stderr, "usage: %s pub.pem msg sig\n", argv[0]); return 2; }

    c = EVP_MD_CTX_new();
    if (!c) return 1;
    if (EVP_DigestInit_ex(c, EVP_sha256(), NULL) != 1 ||
        EVP_DigestUpdate(c, "hello world", 11) != 1 ||
        EVP_DigestFinal_ex(c, md, &mdlen) != 1) { EVP_MD_CTX_free(c); return 1; }
    EVP_MD_CTX_free(c);
    if (mdlen != 32 || memcmp(md, want, 32) != 0) {
        fprintf(stderr, "sha256 mismatch\n");
        return 1;
    }
    printf("sha256(hello world) OK\n");

    kf = fopen(argv[1], "r");
    if (!kf) { fprintf(stderr, "no pubkey\n"); return 1; }
    pk = PEM_read_PUBKEY(kf, NULL, NULL, NULL);
    fclose(kf);
    if (!pk) { fprintf(stderr, "bad pubkey\n"); return 1; }

    msg = slurp(argv[2], &mlen);
    sig = slurp(argv[3], &slen);
    if (!msg || !sig) { EVP_PKEY_free(pk); free(msg); free(sig); return 1; }

    v = EVP_MD_CTX_new();
    if (v && EVP_DigestVerifyInit(v, NULL, EVP_sha256(), NULL, pk) == 1)
        ok = EVP_DigestVerify(v, sig, slen, msg, mlen) == 1;
    if (v) EVP_MD_CTX_free(v);
    EVP_PKEY_free(pk);
    free(msg);
    free(sig);
    if (ok) { printf("signature verify OK\n"); return 0; }
    printf("signature verify FAILED\n");
    return 1;
}
