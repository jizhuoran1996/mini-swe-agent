#!/usr/bin/env python3
"""BUILDv1-A02: build, install, test and independently consume Zstandard (v1.5.7)."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

from buildkit import Session, digest

DEFAULT_INPUT = '/workspace/input'
DEFAULT_OUTPUT = '/workspace/output'

CONSUMER_C = r'''
/* Independent consumer: chunked streaming with a shared dictionary. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <zstd.h>

#define CHUNK_IN 4096     /* compression chunk */
#define CHUNK_OUT 7       /* decompression window: deliberately tiny */

static void die(const char *msg) { fprintf(stderr, "consumer error: %s\n", msg); exit(1); }

static unsigned char *slurp(const char *path, size_t *size) {
    FILE *f = fopen(path, "rb");
    long n; unsigned char *buf;
    if (!f) die("cannot open input file");
    if (fseek(f, 0, SEEK_END) != 0) die("seek failed");
    n = ftell(f);
    if (n < 0) die("tell failed");
    rewind(f);
    buf = (unsigned char *)malloc((size_t)n + 1);
    if (!buf) die("allocation failed");
    if (n > 0 && fread(buf, 1, (size_t)n, f) != (size_t)n) die("read failed");
    fclose(f);
    *size = (size_t)n;
    return buf;
}

static void dump(const char *path, const void *data, size_t size) {
    FILE *f = fopen(path, "wb");
    if (!f) die("cannot open output file");
    if (size && fwrite(data, 1, size, f) != size) die("write failed");
    if (fclose(f) != 0) die("close failed");
}

int main(int argc, char **argv) {
    const char *dictPath, *inPath, *zstPath, *outPath;
    size_t dictSize = 0, inSize = 0, ccap, csize;
    unsigned char *dict, *in, *cdata, *odata;
    ZSTD_CCtx *cctx; ZSTD_DCtx *dctx;
    ZSTD_inBuffer ib; ZSTD_outBuffer ob;
    size_t guard, hint, stalled;

    if (argc != 5) {
        fprintf(stderr, "usage: %s <dict> <input> <compressed-out> <decompressed-out>\n", argv[0]);
        return 2;
    }
    dictPath = argv[1]; inPath = argv[2]; zstPath = argv[3]; outPath = argv[4];
    dict = slurp(dictPath, &dictSize);
    in = slurp(inPath, &inSize);

    /* ---------------- streaming compression ----------------
     * ZSTD_compressStream2() returning 0 while feeding a chunk with
     * ZSTD_e_continue only means "that chunk has been consumed", it does NOT
     * mean the file is done.  The loop therefore feeds further chunks until the
     * tail is submitted with ZSTD_e_end, and then keeps calling with ZSTD_e_end
     * until the call returns 0 (frame completely flushed). */
    cctx = ZSTD_createCCtx();
    if (!cctx) die("ZSTD_createCCtx");
    if (ZSTD_isError(ZSTD_CCtx_loadDictionary(cctx, dict, dictSize))) die("loadDictionary(compress)");
    ccap = ZSTD_compressBound(inSize) + 1024;
    cdata = (unsigned char *)malloc(ccap);
    if (!cdata) die("allocation failed");
    ib.src = in; ib.size = 0; ib.pos = 0;
    ob.dst = cdata; ob.size = ccap; ob.pos = 0;

    guard = 0;
    for (;;) {
        size_t end = ib.pos + CHUNK_IN;
        ZSTD_EndDirective mode;
        size_t rc;
        if (end > inSize) end = inSize;
        ib.size = end;
        mode = (end >= inSize) ? ZSTD_e_end : ZSTD_e_continue;
        rc = ZSTD_compressStream2(cctx, &ob, &ib, mode);
        if (ZSTD_isError(rc)) die("ZSTD_compressStream2");
        if (mode == ZSTD_e_end && rc == 0) break;      /* frame flushed */
        if (mode == ZSTD_e_end && ib.pos >= ib.size)
            continue;                                  /* keep flushing */
        if (++guard > 200000000) die("compression made no progress");
    }
    csize = ob.pos;
    ZSTD_freeCCtx(cctx);
    if (csize == 0) die("empty compressed output");
    dump(zstPath, cdata, csize);

    /* ---------------- streaming decompression ----------------
     * ZSTD_decompressStream() returns 0 only when the frame has been fully
     * decoded AND flushed; a non-zero return is a hint for the next call.  Input
     * exhaustion is therefore not completion: the loop keeps going (with an
     * empty input window once the compressed bytes run out) so a pending final
     * flush can happen, and only reports truncation when a call makes no
     * forward progress at all. */
    dctx = ZSTD_createDCtx();
    if (!dctx) die("ZSTD_createDCtx");
    if (ZSTD_isError(ZSTD_DCtx_loadDictionary(dctx, dict, dictSize))) die("loadDictionary(decompress)");
    odata = (unsigned char *)malloc(inSize + 64);
    if (!odata) die("allocation failed");
    ib.src = cdata; ib.size = 0; ib.pos = 0;
    ob.dst = odata; ob.size = inSize + 64; ob.pos = 0;

    hint = 1; stalled = 0; guard = 0;
    while (hint != 0) {
        size_t const inBefore = ib.pos;
        size_t const outBefore = ob.pos;
        size_t end = ib.pos + CHUNK_OUT;
        if (end > csize) end = csize;
        ib.size = end;
        hint = ZSTD_decompressStream(dctx, &ob, &ib);
        if (ZSTD_isError(hint)) die("ZSTD_decompressStream");
        if (ib.pos == inBefore && ob.pos == outBefore) {
            if (++stalled > 1) break;                  /* no progress -> truncated */
        } else {
            stalled = 0;
        }
        if (++guard > 200000000) die("decompression made no progress");
    }
    if (hint != 0) die("truncated frame");
    ZSTD_freeDCtx(dctx);

    if (ob.pos != inSize) die("round-trip size mismatch");
    if (memcmp(odata, in, inSize) != 0) die("round-trip content mismatch");
    dump(outPath, odata, inSize);
    printf("CONSUMER_OK input=%zu compressed=%zu\n", inSize, csize);
    free(dict); free(in); free(cdata); free(odata);
    return 0;
}
'''

CMP_PY = r'''
import hashlib, sys

def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()

a, b = sys.argv[1], sys.argv[2]
ha, hb = sha(a), sha(b)
print('sha256(%s)=%s' % (a, ha))
print('sha256(%s)=%s' % (b, hb))
if ha != hb:
    print('FILES_DIFFER')
    sys.exit(1)
print('FILES_IDENTICAL')
'''


def _tool(name):
    return shutil.which(name)


def _header(name):
    for directory in ('/usr/include', '/usr/include/x86_64-linux-gnu', '/usr/local/include'):
        candidate = Path(directory) / name
        if candidate.exists():
            return str(candidate)
    return None


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def doctor(input_dir: Path) -> int:
    blocking, optional, lines = [], [], []

    def required(label, ok, detail):
        lines.append(('OK   required  ' if ok else 'MISS required  ') + '%-32s %s' % (label, detail))
        if not ok:
            blocking.append(label)

    required('input_dir', input_dir.is_dir(), str(input_dir))
    manifest = input_dir / 'manifest.json'
    required('manifest.json', manifest.is_file(), str(manifest))
    if manifest.is_file():
        try:
            meta = json.loads(manifest.read_text())['source']
            archive = input_dir / meta['filename']
            if not archive.is_file():
                required('source_archive', False, str(archive))
            else:
                got = digest(archive)
                required('source_archive_sha256', got == meta['sha256'],
                         '%s bytes=%d' % (got[:16] + '...', archive.stat().st_size))
        except Exception as exc:  # noqa: BLE001 - doctor reports, never raises
            required('manifest_readable', False, repr(exc))
    for tool in ('cc', 'make', 'ar', 'python3'):
        required('tool:' + tool, _tool(tool) is not None, _tool(tool) or 'not found')

    # Runtime dependency of the official CLI suite (tests/cli-tests/cltools/zstdless.sh).
    # The real system pager is requested as-is; no stand-in is ever built.
    less = _tool('less')
    required('runtime:less', less is not None,
             (less or 'not found') + ' (needed by tests/cli-tests/cltools/zstdless.sh)')

    for label, binary in (('gzip', 'gzip'), ('xz', 'xz'), ('lz4', 'lz4')):
        path = _tool(binary)
        optional.append({'item': 'cli:' + label, 'resolved': path})
        lines.append('INFO optional  %-32s %s' % ('cli:' + label, path or 'absent'))
    for label, header in (('zlib', 'zlib.h'), ('lzma', 'lzma.h'), ('lz4', 'lz4.h')):
        path = _header(header)
        optional.append({'item': 'header:' + label, 'resolved': path})
        lines.append('INFO optional  %-32s %s' % ('header:' + label, path or 'absent'))

    print('\n'.join(lines))
    print(json.dumps({'ready': not blocking, 'missing_required': blocking, 'optional': optional}, indent=2))
    if blocking:
        print('doctor: NOT READY, %d required item(s) missing' % len(blocking))
        return 78
    print('doctor: READY (core scope: default libzstd + zstd CLI + make check)')
    return 0


def make_fixtures(consumer: Path) -> Path:
    samples = consumer / 'samples'
    samples.mkdir(parents=True, exist_ok=True)
    for i in range(96):
        rows = []
        for j in range(64):
            token = hashlib.sha256(('%d-%d' % (i, j)).encode()).hexdigest()[:8]
            rows.append('user=%03d seq=%03d token=%s status=active role=reader\n' % (i, j, token))
        (samples / ('sample%03d.txt' % i)).write_text(''.join(rows))
    (consumer / 'data.txt').write_text(''.join(
        'line %05d: alpha beta gamma delta epsilon %d\n' % (i, (i * 7) % 101) for i in range(4000)))
    blob, seed = bytearray(), b'BUILDv1-A02-zstd-fixture'
    while len(blob) < 128 * 1024:
        seed = hashlib.sha256(seed).digest()
        blob.extend(seed)
    (consumer / 'data.bin').write_bytes(bytes(blob[: 128 * 1024]))
    return samples


def run(input_dir: Path, output_dir: Path, jobs: int) -> int:
    s = Session(input_dir, output_dir, jobs)
    src = s.prepare()
    jobs_s, tjobs = str(s.jobs), '2'
    cmp_py = str(s.consumer / 'cmp_files.py')
    command = s.commands

    s.write('source_identity.json', {
        'task_id': s.manifest['task_id'],
        'archive_sha256': digest(input_dir / s.manifest['source']['filename']),
        'expected_sha256': s.manifest['source']['sha256'],
        'release_ref': s.manifest['source']['release_ref'],
        'commit': s.manifest['source']['commit'],
        'readme_sha256': digest(src / 'README.md'),
        'makefile_sha256': digest(src / 'Makefile'),
        'top_level': sorted(p.name for p in src.iterdir()),
    })

    tests_makefile = (src / 'tests' / 'Makefile').read_text(errors='replace')
    s.write('official_test_inventory.json', {
        'tests_makefile_sha256': digest(src / 'tests' / 'Makefile'),
        'make_targets': sorted(set(re.findall(r'^([A-Za-z0-9_.-]+)\s*:', tests_makefile, re.M))),
        'cli_test_dirs': sorted(p.name for p in (src / 'tests' / 'cli-tests').iterdir()),
        'cli_test_files': sorted(str(p.relative_to(src / 'tests' / 'cli-tests'))
                                 for p in (src / 'tests' / 'cli-tests').rglob('*.sh')),
        'golden_sets': sorted(p.name for p in (src / 'tests').glob('golden-*')),
        'selected': ['make check', 'test-cli-tests', 'test-invalidDictionaries', 'test-legacy', 'test-pool'],
        'out_of_core_scope': ['test-zstream', 'test-fuzzer'],
    })

    s.run(['make', '-j' + jobs_s], cwd=src, phase='build', name='make_default', timeout=5400)
    s.run(['make', 'install', 'PREFIX=' + str(s.install)], cwd=src, phase='install',
          name='make_install', timeout=1800)

    # Honest dependency gate: the official CLI suite drives programs/zstdless, which
    # pipes through the system pager.  Use the real tool or fail; never a stand-in.
    less = _tool('less')
    s.write('dependencies.json', {'pager': {'name': 'less', 'resolved': less, 'stand_in': False}})
    if less is None:
        raise RuntimeError('required runtime dependency missing: less '
                           '(used by tests/cli-tests/cltools/zstdless.sh)')
    s.run([less, '--version'], cwd=src, phase='verify', name='system_pager_version', check=False)
    test_env = {'FUZZER_FLAGS': '--no-big-tests'}

    s.test('make-check', ['make', 'check'], cwd=src, env=test_env, timeout=5400)
    s.test('test-cli-tests', ['make', '-C', 'tests', '-j' + tjobs, 'test-cli-tests'],
           cwd=src, env=test_env, timeout=5400)
    s.test('test-invalidDictionaries', ['make', '-C', 'tests', 'test-invalidDictionaries'],
           cwd=src, env=test_env, timeout=1800)
    s.test('test-legacy', ['make', '-C', 'tests', 'test-legacy'], cwd=src, env=test_env, timeout=1800)
    s.test('test-pool', ['make', '-C', 'tests', 'test-pool'], cwd=src, env=test_env, timeout=1800)

    # ---- independent consumption outside the source tree -------------------
    consumer = s.consumer
    consumer.mkdir(parents=True, exist_ok=True)
    write_text(consumer / 'consumer.c', CONSUMER_C)
    write_text(consumer / 'cmp_files.py', CMP_PY)
    samples = make_fixtures(consumer)

    zstd = str(s.install / 'bin' / 'zstd')
    include, libdir = str(s.install / 'include'), str(s.install / 'lib')
    lib = s.install / 'lib' / 'libzstd.so'
    if not lib.is_file():
        raise RuntimeError('installed shared library missing: ' + str(lib))
    s.run([zstd, '--version'], cwd=consumer, phase='verify', name='installed_cli_version')

    dict_path = consumer / 'trained.dict'
    s.run([zstd, '--train', '-o', str(dict_path), '--maxdict=16384', '-f'] +
          [str(p) for p in sorted(samples.glob('*.txt'))],
          cwd=consumer, phase='consumer', name='zstd_train_dictionary', check=False, timeout=900)
    if command[-1]['exit_code'] == 0 and dict_path.is_file() and dict_path.stat().st_size:
        dict_kind = 'trained-zstd-dictionary'
    else:
        dict_path.write_bytes(b''.join(p.read_bytes() for p in sorted(samples.glob('*.txt')))[:32768])
        dict_kind = 'raw-content-dictionary'
    s.write('dictionary_info.json', {'kind': dict_kind, 'bytes': dict_path.stat().st_size})

    s.run(['cc', '-O2', '-std=c11', '-Wall', '-Wextra', '-I', include,
           str(consumer / 'consumer.c'), str(lib), '-o', str(consumer / 'consumer'),
           '-Wl,-rpath,' + libdir], cwd=consumer, phase='consumer', name='build_streaming_consumer')

    s.run([str(consumer / 'consumer'), str(dict_path), str(consumer / 'data.txt'),
           str(consumer / 'data.txt.zst'), str(consumer / 'data.txt.out')],
          cwd=consumer, phase='consumer', name='run_streaming_consumer')
    s.run(['python3', cmp_py, str(consumer / 'data.txt'), str(consumer / 'data.txt.out')],
          cwd=consumer, phase='consumer', name='cmp_streaming_consumer')

    linkage = s.run(['ldd', str(consumer / 'consumer')], cwd=consumer, phase='verify', name='consumer_ldd')
    linkage_text = linkage.read_text(errors='replace')
    (output_dir / 'consumer_linkage.txt').write_text(linkage_text)
    if libdir not in linkage_text:
        raise RuntimeError('consumer does not resolve libzstd from the private prefix:\n' + linkage_text)

    s.run([zstd, '-f', '-D', str(dict_path), '-o', str(consumer / 'cli_dict.zst'), str(consumer / 'data.txt')],
          cwd=consumer, phase='consumer', name='cli_compress_with_dictionary')
    s.run([zstd, '-d', '-f', '-D', str(dict_path), '-o', str(consumer / 'cli_dict.out'), str(consumer / 'cli_dict.zst')],
          cwd=consumer, phase='consumer', name='cli_decompress_with_dictionary')
    s.run(['python3', cmp_py, str(consumer / 'data.txt'), str(consumer / 'cli_dict.out')],
          cwd=consumer, phase='consumer', name='cmp_cli_dictionary_roundtrip')
    s.run([zstd, '-f', '-o', str(consumer / 'data.bin.zst'), str(consumer / 'data.bin')],
          cwd=consumer, phase='consumer', name='cli_compress_binary')
    s.run([zstd, '-d', '-f', '-o', str(consumer / 'data.bin.out'), str(consumer / 'data.bin.zst')],
          cwd=consumer, phase='consumer', name='cli_decompress_binary')
    s.run(['python3', cmp_py, str(consumer / 'data.bin'), str(consumer / 'data.bin.out')],
          cwd=consumer, phase='consumer', name='cmp_cli_binary_roundtrip')

    # negative: corrupt the compressed artifact produced by the streaming consumer
    corrupted = bytearray((consumer / 'data.txt.zst').read_bytes())
    for i in range(16, min(len(corrupted) - 8, 64)):
        corrupted[i] ^= 0xFF
    (consumer / 'data.txt.corrupt.zst').write_bytes(bytes(corrupted))
    s.run([zstd, '-d', '-f', '-D', str(dict_path),
           '-o', str(consumer / 'data.txt.corrupt.out'),
           str(consumer / 'data.txt.corrupt.zst')],
          cwd=consumer, phase='negative', name='negative_corrupt_input', check=False)
    negative_decode_rc = command[-1]['exit_code']
    negative_decode_log = output_dir / command[-1]['log']
    if negative_decode_log.read_text(errors='replace').strip() == '':
        raise RuntimeError('corrupt-input negative case produced no diagnostic output')
    if negative_decode_rc == 0:
        raise RuntimeError('negative case failed: corrupt compressed input was accepted')

    stashed = lib.with_name('libzstd.so.stashed')
    lib.rename(stashed)
    try:
        s.run(['cc', '-O2', '-std=c11', '-I', include, str(consumer / 'consumer.c'), str(lib),
               '-o', str(consumer / 'consumer_negative')],
              cwd=consumer, phase='negative', name='negative_link_without_installed_lib', check=False)
        negative_rc = command[-1]['exit_code']
    finally:
        stashed.rename(lib)
    if negative_rc == 0:
        raise RuntimeError('negative case failed: consumer linked without the installed libzstd')
    s.write('negative_cases.json', [
        {'case': 'corrupt compressed input rejected by CLI decompression',
         'expected': 'nonzero exit code',
         'observed_exit_code': negative_decode_rc},
        {'case': 'remove installed libzstd.so then relink a fresh consumer',
         'expected': 'nonzero exit code',
         'observed_exit_code': negative_rc,
         'artifact_restored': lib.is_file()},
    ])

    s.write('resolution.json', {
        'cli': zstd, 'include_dir': include, 'lib_dir': libdir, 'shared_library': str(lib),
        'installed_files': len([p for p in s.install.rglob('*') if p.is_file()]),
        'dictionary': {'path': str(dict_path), 'kind': dict_kind, 'bytes': dict_path.stat().st_size},
        'pager': less,
        'consumer_linkage_verified': libdir in linkage_text,
    })
    s.finish(features={
        'default_make_build': True, 'private_prefix_install': True,
        'official_check': True, 'cli_tests': True, 'invalid_dictionaries': True,
        'legacy_format': True, 'thread_pool': True,
        'system_pager_used': less is not None, 'no_tool_stand_ins': True,
        'independent_streaming_consumer': True, 'cli_dictionary_roundtrip': True,
        'negative_corrupt_input': True, 'negative_missing_artifact': True,
    })
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog='BUILDv1-A02', description='Build/install/test Zstandard v1.5.7.')
    sub = parser.add_subparsers(dest='command')
    for name in ('run', 'doctor'):
        p = sub.add_parser(name, help='%s the frozen build profile' % name)
        p.add_argument('--input', default=DEFAULT_INPUT)
        p.add_argument('--output', default=DEFAULT_OUTPUT)
        p.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == 'doctor':
        return doctor(Path(args.input).resolve())
    return run(Path(args.input).resolve(), Path(args.output).resolve(), args.jobs)


if __name__ == '__main__':
    sys.exit(main())
