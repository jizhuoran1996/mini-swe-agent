/* Independent C consumer for the freshly installed libarchive (BUILDv1-A03).
 *
 * Reads an archive with the public archive_read_* API and prints one
 * tab-separated record per member:
 *
 *   ENTRY<TAB>name<TAB>kind<TAB>size<TAB>hardlink<TAB>symlink<TAB>fnv1a64
 *   TOTAL<TAB>entry-count
 *
 * Exits non-zero when the archive cannot be opened or parsed, so a corrupt
 * archive is an explicit failure rather than a partial delivery.
 */

#include <archive.h>
#include <archive_entry.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

static unsigned long long fnv1a(const unsigned char *p, size_t n,
                                unsigned long long h)
{
	for (size_t i = 0; i < n; i++) {
		h ^= (unsigned long long)p[i];
		h *= 1099511628211ULL;
	}
	return h;
}

int main(int argc, char **argv)
{
	struct archive *a;
	struct archive_entry *entry;
	int rc, count = 0, status = 0;

	if (argc != 2) {
		fprintf(stderr, "usage: %s ARCHIVE\n", argv[0]);
		return 2;
	}

	a = archive_read_new();
	archive_read_support_filter_all(a);
	archive_read_support_format_all(a);
	if (archive_read_open_filename(a, argv[1], 65536) != ARCHIVE_OK) {
		fprintf(stderr, "ERROR open: %s\n", archive_error_string(a));
		archive_read_free(a);
		return 1;
	}

	while ((rc = archive_read_next_header(a, &entry)) == ARCHIVE_OK) {
		const char *name = archive_entry_pathname(entry);
		const char *hard = archive_entry_hardlink(entry);
		const char *soft = archive_entry_symlink(entry);
		mode_t type = archive_entry_filetype(entry);
		long long size = (long long)archive_entry_size(entry);
		const char *kind;
		unsigned long long hash = 1469598103934665603ULL;

		if (hard != NULL)
			kind = "hardlink";
		else if (soft != NULL)
			kind = "symlink";
		else if (S_ISDIR(type))
			kind = "dir";
		else if (S_ISREG(type))
			kind = "file";
		else
			kind = "other";

		if (strcmp(kind, "file") == 0) {
			char buf[16384];
			ssize_t got;
			while ((got = archive_read_data(a, buf, sizeof(buf))) > 0)
				hash = fnv1a((const unsigned char *)buf, (size_t)got, hash);
			if (got < 0) {
				fprintf(stderr, "ERROR data: %s\n", archive_error_string(a));
				status = 1;
			}
		}

		printf("ENTRY\t%s\t%s\t%lld\t%s\t%s\t%016llx\n",
		    name, kind, size,
		    hard != NULL ? hard : "",
		    soft != NULL ? soft : "",
		    hash);
		count++;
	}

	if (rc != ARCHIVE_EOF) {
		fprintf(stderr, "ERROR header: %s\n", archive_error_string(a));
		status = 1;
	}

	printf("TOTAL\t%d\n", count);
	archive_read_free(a);
	return status;
}
