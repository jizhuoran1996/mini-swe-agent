/* Independent consumer for the freshly built PCRE2 8-bit library. */
#define PCRE2_CODE_UNIT_WIDTH 8
#include <pcre2.h>
#include <stdio.h>
#include <string.h>

static int failures;

#define CHECK(cond, msg) do { if (!(cond)) { fprintf(stderr, "FAIL: %s\n", msg); failures++; } } while (0)

int main(void)
{
    char version[64];
    unsigned int jit = 99, unicode = 0;
    int errcode = 0, rc;
    PCRE2_SIZE erroffset = 0;
    pcre2_code *re, *bad;
    pcre2_match_data *md;
    const char *subject = "caf\xc3\xa9-42";   /* UTF-8 "caf\xc3\xa9-42" */

    memset(version, 0, sizeof(version));
    if (pcre2_config(PCRE2_CONFIG_VERSION, version) > 0)
        printf("VERSION=%s\n", version);
    pcre2_config(PCRE2_CONFIG_JIT, &jit);
    printf("JIT=%u\n", jit);
    pcre2_config(PCRE2_CONFIG_UNICODE, &unicode);
    printf("UNICODE=%u\n", unicode);

    CHECK(jit == 0, "core profile requires JIT to be disabled");
    CHECK(unicode == 1, "core profile requires Unicode support");

    re = pcre2_compile((PCRE2_SPTR)"(\\p{L}+)-(\\d+)", PCRE2_ZERO_TERMINATED,
                       PCRE2_UTF | PCRE2_UCP, &errcode, &erroffset, NULL);
    CHECK(re != NULL, "compile UTF/UCP pattern");
    if (re == NULL) {
        fprintf(stderr, "compile error %d at %zu\n", errcode, (size_t)erroffset);
        return 1;
    }

    md = pcre2_match_data_create_from_pattern(re, NULL);
    CHECK(md != NULL, "allocate match data");
    if (md != NULL) {
        rc = pcre2_match(re, (PCRE2_SPTR)subject, strlen(subject), 0, 0, md, NULL);
        CHECK(rc == 3, "expected 3 capture slots");
        if (rc == 3) {
            PCRE2_SIZE *ov = pcre2_get_ovector_pointer(md);
            CHECK(ov[2] == 0 && ov[3] == 5, "group 1 spans the UTF-8 word");
            CHECK(ov[4] == 6 && ov[5] == 8, "group 2 spans the digits");
        }
        rc = pcre2_match(re, (PCRE2_SPTR)"nope", 4, 0, 0, md, NULL);
        CHECK(rc == PCRE2_ERROR_NOMATCH, "expected NOMATCH for non-matching subject");
        pcre2_match_data_free(md);
    }
    pcre2_code_free(re);

    bad = pcre2_compile((PCRE2_SPTR)"(", PCRE2_ZERO_TERMINATED, 0, &errcode, &erroffset, NULL);
    CHECK(bad == NULL && errcode != 0, "invalid pattern must be rejected");
    if (bad != NULL) pcre2_code_free(bad);

    if (failures != 0) {
        printf("CONSUMER8 FAIL %d\n", failures);
        return 1;
    }
    printf("CONSUMER8 OK\n");
    return 0;
}
