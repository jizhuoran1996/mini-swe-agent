#!/usr/bin/env python3
"""Envoy core build + qualification driver (BUILDv1-D10).

Pipeline:
  1. verify the pinned Envoy source archive against the manifest,
  2. materialize the upstream SOURCE_VERSION distribution marker from the
     verified manifest commit so the unmodified, genuine
     `bazel/get_workspace_status` non-git branch is exercised,
  3. build //source/exe:envoy-static offline using the prepared Bazel caches,
  4. package the distribution under <output>/install,
  5. run the official //test/common/http:header_map_impl_test with test caching
     disabled and nonempty discovery/execution evidence,
  6. run an independent single-route local consumer against the packaged binary.

`doctor` reports the exact missing source/tool/dependency items and exits 78
when anything is missing, 0 when the environment is ready. `--help` builds nothing.

Bazel option placement: only genuine STARTUP options (notably --output_base)
precede the subcommand. Options such as --repository_cache, --config, --jobs
and --local_resources are command options and therefore follow `build` / `test`.

We deliberately DO NOT pass `--nofetch`. It blocks initialization of the Bazel
binary's bundled `@@bazel_tools` local repository (a local, network-free
operation). Remote fetches remain bounded by the repository cache + hydrated
external graph and, in this network=none container, fail honestly.

Workspace stamping: the tarball snapshot is not a git repo. The upstream
script `bazel/get_workspace_status` provides an EXPLICIT non-git distribution
door: if a `SOURCE_VERSION` file exists it echoes the recorded commit as
BUILD_SCM_REVISION instead of running git. We therefore write
`SOURCE_VERSION` under the extracted tree with the exact manifest commit
(after sha256 verification) and rely on that original upstream branch. No `.git`
is fabricated, `BAZEL_FAKE_SCM_REVISION` is not set, git is not shadowed, and no
commit/status value is invented.
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, os.environ.get('PYTHONPATH', ''))
import buildkit

HERE = Path(__file__).resolve().parent

CACHE_ROOT = Path('/workspace/cache')
REPO_CACHE = CACHE_ROOT / 'bazel_repository'
OUTPUT_BASE = CACHE_ROOT / 'bazel_output'
EXTERNAL_DIR = OUTPUT_BASE / 'external'
BAZEL_HOME = Path('/workspace/bazel-home')

BAZEL_CANDIDATES = ['/opt/bazel/7.6.0/bazel', 'bazel']
REQUIRED_TOOLS = ['python3', 'go', 'clang', 'clang++', 'ld.lld']


def expected_bazel_version(src):
    version_file = Path(src) / '.bazelversion'
    if version_file.is_file():
        return version_file.read_text().strip().splitlines()[0].strip()
    return None


def find_bazel():
    for candidate in BAZEL_CANDIDATES:
        found = candidate if Path(candidate).is_file() else shutil.which(candidate)
        if found:
            return found
    return None


def inspect(input_dir):
    input_dir = Path(input_dir).resolve()
    missing = []
    manifest = None
    mpath = input_dir / 'manifest.json'
    if not mpath.is_file():
        missing.append(f'manifest:{mpath}')
    else:
        try:
            manifest = json.loads(mpath.read_text())
        except Exception as exc:
            missing.append(f'manifest-unreadable:{mpath}:{exc}')
    if manifest:
        source = manifest.get('source', {})
        name = source.get('filename', 'source.tar.gz')
        archive = input_dir / name
        if not archive.is_file():
            missing.append(f'source-archive:{archive}')
        else:
            got = buildkit.digest(archive)
            if got != source.get('sha256'):
                missing.append(f'source-sha256-mismatch:{got}')
        if not source.get('commit'):
            missing.append('manifest-source-commit-missing')
    bazel = find_bazel()
    if not bazel:
        missing.append('tool:bazel(7.6.0 at /opt/bazel/7.6.0/bazel)')
    for tool in REQUIRED_TOOLS:
        if shutil.which(tool) is None and not Path(tool).is_file():
            missing.append(f'tool:{tool}')
    for path, label in [(REPO_CACHE, 'bazel_repository'),
                        (EXTERNAL_DIR, 'bazel_output/external')]:
        if not path.is_dir() or not any(path.iterdir()):
            missing.append(f'offline-cache:{label}:{path}')
    return missing, manifest


def command_doctor(args):
    missing, _ = inspect(args.input)
    sys.stdout.write(json.dumps({'ready': not missing, 'missing': missing}, indent=2) + '\n')
    return 78 if missing else 0


def startup_options():
    return [f'--output_base={OUTPUT_BASE}']


def build_options():
    return [
        f'--repository_cache={REPO_CACHE}',
        '--config=clang',
        '--jobs=4',
        '--local_resources=memory=24000',
    ]


def write_source_version(src, manifest, session):
    """Create the SOURCE_VERSION marker consumed by upstream get_workspace_status.

    The tarball has no .git, so the original status script would invoke `git`
    and fail. Upstream `bazel/get_workspace_status` has an explicit
    distribution branch that reads SOURCE_VERSION and echoes the recorded
    commit/sha. We write the *exact* manifest commit after the archive was
    sha256-verified in prepare(), and record the why/commit in build evidence.
    """
    commit = str(manifest['source']['commit']).strip()
    if len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
        raise ValueError(f'refusing to write non-sha1 SOURCE_VERSION: {commit!r}')
    marker = Path(src) / 'SOURCE_VERSION'
    marker.write_text(commit + '\n')
    session.write('source_version.json', {
        'file': 'SOURCE_VERSION',
        'commit': commit,
        'written_from': 'manifest.source.commit',
        'reason': ('Envoy source tarball is not a git checkout; upstream '
                   'bazel/get_workspace_status provides an explicit non-git '
                   'distribution branch keyed on SOURCE_VERSION. Supplying the '
                   'verified commit exercises that original branch instead of '
                   'invoking git, fabricating .git, or inventing values.'),
        'source_sha256': manifest['source']['sha256'],
        'upstream_script': 'bazel/get_workspace_status',
    })
    return marker


def command_run(args):
    missing, manifest = inspect(args.input)
    if missing:
        sys.stdout.write(json.dumps({'ready': False, 'missing': missing}, indent=2) + '\n')
        return 78

    session = buildkit.Session(args.input, args.output, jobs=args.jobs)
    session.prepare()
    src = session.src
    bazel = str(find_bazel())

    version_log = session.run([bazel, '--version'], cwd=src, phase='preflight',
                              name='bazel-version', timeout=120)
    want = expected_bazel_version(src)
    got = version_log.read_text(errors='replace').strip()
    if want and want not in got:
        raise RuntimeError(f'bazel version mismatch: want {want}, got {got!r}')

    # Write the upstream distribution marker from the verified commit.
    write_source_version(src, manifest, session)

    status_script = src / 'bazel' / 'get_workspace_status'
    if not status_script.is_file():
        raise RuntimeError('official bazel/get_workspace_status missing from source')

    BAZEL_HOME.mkdir(parents=True, exist_ok=True)
    env = {
        'HOME': str(BAZEL_HOME),
        'GOPROXY': 'off',
        'GOFLAGS': '-mod=mod',
        'GOMODCACHE': str(BAZEL_HOME / 'go-mod'),
        'GOCACHE': str(BAZEL_HOME / 'go-build'),
        'ENVOY_IP_TEST_VERSIONS': 'v4only',
        'BAZELISK_SKIP_WRAPPER': '1',
    }

    # 1. Compile the official static entry binary from source.
    session.run([bazel] + startup_options() + ['build'] + build_options() +
                ['-c', 'opt', '//source/exe:envoy-static'],
                cwd=src, phase='build', name='envoy-static', env=env, timeout=10800)
    built = src / 'bazel-bin' / 'source' / 'exe' / 'envoy-static'
    if not built.is_file():
        raise RuntimeError(f'envoy-static not produced at {built}')

    # 2. Package distribution.
    bindir = session.install / 'bin'
    bindir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(built, bindir / 'envoy')
    (bindir / 'envoy').chmod(0o755)
    conf = session.install / 'share' / 'envoy' / 'config'
    conf.mkdir(parents=True, exist_ok=True)
    shutil.copy2(HERE / 'envoy_bootstrap.yaml', conf / 'bootstrap.yaml')
    if (src / 'NOTICE').is_file():
        shutil.copy2(src / 'NOTICE', session.install / 'NOTICE')
    version = (src / 'VERSION.txt').read_text().strip() if (src / 'VERSION.txt').is_file() else 'unknown'
    session.write('delivery_metadata.json', {
        'task_id': manifest['task_id'], 'profile': manifest['profile'],
        'source_commit': manifest['source']['commit'],
        'source_sha256': manifest['source']['sha256'], 'envoy_version': version,
        'binary': 'install/bin/envoy', 'bazel': bazel, 'bazel_version': got,
        'build_jobs': session.jobs, 'test_jobs': 2, 'ip_mode': 'v4only',
        'nofetch_disabled': True,
        'workspace_status': 'SOURCE_VERSION-distribution-branch',
    })

    # 3. Official upstream unit test with caching disabled and real evidence.
    bep = session.output / 'header_map_impl_test.bep.json'
    session.test('header_map_impl_test',
                 [bazel] + startup_options() + ['test'] + build_options() + [
                     '-c', 'opt',
                     '--local_test_jobs=2',
                     '--nocache_test_results',
                     '--test_output=errors',
                     '--test_env=ENVOY_IP_TEST_VERSIONS=v4only',
                     f'--build_event_json_file={bep}',
                     '//test/common/http:header_map_impl_test'],
                 cwd=src, parser='gtest_cases', env=env, timeout=7200)

    # 4. Independent single-route consumer, run outside the source tree.
    result = session.output / 'consumer_result.json'
    session.run(['python3', str(HERE / 'consumer_check.py'),
                 '--envoy', str(bindir / 'envoy'),
                 '--config', str(conf / 'bootstrap.yaml'),
                 '--result', str(result)],
                cwd=session.consumer, phase='consumer', name='single_route',
                env=env, timeout=900)
    payload = json.loads(result.read_text())
    if not payload.get('passed'):
        raise RuntimeError(f'consumer verification failed: {payload}')

    # 5. Installed-binary identity check as a second consumer.
    session.test('install_binary_identity',
                 [str(bindir / 'envoy'), '--version'],
                 cwd=session.consumer, parser='auto', env=env, timeout=120)

    session.finish(features={
        'binary': 'install/bin/envoy',
        'official_targets': ['//source/exe:envoy-static',
                             '//test/common/http:header_map_impl_test'],
        'consumer': payload, 'ip_mode': 'v4only',
        'bazel_version': got, 'build_jobs': session.jobs, 'test_jobs': 2,
        'bazel_tools_local_repo_initialized': True,
        'workspace_status': 'SOURCE_VERSION-distribution-branch',
        'source_version_commit': manifest['source']['commit'],
    })
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog='main.py', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command')
    run_p = sub.add_parser('run', help='verify, build, test and package Envoy')
    run_p.add_argument('--input', default='input')
    run_p.add_argument('--output', default='output')
    run_p.add_argument('--jobs', type=int, default=4)
    doc_p = sub.add_parser('doctor', help='report missing source/tool/dependency items')
    doc_p.add_argument('--input', default='input')
    doc_p.add_argument('--output', default='output')
    args = parser.parse_args(argv)
    if args.command == 'doctor':
        return command_doctor(args)
    if args.command == 'run':
        return command_run(args)
    parser.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
