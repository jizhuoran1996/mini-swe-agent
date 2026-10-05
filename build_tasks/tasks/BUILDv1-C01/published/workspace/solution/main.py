#!/usr/bin/env python3
"""BUILDv1-C01 -- build, install and validate an installable FFmpeg CPU toolkit.

Frozen CORE profile: clean out-of-tree build of FFmpeg n7.1.1
(commit db69d06eeeab4f46da15030a80d539efb4503ca8) from the frozen source
archive, install into a private prefix, run the frozen core FATE subset
(fate-checkasm, fate-ffprobe_compact, fate-ffprobe_xml) and validate the
installed artefacts with an out-of-tree C consumer that links only against
the newly installed shared libraries.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import buildkit

TASK_ID = 'BUILDv1-C01'
REQUIRED_TOOLS = (
    (('cc', 'gcc', 'clang'), 'C compiler'),
    (('make',), 'GNU make'),
    (('ar',), 'binutils ar'),
    (('ranlib',), 'binutils ranlib'),
    (('ld',), 'binutils ld'),
    (('python3',), 'Python 3'),
)
ASM_TOOLS = (('nasm', 'yasm'), 'x86 assembler (needed for --enable-x86asm / fate-checkasm)')
FATE_CORE = ('fate-checkasm', 'fate-ffprobe_compact', 'fate-ffprobe_xml')
BUILD_LIBDIRS = ('libavutil', 'libavcodec', 'libavformat', 'libavfilter',
                 'libswscale', 'libswresample', 'libavdevice', 'libpostproc')
CONSUMER_C = r'''#include <stdio.h>
#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>
#include <libavutil/avutil.h>

int main(int argc, char **argv)
{
    AVFormatContext *fmt = NULL;
    AVCodecContext *dec_ctx = NULL;
    AVPacket *pkt = NULL;
    AVFrame *frame = NULL;
    int ret, audio_index = -1;
    long long frames = 0, samples = 0;
    unsigned i;

    if (argc < 2) {
        fprintf(stderr, "usage: %s MEDIA_FILE\n", argv[0]);
        return 2;
    }
    printf("AVVERSION %s\n", av_version_info());
    if ((ret = avformat_open_input(&fmt, argv[1], NULL, NULL)) < 0) {
        fprintf(stderr, "avformat_open_input failed: %d\n", ret);
        return 3;
    }
    if ((ret = avformat_find_stream_info(fmt, NULL)) < 0) {
        fprintf(stderr, "avformat_find_stream_info failed: %d\n", ret);
        return 4;
    }
    printf("FORMAT %s\n", fmt->iformat && fmt->iformat->name ? fmt->iformat->name : "?");
    printf("NB_STREAMS %u\n", fmt->nb_streams);
    printf("DURATION_US %lld\n", (long long)fmt->duration);

    for (i = 0; i < fmt->nb_streams; i++) {
        AVStream *st = fmt->streams[i];
        const AVCodec *dec = avcodec_find_decoder(st->codecpar->codec_id);
        const char *type = av_get_media_type_string(st->codecpar->codec_type);
        printf("STREAM %u %s %s %d %d %d\n", i, type ? type : "unknown",
               dec ? dec->name : "unknown", st->codecpar->sample_rate,
               st->codecpar->ch_layout.nb_channels, st->codecpar->width);
        if (st->codecpar->codec_type == AVMEDIA_TYPE_AUDIO && audio_index < 0)
            audio_index = (int)i;
    }

    if (audio_index >= 0) {
        AVStream *st = fmt->streams[audio_index];
        const AVCodec *dec = avcodec_find_decoder(st->codecpar->codec_id);
        dec_ctx = avcodec_alloc_context3(dec);
        pkt = av_packet_alloc();
        frame = av_frame_alloc();
        if (dec && dec_ctx && pkt && frame &&
            avcodec_parameters_to_context(dec_ctx, st->codecpar) >= 0 &&
            avcodec_open2(dec_ctx, dec, NULL) >= 0) {
            while (av_read_frame(fmt, pkt) >= 0) {
                if (pkt->stream_index == audio_index && avcodec_send_packet(dec_ctx, pkt) >= 0) {
                    while (avcodec_receive_frame(dec_ctx, frame) >= 0) {
                        frames++;
                        samples += frame->nb_samples;
                    }
                }
                av_packet_unref(pkt);
            }
            avcodec_send_packet(dec_ctx, NULL);
            while (avcodec_receive_frame(dec_ctx, frame) >= 0) {
                frames++;
                samples += frame->nb_samples;
            }
        }
        printf("DECODED_FRAMES %lld\n", frames);
        printf("DECODED_SAMPLES %lld\n", samples);
        av_frame_free(&frame);
        av_packet_free(&pkt);
        avcodec_free_context(&dec_ctx);
    }

    avformat_close_input(&fmt);
    printf("CONSUMER_OK\n");
    return 0;
}
'''


def doctor(input_dir):
    """Return the list of exact missing source/tool/dependency items."""
    inp = Path(input_dir)
    if not inp.is_dir():
        return ['input directory not found: %s' % inp]
    mpath = inp / 'manifest.json'
    if not mpath.is_file():
        return ['manifest.json not found in %s' % inp]
    try:
        manifest = json.loads(mpath.read_text())
    except Exception as exc:
        return ['manifest.json unreadable: %s' % exc]
    missing = []
    src = manifest.get('source') or {}
    archive = inp / str(src.get('filename', 'source.tar.gz'))
    if not archive.is_file():
        missing.append('source archive not found: %s' % archive)
    else:
        want = src.get('sha256')
        got = buildkit.digest(archive)
        if want and got != want:
            missing.append('source archive sha256 mismatch (want %s, got %s)' % (want, got))
    for alts, desc in tuple(REQUIRED_TOOLS) + (ASM_TOOLS,):
        if not any(shutil.which(a) for a in alts):
            missing.append('missing tool: %s (%s)' % (' or '.join(alts), desc))
    return missing


def discover_samples(input_dir):
    for name in ('samples', 'fate-suite', 'fate_samples', 'fate'):
        candidate = Path(input_dir) / name
        if candidate.is_dir():
            return candidate
    for candidate in sorted(Path(input_dir).iterdir()):
        if candidate.is_dir() and 'sample' in candidate.name.lower():
            return candidate
    return Path(input_dir) / 'samples'


def make_scripts_executable(root):
    """The safe tar filter drops execute bits; restore them for build scripts."""
    for path in root.rglob('*'):
        try:
            if not path.is_file():
                continue
        except OSError:
            continue
        if path.suffix in ('.sh', '.pl') or path.name == 'configure' or path.name.startswith('configure.'):
            try:
                path.chmod(0o755)
            except OSError:
                pass


def make_test_env(session):
    """Environment for `make`/FATE so the *freshly built* tree is used.

    Several upstream test-file rules invoke the built tools by plain name, and
