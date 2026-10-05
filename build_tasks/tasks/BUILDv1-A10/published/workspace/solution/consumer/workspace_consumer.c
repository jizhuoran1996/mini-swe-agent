/* Reference copy of the consumer that main.py writes to /workspace/consumer/src and compiles
 * against the freshly installed libgit2. Kept here for review only; main.py embeds the same text. */
#include <git2.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv)
{
    if (argc < 2) { fprintf(stderr, "usage: consumer <repo-path>\n"); return 2; }
    git_libgit2_init();
    git_repository *repo = NULL;
    if (git_repository_init(&repo, argv[1], 0) < 0) return 1;
    git_repository_free(repo);
    git_libgit2_shutdown();
    return 0;
}
