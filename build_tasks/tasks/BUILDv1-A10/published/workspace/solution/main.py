#!/usr/bin/env python3
"""BUILDv1-A10: build, test, install libgit2 v1.9.1 and verify an independent C consumer."""
import argparse
import json
import re
import shutil
from pathlib import Path

from buildkit import Session, digest

CONSUMER_C = r'''
#include <git2.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CK(expr) do { int _e = (expr); if (_e < 0) { \
    const git_error *_g = git_error_last(); \
    fprintf(stderr, "FAIL %s: %s\n", #expr, _g ? _g->message : "unknown"); \
    exit(1); } } while (0)

int main(int argc, char **argv)
{
    if (argc < 2) { fprintf(stderr, "usage: consumer <repo-path>\n"); return 2; }
    CK(git_libgit2_init());

    git_repository *repo = NULL;
    CK(git_repository_init(&repo, argv[1], 0));

    git_signature *sig = NULL;
    CK(git_signature_new(&sig, "Task Author", "author@example.invalid", 1700000000, 0));

    const char *blob_text[2] = { "hello\n", "hello world\n" };
    git_oid commits[2];
    git_oid tree_ids[2];

    for (int i = 0; i < 2; i++) {
        git_oid blob;
        CK(git_blob_create_from_buffer(&blob, repo, blob_text[i], strlen(blob_text[i])));
        git_treebuilder *tb = NULL;
        CK(git_treebuilder_new(&tb, repo, NULL));
        CK(git_treebuilder_insert(NULL, tb, "a.txt", &blob, GIT_FILEMODE_BLOB));
        CK(git_treebuilder_write(&tree_ids[i], tb));
        git_treebuilder_free(tb);

        git_tree *tree = NULL;
        CK(git_tree_lookup(&tree, repo, &tree_ids[i]));

        git_commit *parent = NULL;
        git_commit *parents[1];
        int nparents = 0;
        if (i > 0) {
            CK(git_commit_lookup(&parent, repo, &commits[0]));
            parents[0] = parent;
            nparents = 1;
        }
        char msg[32];
        snprintf(msg, sizeof(msg), "commit %d\n", i + 1);
        CK(git_commit_create(&commits[i], repo, "HEAD", sig, sig, NULL, msg,
                             tree, nparents, parents));
        if (parent) git_commit_free(parent);
        git_tree_free(tree);
    }

    char hex1[64] = {0}, hex2[64] = {0};
    git_oid_tostr(hex1, sizeof(hex1), &commits[0]);
    git_oid_tostr(hex2, sizeof(hex2), &commits[1]);
    printf("commit1=%s\n", hex1);
    printf("commit2=%s\n", hex2);

    git_tree *t1 = NULL, *t2 = NULL;
    CK(git_tree_lookup(&t1, repo, &tree_ids[0]));
    CK(git_tree_lookup(&t2, repo, &tree_ids[1]));
    git_diff *diff = NULL;
    CK(git_diff_tree_to_tree(&diff, repo, t1, t2, NULL));
    printf("diff_deltas=%zu\n", git_diff_num_deltas(diff));
    git_diff_free(diff);
    git_tree_free(t2);

    {
        git_oid bogus;
        git_commit *bogus_commit = NULL;
        CK(git_oid_fromstr(&bogus, "0123456789abcdef0123456789abcdef01234567"));
        if (git_commit_lookup(&bogus_commit, repo, &bogus) == 0) {
            fprintf(stderr, "expected lookup of nonexistent commit to fail\n");
            return 3;
        }
        printf("bogus_lookup_failed=yes\n");
    }

    CK(git_repository_set_head_detached(repo, &commits[0]));
    git_checkout_options co = GIT_CHECKOUT_OPTIONS_INIT;
    co.checkout_strategy = GIT_CHECKOUT_FORCE;
    CK(git_checkout_head(repo, &co));

    const char *workdir = git_repository_workdir(repo);
    char path[4096];
    snprintf(path, sizeof(path), "%sa.txt", workdir);
    FILE *f = fopen(path, "rb");
    if (!f) { fprintf(stderr, "cannot open %s\n", path); return 4; }
    char buf[64] = {0};
    size_t n = fread(buf, 1, sizeof(buf) - 1, f);
    fclose(f);
    buf[n] = 0;
    printf("worktree_a.txt=%s", buf);
    if (strcmp(buf, "hello\n") != 0) {
        fprintf(stderr, "unexpected worktree content after checkout\n");
        return 5;
    }
    printf("restored=yes\n");

    git_tree_free(t1);
    git_signature_free(sig);
    git_repository_free(repo);
    CK(git_libgit2_shutdown());
    return 0;
}
'''


def _tool(name):
    return shutil.which(name)


