#!/usr/bin/env python3
"""BUILDv1-C02: build GStreamer 1.26.2 (core + gst-plugins-base + gst-plugins-good)
from the frozen source archive, install into a private prefix, run the frozen
upstream unit-test selectors and verify the new SDK with an out-of-tree consumer."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, os.environ.get('PYTHONPATH', ''))
import buildkit  # trusted execution helper (provided on PYTHONPATH)

SUBPROJECTS = ['gstreamer', 'gst-plugins-base', 'gst-plugins-good']
REQUIRED_TOOLS = ['meson', 'ninja', 'pkg-config']
REQUIRED_PKGS = ['glib-2.0', 'gobject-2.0', 'zlib']

SETUP_OPTIONS = [
    '--wrap-mode=nodownload', '--libdir=lib', '--libexecdir=libexec',
    '-Dauto_features=disabled',
    '-Dbase=enabled', '-Dgood=enabled', '-Dbad=disabled', '-Dugly=disabled',
    '-Dtests=enabled', '-Dtools=enabled',
    '-Dgstreamer:check=enabled', '-Dgstreamer:ptp-helper=disabled',
    '-Dgst-plugins-base:app=enabled',
    '-Dgst-plugins-base:audioconvert=enabled',
    '-Dgst-plugins-base:audioresample=enabled',
    '-Dgst-plugins-base:audiotestsrc=enabled',
    '-Dgst-plugins-base:videoconvertscale=enabled',
    '-Dgst-plugins-base:videotestsrc=enabled',
    '-Dgst-plugins-base:typefind=enabled',
    '-Dgst-plugins-base:playback=enabled',
    '-Dgst-plugins-good:wavenc=enabled',
    '-Dgst-plugins-good:wavparse=enabled',
    '-Dgst-plugins-good:jpeg=enabled',
    '-Dgst-plugins-good:png=enabled',
    '-Dgst-plugins-good:matroska=enabled',
    '-Dgst-plugins-good:isomp4=enabled',
]

# (subproject, meson test name) frozen by the CORE profile test_selection block.
TEST_SELECTION = [
    ('gstreamer', 'gst_gstbuffer'),
    ('gstreamer', 'gst_gstbus'),
    ('gstreamer', 'gst_gstvalue'),
    ('gst-plugins-base', 'elements_appsrc'),
    ('gst-plugins-base', 'elements_appsink'),
    ('gst-plugins-base', 'elements_audioconvert'),
    ('gst-plugins-base', 'elements_audioresample'),
    ('gst-plugins-base', 'elements_videoconvert'),
]

CONSUMER_C = r'''/* BUILDv1-C02 out-of-tree consumer for the newly built GStreamer SDK. */
#include <gst/gst.h>
#include <gst/app/gstappsrc.h>
#include <gst/app/gstappsink.h>
#include <stdio.h>
#include <string.h>

static int drain(GstElement *sink)
{
    int n = 0;
    GstSample *s;
    while ((s = gst_app_sink_try_pull_sample(GST_APP_SINK(sink), 2 * GST_SECOND))) {
        n++;
        gst_sample_unref(s);
    }
    return n;
}

static int run_audio(void)
{
    GError *err = NULL;
    GstElement *pipe = gst_parse_launch(
        "appsrc name=src format=bytes is-live=false ! "
        "audioconvert ! audioresample ! appsink name=sink sync=false", &err);
    if (!pipe) {
        fprintf(stderr, "audio pipeline parse failure: %s\n", err ? err->message : "?");
        return 1;
    }
    GstElement *src = gst_bin_get_by_name(GST_BIN(pipe), "src");
    GstElement *sink = gst_bin_get_by_name(GST_BIN(pipe), "sink");
    GstCaps *caps = gst_caps_from_string(
        "audio/x-raw,format=S16LE,rate=44100,channels=2,layout=interleaved");
    g_object_set(src, "caps", caps, NULL);
    gst_caps_unref(caps);

    if (gst_element_set_state(pipe, GST_STATE_PLAYING) == GST_STATE_CHANGE_FAILURE) {
        fprintf(stderr, "audio: failed to reach PLAYING\n");
        return 1;
    }
    for (int i = 0; i < 200; i++) {
        GstBuffer *b = gst_buffer_new_allocate(NULL, 4000, NULL);
        if (gst_app_src_push_buffer(GST_APP_SRC(src), b) != GST_FLOW_OK) {
            fprintf(stderr, "audio: push_buffer failed at %d\n", i);
            return 1;
        }
    }
    gst_app_src_end_of_stream(GST_APP_SRC(src));
    int n = drain(sink);
    printf("audio_samples=%d\n", n);

    gst_element_set_state(pipe, GST_STATE_NULL);
    gst_object_unref(src);
    gst_object_unref(sink);
    gst_object_unref(pipe);
    return n > 0 ? 0 : 1;
}

static int run_video(void)
{
    GError *err = NULL;
    GstElement *pipe = gst_parse_launch(
        "appsrc name=src format=bytes is-live=false ! "
        "videoconvert ! videoscale ! video/x-raw,width=160,height=120 ! "
        "appsink name=sink sync=false", &err);
    if (!pipe) {
        fprintf(stderr, "video pipeline parse failure: %s\n", err ? err->message : "?");
        return 1;
    }
    GstElement *src = gst_bin_get_by_name(GST_BIN(pipe), "src");
    GstElement *sink = gst_bin_get_by_name(GST_BIN(pipe), "sink");
    GstCaps *caps = gst_caps_from_string(
        "video/x-raw,format=I420,width=320,height=240,framerate=30/1");
    g_object_set(src, "caps", caps, NULL);
    gst_caps_unref(caps);

    if (gst_element_set_state(pipe, GST_STATE_PLAYING) == GST_STATE_CHANGE_FAILURE) {
        fprintf(stderr, "video: failed to reach PLAYING\n");
        return 1;
    }
    for (int i = 0; i < 30; i++) {
        GstBuffer *b = gst_buffer_new_allocate(NULL, 320 * 240 * 3 / 2, NULL);
        if (gst_app_src_push_buffer(GST_APP_SRC(src), b) != GST_FLOW_OK) {
            fprintf(stderr, "video: push_buffer failed at %d\n", i);
            return 1;
        }
    }
    gst_app_src_end_of_stream(GST_APP_SRC(src));
    int n = drain(sink);
    printf("video_samples=%d\n", n);

    gst_element_set_state(pipe, GST_STATE_NULL);
    gst_object_unref(src);
    gst_object_unref(sink);
    gst_object_unref(pipe);
    return n > 0 ? 0 : 1;
}

int main(int argc, char **argv)
{
    gst_init(&argc, &argv);
    int a = run_audio();
    int v = run_video();
    printf("consumer_ok=%d\n", (a == 0 && v == 0) ? 1 : 0);
    return (a == 0 && v == 0) ? 0 : 1;
}
'''


def archive_member_names(path: Path) -> list[str]:
    with tarfile.open(path) as tf:
        return [m.name for m in tf.getmembers()]


def doctor(input_dir) -> list[str]:
    """Return the exact list of missing source/tool/dependency items (empty == ready)."""
    input_dir = Path(input_dir)
    missing: list[str] = []
    manifest_path = input_dir / 'manifest.json'
    if not manifest_path.is_file():
        return [f'missing {manifest_path}']
    manifest = json.loads(manifest_path.read_text())
    source = manifest['source']
    archive = input_dir / source['filename']
    if not archive.is_file():
        missing.append(f'missing source archive {archive}')
    else:
        actual = buildkit.digest(archive)
        if actual != source['sha256']:
            missing.append(f'source archive checksum mismatch: {actual} != {source["sha256"]}')
        else:
            names = archive_member_names(archive)
            for sub in SUBPROJECTS:
                if not any(n.endswith(f'subprojects/{sub}/meson.build') for n in names):
                    missing.append(
                        f'frozen archive lacks vendored subproject source '
                        f'subprojects/{sub}/meson.build (git submodules not published in tarball)')
    for tool in REQUIRED_TOOLS:
        if shutil.which(tool) is None:
            missing.append(f'missing build tool: {tool}')
    if shutil.which('cc') is None and shutil.which('gcc') is None:
        missing.append('missing C compiler: cc/gcc')
    for pkg in REQUIRED_PKGS:
        if shutil.which('pkg-config'):
            proc = subprocess.run(['pkg-config', '--exists', pkg],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if proc.returncode != 0:
                missing.append(f'missing pkg-config dependency: {pkg}')
    return missing


def gst_env(session) -> dict:
    prefix = session.install
    return {
        'PATH': str(prefix / 'bin') + os.pathsep + os.environ.get('PATH', ''),
        'LD_LIBRARY_PATH': str(prefix / 'lib'),
        'GST_PLUGIN_PATH': str(prefix / 'lib' / 'gstreamer-1.0'),
        'GST_PLUGIN_SYSTEM_PATH': '',
        'GST_PLUGIN_SCANNER': str(prefix / 'libexec' / 'gstreamer-1.0' / 'gst-plugin-scanner'),
        'GST_REGISTRY': str(session.output / 'registry.dat'),
        'GST_PLUGIN_LOADING_WHITELIST': '*',
    }


def parse_inventory(lines):
    """Normalise `meson test --list` into (project, test_name) pairs.

    Meson prints display strings such as ``gstreamer / gst_gstbuffer`` (newer)
    or ``gstreamer:gst_gstbuffer`` (older); neither is a valid CLI selector, so
    the project and the registered test name are split explicitly. Duplicate
    ``(project, name)`` pairs (one per configured executable) collapse to one.
    """
    pairs: list[tuple[str, str]] = []
    seen = set()
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if ' / ' in line:
            project, name = line.rsplit(' / ', 1)
        elif ':' in line:
            project, name = line.split(':', 1)
        else:
            project, name = '', line
        project, name = project.strip(), name.strip()
        if not name:
            continue
        if (project, name) not in seen:
            seen.add((project, name))
            pairs.append((project, name))
    return pairs


def find_selector(pairs, project: str, name: str):
    """Return the exact meson ``project:test`` selector registered upstream."""
    for proj, tname in pairs:
        if tname == name and proj == project:
            return (proj, tname)
    for proj, tname in pairs:
        if tname == name:
            return (proj, tname)
    return None


def cmd_doctor(args) -> int:
    missing = doctor(args.input)
    if missing:
        print('doctor: NOT READY')
        for item in missing:
            print('  -', item)
        return 78
    print('doctor: READY')
    return 0


def cmd_run(args) -> int:
    missing = doctor(args.input)
    if missing:
        print('doctor: NOT READY - refusing to build')
        for item in missing:
            print('  -', item)
        return 78

    session = buildkit.Session(args.input, args.output, jobs=args.jobs)
    session.prepare()
    build, src, install = session.build, session.src, session.install

    session.run(['meson', 'setup', str(build), str(src), '--prefix', str(install)] + SETUP_OPTIONS,
                cwd=str(src), phase='configure', name='meson_setup', timeout=3600)
    session.run(['meson', 'compile', '-C', str(build), '-j', str(session.jobs)],
                cwd=str(build), phase='build', name='meson_compile', timeout=10800)
    session.run(['meson', 'install', '-C', str(build)],
                cwd=str(build), phase='install', name='meson_install', timeout=3600)

    env = gst_env(session)

    # --- upstream test discovery inventory (preserved before execution) ---
    list_log = session.run(['meson', 'test', '-C', str(build), '--list'],
                           cwd=str(build), phase='test_list', name='meson_test_list',
                           env=env, timeout=600)
    inventory = list_log.read_text(errors='replace').splitlines()
    (session.output / 'test_inventory.txt').write_text('\n'.join(inventory) + '\n')
    pairs = parse_inventory(inventory)
    (session.output / 'test_inventory.json').write_text(
        json.dumps([{'project': p, 'test': t} for p, t in pairs], indent=2) + '\n')

    executed = []
    for project, name in TEST_SELECTION:
        match = find_selector(pairs, project, name)
        if match is None:
            available = ', '.join(sorted({t for _, t in pairs})) or '<empty inventory>'
            raise RuntimeError(
                f'required upstream test absent from inventory: {project}:{name}\n'
                f'registered tests: {available}')
        proj, tname = match
        argv = ['meson', 'test', '-C', str(build), '--print-errorlogs',
                '--num-processes', str(max(1, min(session.jobs, 2)))]
        # Prefer the exact upstream registered name when the project is known;
        # fall back to --suite <project> <name> for older meson layouts.
        if proj:
            argv.append(f'{proj}:{tname}')
        else:
            argv.extend(['--suite', project, tname])
        session.test(f'{project}__{name}', argv, cwd=str(build), env=env, timeout=3600)
        executed.append(f'{proj}:{tname}' if proj else f'{project}:{tname}')

    # --- independent out-of-tree consumer -------------------------------------
    pkg_env = os.environ.copy()
    pkg_env['PKG_CONFIG_PATH'] = str(install / 'lib' / 'pkgconfig')
    pc_modules = ['gstreamer-1.0', 'gstreamer-app-1.0']
    cflags = subprocess.run(['pkg-config', '--cflags'] + pc_modules, env=pkg_env,
                            capture_output=True, text=True, check=True).stdout.split()
    libs = subprocess.run(['pkg-config', '--libs'] + pc_modules, env=pkg_env,
                          capture_output=True, text=True, check=True).stdout.split()
    if not cflags or not libs:
        raise RuntimeError('installed SDK pkg-config produced no compile/link flags')

    source = session.consumer / 'appsink_consumer.c'
    source.write_text(CONSUMER_C)
    binary = session.consumer / 'appsink_consumer'
    session.run(['cc', '-O2', '-o', str(binary), str(source)] + cflags + libs,
                cwd=str(session.consumer), phase='consumer_build', name='consumer_cc',
                env=pkg_env, timeout=600)
    session.run([str(binary)], cwd=str(session.consumer), phase='consumer_run',
                name='consumer_appsink', env=env, timeout=600)

    media = session.consumer / 'media'
    media.mkdir(parents=True, exist_ok=True)
    launch = str(install / 'bin' / 'gst-launch-1.0')
    session.run([launch, '-q', 'audiotestsrc', 'num-buffers=64', 'samplesperbuffer=1024',
                 '!', 'audioconvert', '!', 'wavenc', '!',
                 'filesink', f'location={media / "tone.wav"}'],
                cwd=str(media), phase='consumer_run', name='pipeline_encode_wav',
                env=env, timeout=600)
    session.run([launch, '-q', 'filesrc', f'location={media / "tone.wav"}',
                 '!', 'wavparse', '!', 'audioconvert', '!', 'wavenc', '!',
                 'filesink', f'location={media / "roundtrip.wav"}'],
                cwd=str(media), phase='consumer_run', name='pipeline_decode_wav',
                env=env, timeout=600)
    session.run([launch, '-q', 'videotestsrc', 'num-buffers=8',
                 '!', 'videoconvert', '!', 'pngenc', '!',
                 'filesink', f'location={media / "frame.png"}'],
                cwd=str(media), phase='consumer_run', name='pipeline_encode_png',
                env=env, timeout=600)
    session.run([launch, '-q', 'filesrc', f'location={media / "frame.png"}',
                 '!', 'pngdec', '!', 'videoconvert', '!', 'jpegenc', '!',
                 'filesink', f'location={media / "frame.jpg"}'],
                cwd=str(media), phase='consumer_run', name='pipeline_transcode_image',
                env=env, timeout=600)

    produced = {p.name: p.stat().st_size for p in sorted(media.iterdir()) if p.is_file()}
    for name, size in produced.items():
        if size <= 0:
            raise RuntimeError(f'media consumer produced empty file: {name}')

    plugins = sorted(p.name for p in (install / 'lib' / 'gstreamer-1.0').glob('*.so'))
    if not plugins:
        raise RuntimeError('no shared plugins installed under the private prefix')

    session.finish(features={
        'subprojects': SUBPROJECTS,
        'setup_options': SETUP_OPTIONS,
        'test_selectors': executed,
        'media_outputs': produced,
        'installed_plugins': plugins,
        'consumer_binary': str(binary),
        'consumer_provenance': 'built against private prefix pkg-config outside src',
    })
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog='buildv1-c02',
                                     description='GStreamer 1.26.2 frozen CORE offline source build')
    sub = parser.add_subparsers(dest='command')
    doc = sub.add_parser('doctor', help='list exact missing source/tool/dependency items')
    doc.add_argument('--input', required=True)
    run = sub.add_parser('run', help='build, install, test and verify the SDK')
    run.add_argument('--input', required=True)
    run.add_argument('--output', required=True)
    run.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args(argv)
    if args.command == 'doctor':
        return cmd_doctor(args)
    if args.command == 'run':
        return cmd_run(args)
    parser.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
