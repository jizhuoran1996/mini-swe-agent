#!/usr/bin/env python3
"""BUILDv1-B08 core profile: build Go 1.24.4 from source, install it, run the
frozen official package tests, and verify the delivered toolchain with an
out-of-tree consumer module."""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.environ.get('PYTHONPATH', '/workspace'))
import buildkit  # noqa: E402

PIN_VERSION = 'go1.24.4'
# Upstream Go requires the bootstrap toolchain to be at least go1.22.6
# (see https://go.dev/doc/install/source for go1.24.x).
MIN_BOOTSTRAP = (1, 22, 6)
CORE_PACKAGES = ['bytes', 'strings', 'encoding/json', 'compress/gzip']

MAIN_GO = '''package main

import (
	"bytes"
	"compress/gzip"
	"encoding/json"
	"fmt"
	"strings"
)

type Rec struct {
	Name string
	N    int
}

func RoundTrip(name string, n int) (string, error) {
	var buf bytes.Buffer
	w := gzip.NewWriter(&buf)
	data, err := json.Marshal(Rec{name, n})
	if err != nil {
		return "", err
	}
	if _, err := w.Write(data); err != nil {
		return "", err
	}
	if err := w.Close(); err != nil {
		return "", err
	}
	r, err := gzip.NewReader(bytes.NewReader(buf.Bytes()))
	if err != nil {
		return "", err
	}
	var dec Rec
	if err := json.NewDecoder(r).Decode(&dec); err != nil {
		return "", err
	}
	return strings.ToUpper(dec.Name), nil
}

func Fan(n int) int {
	ch := make(chan int, n)
	for i := 0; i < n; i++ {
		go func(i int) { ch <- i * i }(i)
	}
	sum := 0
	for i := 0; i < n; i++ {
		sum += <-ch
	}
	return sum
}

func main() {
	s, err := RoundTrip("go", 7)
	if err != nil {
		panic(err)
	}
	fmt.Printf("roundtrip=%s fan=%d\\n", s, Fan(10))
}
'''

MAIN_TEST_GO = '''package main

import "testing"

func TestRoundTrip(t *testing.T) {
	s, err := RoundTrip("client", 42)
	if err != nil {
		t.Fatal(err)
	}
	if s != "CLIENT" {
		t.Fatalf("got %q", s)
	}
}

func TestFan(t *testing.T) {
	if got := Fan(10); got != 285 {
		t.Fatalf("got %d", got)
	}
}
'''