def do_doctor(input_dir):
    inp = Path(input_dir)
    checks = []

    def add(item, ok, detail=''):
        checks.append({'item': item, 'ok': bool(ok), 'detail': detail})

    manifest = inp / 'manifest.json'
    add('manifest.json', manifest.is_file(), str(manifest))
    if manifest.is_file():
        try:
            meta = json.loads(manifest.read_text())
            archive = inp / meta['source']['filename']
            if archive.is_file():
                actual = digest(archive)
                expected = meta['source']['sha256']
                add('source archive sha256', actual == expected, actual)
            else:
                add('source archive', False, str(archive))
        except Exception as exc:  # noqa: BLE001 - report any manifest problem verbatim
            add('manifest parse', False, str(exc))
    for tool in ['cmake', 'cc', 'gcc', 'make', 'python3', 'git', 'ldd']:
        found = _tool(tool)
        add('tool:' + tool, found is not None, found or 'not found')

    ok = all(c['ok'] for c in checks)
    report = {'task_id': 'BUILDv1-A10', 'ready': ok, 'checks': checks,
              'missing': [c['item'] for c in checks if not c['ok']]}
    print(json.dumps(report, indent=2))
    return 0 if ok else 78


TEST_NAME = re.compile(r'^([A-Za-z0-9_]+)::([A-Za-z0-9_:]+)(.*)$')


def _strip_ctest_prefix(text):
    """ctest -V prefixes every test-stdout line with '<n>: '; remove only that."""
    out = []
    for raw in text.splitlines():
        match = re.match(r'^\s*\d+:\s?(.*)$', raw)
        out.append(match.group(1) if match else raw)
    return out


def _first_int(pattern, text):
    match = re.search(pattern, text)
    return int(match.group(1)) if match else None


def parse_clar(text):
    """Parse Clar's verbose output out of a ctest -V transcript.

    Clar (invoked by add_clar_test as `libgit2_tests -v -xonline`) prints one line per
    executed test, of the form `<suite>::<case>` followed by progress markers:
    '.' passed, 'S' skipped, 'F'/'E' failed. The CTest-level selector `offline` is a
    single aggregate test and must never be reported as the case count.
    """
    lines = _strip_ctest_prefix(text)
    body = '\n'.join(lines)

    suites, names, seen = set(), [], set()
    passed = skipped = failed = captured = 0
    for line in lines:
        stripped = line.strip()
        match = TEST_NAME.match(stripped)
        if not match:
            continue
        full = match.group(1) + '::' + match.group(2)
        if full in seen:
            continue
        seen.add(full)
        names.append(full)
        suites.add(match.group(1))
        tail = match.group(3).strip()
        last = tail[-1] if tail else ''
        if last == '.':
            passed += 1
            captured += 1
        elif last == 'S':
            skipped += 1
            captured += 1
        elif last in ('F', 'E'):
            failed += 1
            captured += 1

    summary_tests = _first_int(r'Executed\s+(\d+)\s+tests', body)
    summary_suites = _first_int(r'Loaded\s+(\d+)\s+suites', body)
    assertions = _first_int(r'(\d+)\s+assertions?\b', body)
    summary_failed = _first_int(r'(\d+)\s+(?:tests?\s+)?fail(?:ed|ures)', body)

    tests = len(names) or summary_tests
    result = {
        'selector': 'offline',
        'aggregate_ctest_tests': 1,
        'suites': len(suites) or summary_suites,
        'tests': tests,
        'passed': passed if captured else None,
        'skipped': skipped if captured else None,
        'failed': summary_failed if summary_failed is not None else (failed if captured else None),
        'statuses_captured': captured,
        'assertions': assertions,
        'clar_summary_lines': {'executed': summary_tests, 'loaded_suites': summary_suites},
        'parse_source': ('clar per-test status characters' if captured
                         else 'clar test-name lines'),
        'sample_tests': names[:5],
        'all_tests': names,
    }
    return result