the build-tree binaries need their freshly built shared libraries.  Both are
resolved from this repository's own build output -- never a prebuilt product.
    """
    build = str(session.build)
    install = str(session.install)
    libdirs = [str(session.build / d) for d in BUILD_LIBDIRS]
    libdirs.append(str(session.install / 'lib'))
    old_ld = os.environ.get('LD_LIBRARY_PATH')
    if old_ld:
        libdirs.append(old_ld)
    old_path = os.environ.get('PATH', '/usr/local/bin:/usr/bin:/bin')
    return {
        'PATH': os.pathsep.join([build, str(session.install / 'bin'), old_path]),
        'LD_LIBRARY_PATH': os.pathsep.join(libdirs),
    }


def parse_fate_list(text):
    return {tok for tok in text.split() if tok.startswith('fate-')}


def parse_probe(text):
    info = {'streams': []}
    for line in text.splitlines():
        fields = line.split()
        if not fields:
            continue
        if fields[0] == 'STREAM':
            info['streams'].append(fields[1:])
        elif len(fields) >= 2:
            info[fields[0]] = fields[1]
    return info


def check_probe(label, text, expect_codec, expect_samples):
    info = parse_probe(text)
    if info.get('NB_STREAMS') != '1':
        raise RuntimeError('%s: NB_STREAMS=%r (expected 1)' % (label, info.get('NB_STREAMS')))
    if not info['streams']:
        raise RuntimeError('%s: no STREAM line parsed from consumer output' % label)
    stream = info['streams'][0]
    if stream[1] != 'audio':
        raise RuntimeError('%s: stream type %r != audio' % (label, stream[1]))
    if stream[2] != expect_codec:
        raise RuntimeError('%s: codec %r != %r' % (label, stream[2], expect_codec))
    samples = int(info['DECODED_SAMPLES'])
    if samples != expect_samples:
        raise RuntimeError('%s: decoded samples %d != %d' % (label, samples, expect_samples))
    if 'CONSUMER_OK' not in text or not info.get('AVVERSION'):
        raise RuntimeError('%s: consumer did not complete cleanly: %r' % (label, info.get('AVVERSION')))
    return info


def run_fate(session, build, targets, env):
    """Run the frozen core FATE selectors with the private build on PATH."""
    tjobs = '-j%d' % min(2, session.jobs)
    checkasm = ['fate-checkasm'] if 'fate-checkasm' in targets else \
        sorted(t for t in targets if t.startswith('fate-checkasm'))
    if not checkasm:
        raise RuntimeError('no fate-checkasm selector present in the fate-list inventory')
    session.test('fate-checkasm', ['make', tjobs] + checkasm, cwd=build, env=env, timeout=7200)
    for target in FATE_CORE[1:]:
        session.test(target, ['make', tjobs, target], cwd=build, env=env, timeout=3600)


def cmd_run(args):
    missing = doctor(args.input)
    if missing:
        for item in missing:
            print('MISSING: ' + item)
        print('doctor: %d missing item(s); refusing to build' % len(missing))
        return 78

    session = buildkit.Session(args.input, args.output, args.jobs)
    try:
        session.prepare()
    except ValueError as exc:
        print('MISSING: source preparation failed: %s' % exc, file=sys.stderr)
        return 78

    src, build, install = session.src, session.build, session.install
    make_scripts_executable(src)

    samples = discover_samples(args.input)
    configure = [
        str(src / 'configure'),
        '--prefix=' + str(install),
        '--enable-shared',
        '--disable-static',
        '--disable-autodetect',
        '--disable-ffplay',
        '--disable-doc',
        '--samples=' + str(samples),
    ]
    session.run(configure, cwd=build, phase='configure', name='configure', timeout=3600)
    session.run(['make', '-j%d' % session.jobs], cwd=build, phase='build', name='make', timeout=14400)
    session.run(['make', 'install'], cwd=build, phase='install', name='make_install', timeout=3600)

    env = make_test_env(session)

    # ---- official FATE discovery (inventory saved before execution) ----
    fate_log = session.run(['make', 'fate-list'], cwd=build, phase='test_inventory',
                           name='fate_list', env=env, timeout=1800)
    targets = parse_fate_list(fate_log.read_text(errors='replace'))
    session.write('fate_inventory.json', {
        'source': 'make fate-list',
        'target_count': len(targets),
        'required_present': {name: (name in targets) for name in FATE_CORE},
        'checkasm_related': sorted(t for t in targets if 'checkasm' in t)[:400],
    })

    absent = [name for name in FATE_CORE[1:] if name not in targets]
    if absent:
        raise RuntimeError('frozen core FATE selectors missing from fate-list: %s' % absent)

    run_fate(session, build, targets, env)

    # ---- independent out-of-tree consumer against the private prefix ----
    consumer = session.consumer
    media = consumer / 'media'
    media.mkdir(parents=True, exist_ok=True)
    ffmpeg = install / 'bin' / 'ffmpeg'
    cenv = {
        'LD_LIBRARY_PATH': str(install / 'lib'),
        'PKG_CONFIG_PATH': str(install / 'lib' / 'pkgconfig'),
    }

    tone = media / 'tone.wav'
    flac = media / 'tone.flac'
    back = media / 'tone_back.wav'
    raw_a, raw_b = media / 'tone.raw', media / 'tone_back.raw'
    session.run([str(ffmpeg), '-nostdin', '-v', 'error', '-y', '-f', 'lavfi',
                 '-i', 'sine=frequency=1000:duration=2:sample_rate=44100',
                 '-ac', '1', '-c:a', 'pcm_s16le', str(tone)],
                cwd=consumer, phase='consumer', name='gen_tone', env=cenv, timeout=600)
    session.run([str(ffmpeg), '-nostdin', '-v', 'error', '-y', '-i', str(tone),
                 '-c:a', 'flac', str(flac)],
                cwd=consumer, phase='consumer', name='transcode_flac', env=cenv, timeout=600)
    session.run([str(ffmpeg), '-nostdin', '-v', 'error', '-y', '-i', str(flac),
                 '-c:a', 'pcm_s16le', str(back)],
                cwd=consumer, phase='consumer', name='transcode_back', env=cenv, timeout=600)
    session.run([str(ffmpeg), '-nostdin', '-v', 'error', '-y', '-i', str(tone),
                 '-f', 's16le', '-c:a', 'pcm_s16le', str(raw_a)],
                cwd=consumer, phase='consumer', name='raw_original', env=cenv, timeout=600)
    session.run([str(ffmpeg), '-nostdin', '-v', 'error', '-y', '-i', str(back),
                 '-f', 's16le', '-c:a', 'pcm_s16le', str(raw_b)],
                cwd=consumer, phase='consumer', name='raw_roundtrip', env=cenv, timeout=600)

    digest_a, digest_b = buildkit.digest(raw_a), buildkit.digest(raw_b)
    if digest_a != digest_b:
        raise RuntimeError('lossless round trip mismatch: %s != %s' % (digest_a, digest_b))
    if raw_a.stat().st_size != 88200 * 2:
        raise RuntimeError('unexpected raw PCM size: %d' % raw_a.stat().st_size)

    csrc = consumer / 'probe_consumer.c'
    csrc.write_text(CONSUMER_C)
    probe = consumer / 'probe_consumer'
    session.run(['cc', '-O2', '-Wall', '-o', str(probe), str(csrc),
                 '-I', str(install / 'include'), '-L', str(install / 'lib'),
                 '-lavformat', '-lavcodec', '-lavutil', '-lswresample', '-lswscale',
                 '-Wl,-rpath,' + str(install / 'lib'), '-lm'],
                cwd=consumer, phase='consumer_build', name='compile_probe_consumer',
                env=cenv, timeout=900)

    ldd_text = ''
    if shutil.which('ldd'):
        ldd_log = session.run(['ldd', str(probe)], cwd=consumer, phase='consumer',
                              name='ldd_probe_consumer', env=cenv, timeout=120)
        ldd_text = ldd_log.read_text(errors='replace')
        if str(install / 'lib') not in ldd_text:
            raise RuntimeError('consumer does not resolve libraries from the private prefix:\n' + ldd_text)

    report = {'source_revision': json.loads((Path(args.input) / 'manifest.json').read_text())['source']['commit'],
              'linkage': ldd_text.splitlines()[:16], 'probes': {}}
    probe_logs = {}
    for label, path, codec, count in (('flac', flac, 'flac', 88200),
                                      ('wav', tone, 'pcm_s16le', 88200),
                                      ('roundtrip_wav', back, 'pcm_s16le', 88200)):
        log = session.run([str(probe), str(path)], cwd=consumer, phase='consumer',
                          name='probe_' + label, env=cenv, timeout=600)
        text = log.read_text(errors='replace')
        probe_logs[label] = text
        report['probes'][label] = check_probe(label, text, codec, count)
    report['lossless_roundtrip_sha256'] = digest_a

    deliverables = session.output / 'deliverables'
    deliverables.mkdir(parents=True, exist_ok=True)
    shutil.copy2(csrc, deliverables / 'probe_consumer.c')
    shutil.copy2(probe, deliverables / 'probe_consumer')
    session.write('consumer_report.json', report)
    session.write('probe_outputs.json', probe_logs)

    session.finish(features={
        'profile': 'core',
        'build_system': 'configure + GNU make (out-of-tree)',
        'configure': configure,
        'install_prefix': str(install),
        'fate_core_selectors': list(FATE_CORE),
        'fate_test_env': {'PATH_prefix': [str(build), str(install / 'bin')],
                          'LD_LIBRARY_PATH': env['LD_LIBRARY_PATH']},
        'consumer': 'C libavformat/libavcodec probe + lossless flac round trip',
        'consumer_reference_samples': 88200,
    })
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='main.py',
        description='BUILDv1-C01: build, install and validate FFmpeg (n7.1.1) for offline CPU media work')
    sub = parser.add_subparsers(dest='command')
    run = sub.add_parser('run', help='clean build, install, run core FATE and consumer checks')
    run.add_argument('--input', required=True)
    run.add_argument('--output', required=True)
    run.add_argument('--jobs', type=int, default=4)
    doc = sub.add_parser('doctor', help='list exact missing source/tool/dependency items')
    doc.add_argument('--input', required=True)
    args = parser.parse_args(argv)

    if args.command == 'doctor':
        missing = doctor(args.input)
        for item in missing:
            print('MISSING: ' + item)
        if missing:
            print('doctor: not ready (%d missing item(s))' % len(missing))
            return 78
        print('doctor: ready')
        return 0
    if args.command == 'run':
        return cmd_run(args)
    parser.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
