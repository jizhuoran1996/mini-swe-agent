/* Independent consumer for the freshly built PCRE2 POSIX wrapper. */
#include <pcre2posix.h>
#include <stdio.h>

int main(void)
{
    regex_t re;
    int failures = 0;
    int rc = regcomp(&re, "^[0-9]+$", REG_EXTENDED);

    if (rc != 0) {
        fprintf(stderr, "regcomp failed: %d\n", rc);
        return 1;
    }
    if (regexec(&re, "12345", 0, NULL, 0) != 0) {
        fprintf(stderr, "FAIL: expected match for 12345\n");
        failures++;
    }
    if (regexec(&re, "12a45", 0, NULL, 0) == 0) {
        fprintf(stderr, "FAIL: expected no match for 12a45\n");
        failures++;
    }
    regfree(&re);

    if (failures != 0) {
        printf("CONSUMER_POSIX FAIL\n");
        return 1;
    }
    printf("CONSUMER_POSIX OK\n");
    return 0;
}