def do_run(args):
    sess = Session(args.input, args.output, args.jobs)
    sess.prepare()
    src, build, install = sess.src, sess.build, sess.install

    sess.run(['cmake', '-S', str(src), '-B', str(build),
              '-DCMAKE_BUILD_TYPE=Release',
              '-DCMAKE_INSTALL_PREFIX=' + str(install),
              '-DBUILD_TESTS=ON', '-DBUILD_EXAMPLES=ON', '-DBUILD_CLI=OFF',
              '-DUSE_HTTPS=OpenSSL', '-DUSE_SSH=OFF'],
             cwd=src, phase='configure', name='cmake_configure', timeout=1800)

    sess.run(['cmake', '--build', str(build), '--parallel', str(sess.jobs)],
             cwd=build, phase='build', name='cmake_build', timeout=5400)

    inventory = sess.run(['ctest', '--test-dir', str(build), '-N', '-R', '^offline$'],
                         cwd=build, phase='inventory', name='ctest_inventory', timeout=300)
    shutil.copyfile(inventory, sess.output / 'ctest_inventory.txt')

    log = sess.test('offline-clar',
                    ['ctest', '--test-dir', str(build), '-R', '^offline$',
                     '-V', '--output-on-failure'],
                    cwd=build, parser='ctest_cases', timeout=5400)

    clar = parse_clar(log.read_text(errors='replace'))
    if not clar['tests']:
        raise RuntimeError('Could not parse any Clar case from the verbose CTest log; '
                           'the aggregate CTest selector is not a case count')
    (sess.output / 'clar_test_inventory.txt').write_text(
        '\n'.join(clar.pop('all_tests')) + '\n')
    clar['ctest_inventory'] = 'ctest_inventory.txt'
    clar['log'] = str(log.relative_to(sess.output))
    sess.write('clar_summary.json', clar)

    sess.run(['cmake', '--install', str(build)],
             cwd=build, phase='install', name='cmake_install', timeout=900)

    cdir = Path('/workspace/consumer')
    csrc = cdir / 'src'
    csrc.mkdir(parents=True, exist_ok=True)
    source = csrc / 'workspace_consumer.c'
    source.write_text(CONSUMER_C)
    work = cdir / 'work'
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    repo_path = work / 'repo'
    exe = cdir / 'workspace_consumer'

    sess.run(['cc', '-O2', '-Wall', '-Wextra', str(source),
              '-I', str(install / 'include'), '-L', str(install / 'lib'), '-lgit2',
              '-Wl,-rpath,' + str(install / 'lib'), '-o', str(exe)],
             cwd=csrc, phase='consumer_build', name='consumer_cc', timeout=600)

    link_log = sess.run(['ldd', str(exe)], cwd=csrc, phase='consumer_link',
                        name='consumer_ldd', timeout=120).read_text()
    installed_so = str(install / 'lib')
    if installed_so not in link_log:
        raise RuntimeError('consumer is not linked against the installed library:\n' + link_log)

    run_log = sess.run([str(exe), str(repo_path)], cwd=work, phase='consumer_run',
                       name='consumer_run', timeout=300).read_text(errors='replace')
    values = dict(re.findall(r'^(\w+)=(.*)$', run_log, re.M))
    c1, c2 = values.get('commit1'), values.get('commit2')
    if not c1 or not c2 or values.get('diff_deltas') != '1' \
            or values.get('bogus_lookup_failed') != 'yes' \
            or values.get('restored') != 'yes':
        raise RuntimeError('consumer assertions failed:\n' + run_log)

    head = sess.run(['git', '-C', str(repo_path), 'rev-parse', 'HEAD'],
                    cwd=work, phase='verify', name='git_head', timeout=120)
    if head.read_text().strip() != c1:
        raise RuntimeError('detached HEAD does not match the restored commit1')

    for label, oid in [('commit1', c1), ('commit2', c2)]:
        sess.run(['git', '-C', str(repo_path), 'cat-file', '-e', oid],
                 cwd=work, phase='verify', name='git_catfile_' + label, timeout=120)

    restored = (repo_path / 'a.txt').read_text()
    if restored != 'hello\n':
        raise RuntimeError('worktree was not restored to the old version: ' + repr(restored))

    report = {'consumer_stdout': run_log, 'commits': [c1, c2],
              'restored_head': head.read_text().strip(), 'worktree_a_txt': restored,
              'ldd_snippet': [line for line in link_log.splitlines() if 'git2' in line],
              'link_root': installed_so}
    sess.write('consumer_verification.json', report)

    sess.finish(features={'c_library': 'libgit2-1.9.1', 'https_backend': 'OpenSSL',
                          'ssh_support': 'off', 'ctest_selector': 'offline',
                          'clar_suites': clar['suites'], 'clar_tests': clar['tests'],
                          'clar_passed': clar['passed'], 'clar_skipped': clar['skipped'],
                          'clar_failed': clar['failed'],
                          'independent_consumer': True,
                          'consumer_commits': [c1, c2]})
    print(json.dumps({'status': 'ok', 'commits': [c1, c2],
                      'clar_suites': clar['suites'], 'clar_tests': clar['tests']}, indent=2))
    return 0


def main():
    parser = argparse.ArgumentParser(prog='buildv1-a10',
                                     description='Build/test/install libgit2 and verify a consumer.')
    sub = parser.add_subparsers(dest='command')
    run = sub.add_parser('run', help='build, test, install and verify')
    run.add_argument('--input', required=True)
    run.add_argument('--output', required=True)
    run.add_argument('--jobs', type=int, default=4)
    doc = sub.add_parser('doctor', help='list missing source/tool/dependency items')
    doc.add_argument('--input', required=True)
    args = parser.parse_args()
    if args.command == 'run':
        return do_run(args)
    if args.command == 'doctor':
        return do_doctor(args.input)
    parser.print_help()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