def bootstrap_version(root):
    """Return (major, minor, patch) for a candidate GOROOT, or None."""
    go_bin = Path(root) / 'bin' / 'go'
    if not go_bin.is_file():
        return None
    env = os.environ.copy()
    env['GOTOOLCHAIN'] = 'local'
    env.pop('GOROOT_BOOTSTRAP', None)
    try:
        out = subprocess.run([str(go_bin), 'version'], env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    match = re.search(r'go(\d+)\.(\d+)(?:\.(\d+))?', out.stdout.decode(errors='replace'))
    if not match:
        return None
    major, minor, patch = match.group(1), match.group(2), match.group(3) or '0'
    return (int(major), int(minor), int(patch))


def version_ok(version):
    return version is not None and version >= MIN_BOOTSTRAP


def resolve_bootstrap(explicit=None):
    """Select a bootstrap GOROOT meeting the >=1.22.6 requirement.

    Preference order: explicit --bootstrap, GOROOT_BOOTSTRAP env,
    /opt/bootstrap/go (supplied by the official runtime), then common
    system locations. Candidates that fail the version gate are reported
    but never selected.
    """
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    if os.environ.get('GOROOT_BOOTSTRAP'):
        candidates.append(Path(os.environ['GOROOT_BOOTSTRAP']))
    candidates.append(Path('/opt/bootstrap/go'))
    for c in ['/usr/local/go', '/usr/lib/go', '/usr/lib/go-1.24',
              '/usr/lib/go-1.23', '/usr/lib/go-1.22', '/opt/go']:
        candidates.append(Path(c))
    which = shutil.which('go')
    if which:
        candidates.append(Path(which).resolve().parent.parent)

    seen = set()
    rejected = []
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if not (candidate / 'bin' / 'go').is_file():
            continue
        version = bootstrap_version(candidate)
        if version_ok(version):
            return candidate, version, rejected
        rejected.append((candidate, version))
    return None, None, rejected


def find_bootstrap(explicit=None):
    root, _version, _rejected = resolve_bootstrap(explicit)
    return root


def doctor(input_dir, stream=sys.stdout):
    ok = True
    input_dir = Path(input_dir)
    manifest_path = input_dir / 'manifest.json'
    if not manifest_path.is_file():
        print(f'source_manifest: MISSING {manifest_path}', file=stream)
        return False
    manifest = json.loads(manifest_path.read_text())
    archive = input_dir / manifest['source']['filename']
    if not archive.is_file():
        print(f'source_archive: MISSING {archive}', file=stream)
        ok = False
    else:
        digest = buildkit.digest(archive)
        if digest != manifest['source']['sha256']:
            print(f'source_archive: SHA256 MISMATCH got {digest}', file=stream)
            ok = False
        else:
            print(f'source_archive: OK {archive} sha256={digest}', file=stream)

    required = '.'.join(str(n) for n in MIN_BOOTSTRAP)
    root, version, rejected = resolve_bootstrap()
    if root is not None:
        print(f'bootstrap_go: OK {root} version=go{version[0]}.{version[1]}.{version[2]} '
              f'(min {required})', file=stream)
    else:
        print(f'bootstrap_go: MISSING (need Go>={required} with bin/go and src/runtime)',
              file=stream)
        for cand, ver in rejected:
            shown = 'unknown' if ver is None else f'{ver[0]}.{ver[1]}.{ver[2]}'
            print(f'bootstrap_go.rejected: {cand} version={shown} (< {required})', file=stream)
        ok = False

    for tool, required_tool in [('bash', True), ('gcc', True), ('ar', True),
                                ('cc', False), ('g++', False)]:
        which = shutil.which(tool)
        if which:
            print(f'tool.{tool}: OK {which}', file=stream)
        else:
            print(f'tool.{tool}: MISSING', file=stream)
            if required_tool:
                ok = False
    return ok


def project_env(sess, base_home):
    home = sess.build / base_home
    gopath = sess.build / 'gopath'
    home.mkdir(parents=True, exist_ok=True)
    gopath.mkdir(parents=True, exist_ok=True)
    return {
        'HOME': str(home),
        'GOPATH': str(gopath),
        'GOTOOLCHAIN': 'local',
        'GOPROXY': 'off',
        'GOFLAGS': '',
        'GO111MODULE': 'on',
        'CGO_ENABLED': '0',
        'GOMAXPROCS': '2',
        'CC': os.environ.get('CC', 'gcc'),
        'CXX': os.environ.get('CXX', 'g++'),
        'PATH': os.environ.get('PATH', '/usr/local/bin:/usr/bin:/bin'),
    }


def parse_go_test_json(log_path):
    package_pass = set()
    test_pass = set()
    cached = 0
    for line in log_path.read_text(errors='replace').splitlines():
        line = line.strip()
        if not line.startswith('{'):
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        action = obj.get('Action')
        pkg = obj.get('Package')
        test = obj.get('Test')
        if action == 'pass' and pkg and test:
            test_pass.add((pkg, test))
        elif action == 'pass' and pkg and not test:
            package_pass.add(pkg)
        elif action == 'output':
            if 'cached' in (obj.get('Output') or '').lower():
                cached += 1
    return package_pass, test_pass, cached


def cmd_run(args):
    sess = buildkit.Session(args.input, args.output, jobs=args.jobs)
    sess.prepare()

    bootstrap, bs_version, rejected = resolve_bootstrap(getattr(args, 'bootstrap', None))
    if bootstrap is None:
        lines = ['bootstrap Go toolchain >=1.22.6 not found (run doctor)']
        for cand, ver in rejected:
            shown = 'unknown' if ver is None else f'{ver[0]}.{ver[1]}.{ver[2]}'
            lines.append(f'  rejected {cand} (version {shown})')
        raise SystemExit('\n'.join(lines))

    build_env = project_env(sess, 'home')
    build_env['GOROOT_BOOTSTRAP'] = str(bootstrap)
    build_env['GOCACHE'] = str(sess.build / 'gocache_build')
    build_env['GOMAXPROCS'] = str(sess.jobs)
    (sess.build / 'gocache_build').mkdir(parents=True, exist_ok=True)

    sess.run([str(bootstrap / 'bin' / 'go'), 'version'], cwd=str(sess.build),
             phase='probe', name='bootstrap_version', env=build_env, timeout=120)

    sess.run(['bash', './make.bash'], cwd=str(sess.src / 'src'), phase='build',
             name='make.bash', env=build_env, timeout=7200)

    built_go = sess.src / 'bin' / 'go'
    if not built_go.is_file():
        raise SystemExit('make.bash did not produce src/bin/go')
    version_log = sess.run([str(built_go), 'version'], cwd=str(sess.src),
                           phase='verify', name='target_go_version',
                           env=build_env, timeout=120)
    if PIN_VERSION not in version_log.read_text():
        raise SystemExit('target toolchain version mismatch, expected ' + PIN_VERSION)

    ignore = shutil.ignore_patterns('.git', '.gitignore', '.gitattributes')
    shutil.copytree(sess.src, sess.install, dirs_exist_ok=True,
                    symlinks=True, ignore=ignore)
    install_go = sess.install / 'bin' / 'go'

    verify_env = dict(build_env)
    verify_env['GOROOT'] = str(sess.install)
    sess.run([str(install_go), 'version'], cwd=str(sess.install),
             phase='verify', name='installed_go_version', env=verify_env, timeout=120)
    sess.run([str(install_go), 'env', 'GOROOT', 'GOTOOLDIR', 'GOVERSION', 'GOOS',
              'GOARCH', 'GOHOSTOS', 'GOHOSTARCH', 'CGO_ENABLED'],
             cwd=str(sess.build), phase='verify', name='toolchain_identity',
             env=verify_env, timeout=120)

    test_env = dict(build_env)
    test_env['GOROOT'] = str(sess.install)
    test_env['GOCACHE'] = str(sess.build / 'gocache_test')
    test_env['GOFLAGS'] = '-p=2'
    (sess.build / 'gocache_test').mkdir(parents=True, exist_ok=True)

    test_log = sess.test(
        'std_packages',
        [str(install_go), 'test', '-count=1', '-json', '-timeout', '20m'] + CORE_PACKAGES,
        cwd=str(sess.install / 'src'), env=test_env, timeout=3600)

    package_pass, test_pass, cached = parse_go_test_json(test_log)
    if not package_pass:
        raise RuntimeError('no packages reported pass in go test -json output')
    sess.write('official_test_evidence.json', {
        'parser': 'go-test-json',
        'selected_packages': CORE_PACKAGES,
        'packages_passed': sorted(package_pass),
        'package_pass_count': len(package_pass),
        'test_cases_passed': len(test_pass),
        'cached_output_lines': cached,
        'count_flag': '-count=1 (cache disabled)',
        'profile': 'core',
        'scope': 'linux/amd64 CGO_ENABLED=0',
    })

    consumer_dir = sess.consumer / 'mod'
    consumer_dir.mkdir(parents=True, exist_ok=True)
    (consumer_dir / 'go.mod').write_text('module consumer\n\ngo 1.24\n')
    (consumer_dir / 'main.go').write_text(MAIN_GO)
    (consumer_dir / 'main_test.go').write_text(MAIN_TEST_GO)

    cons_env = dict(build_env)
    cons_env['GOROOT'] = str(sess.install)
    cons_env['GOCACHE'] = str(sess.build / 'gocache_consumer')
    cons_env['GOMODCACHE'] = str(sess.build / 'gomodcache')
    (sess.build / 'gocache_consumer').mkdir(parents=True, exist_ok=True)
    (sess.build / 'gomodcache').mkdir(parents=True, exist_ok=True)

    sess.test('consumer_module_tests',
              [str(install_go), 'test', '-count=1', '-v', './...'],
              cwd=str(consumer_dir), env=cons_env, timeout=900)

    bin_path = consumer_dir / 'consumer_bin'
    sess.run([str(install_go), 'build', '-trimpath', '-o', str(bin_path), '.'],
             cwd=str(consumer_dir), phase='consumer', name='consumer_build',
             env=cons_env, timeout=900)
    run_log = sess.run([str(bin_path)], cwd=str(consumer_dir), phase='consumer',
                       name='consumer_run', env=cons_env, timeout=300)
    out = (consumer_dir / 'consumer_outcome.txt')
    out.write_text(run_log.read_text())

    sess.write('toolchain_report.json', {
        'pin': PIN_VERSION,
        'profile': 'core',
        'scope': 'linux/amd64 CGO_ENABLED=0',
        'bootstrap': str(bootstrap),
        'bootstrap_version': 'go%d.%d.%d' % bs_version,
        'bootstrap_minimum': 'go%s' % '.'.join(str(n) for n in MIN_BOOTSTRAP),
        'bootstrap_rejected': [
            {'path': str(p), 'version': None if v is None else 'go%d.%d.%d' % v}
            for p, v in rejected
        ],
        'delivered_goroot': str(sess.install),
        'official_packages_tested': CORE_PACKAGES,
        'packages_passed': sorted(package_pass),
        'test_cases_passed': len(test_pass),
        'consumer': 'independent Go module outside src, built and run with install/bin/go',
    })

    sess.finish(features={
        'toolchain': PIN_VERSION,
        'bootstrap': 'go%d.%d.%d' % bs_version,
        'cgo': 'disabled',
        'official_packages': CORE_PACKAGES,
        'consumer_module': True,
    })
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog='solution/main.py',
                                     description='Build Go toolchain from source and verify.')
    subs = parser.add_subparsers(dest='cmd')
    run = subs.add_parser('run', help='build, install and verify')
    run.add_argument('--input', required=True)
    run.add_argument('--output', required=True)
    run.add_argument('--jobs', type=int, default=4)
    run.add_argument('--bootstrap', default=None,
                     help='explicit bootstrap GOROOT (>= go1.22.6); '
                          'defaults to GOROOT_BOOTSTRAP or /opt/bootstrap/go')
    doc = subs.add_parser('doctor', help='check source and tooling readiness')
    doc.add_argument('--input', required=True)

    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 0
    if args.cmd == 'doctor':
        return 0 if doctor(args.input) else 78
    args.jobs = max(1, min(int(args.jobs), 4))
    return cmd_run(args)


if __name__ == '__main__':
    sys.exit(main())
