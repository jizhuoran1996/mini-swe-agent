#!/usr/bin/env python3
"""BUILDv1-C03: source-build ImageMagick 7 (PNG/JPEG/TIFF CLI + MagickWand/Magick++).

Build, install and test the frozen upstream tarball; then consume the
freshly-installed prefix from a clean consumer directory outside the source
tree.  The C consumer uses the ImageMagick 7 header layout
``<MagickWand/MagickWand.h>`` (the legacy ``<wand/MagickWand.h>`` path does
not exist under the installed ImageMagick-7 include root).
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import buildkit

TASK_ID = 'BUILDv1-C03'
REQUIRED_TOOLS = ['gcc', 'g++', 'make', 'pkg-config', 'tar']
REQUIRED_PKGS = ['libpng', 'libjpeg', 'libtiff-4', 'freetype2']


def _which(name):
    return shutil.which(name)


def _pkgconfig_ok(name):
    if not _which('pkg-config'):
        return False
    try:
        return subprocess.run(['pkg-config', '--exists', name],
                              capture_output=True, timeout=15).returncode == 0
    except Exception:
        return False


def doctor(input_dir):
    input_dir = Path(input_dir).resolve()
    missing = []
    if not (input_dir / 'manifest.json').is_file():
        missing.append('source:manifest.json')
    if not (input_dir / 'source.tar.gz').is_file():
        missing.append('source:source.tar.gz')
    for tool in REQUIRED_TOOLS:
        if not _which(tool):
            missing.append('tool:' + tool)
    for pkg in REQUIRED_PKGS:
        if not _pkgconfig_ok(pkg):
            missing.append('dependency:' + pkg)
    if not _which('gs'):
        missing.append('dependency:ghostscript')
    if missing:
        for item in missing:
            print('MISSING ' + item)
        return 78
    print('READY: source, tools and delegate dependencies present')
    return 0


# ImageMagick 7 public header layout: <MagickWand/MagickWand.h>.
# NOTE: this is a plain (non-raw) Python string, therefore every C-side
# ``%%s`` below would be emitted as a literal ``%%s`` in C.  We keep the
# source readable by writing ``%s`` directly (Python only treats ``%``
# specially when a ``%`` operator is applied to the string literal).
CONSUMER_C = (
    "#include <stdio.h>\n"
    "#include <stddef.h>\n"
    "#include <sys/types.h>\n"
    "#include <MagickWand/MagickWand.h>\n"
    "\n"
    "int main(int argc, char **argv) {\n"
    "    if (argc != 3) { fprintf(stderr, \"usage: %s in out\\n\", argv[0]); return 2; }\n"
    "\n"
    "    MagickWandGenesis();\n"
    "    MagickWand *wand = NewMagickWand();\n"
    "\n"
    "    if (MagickReadImage(wand, argv[1]) == MagickFalse) {\n"
    "        fprintf(stderr, \"read failed: %s\\n\", argv[1]);\n"
    "        return 1;\n"
    "    }\n"
    "\n"
    "    size_t w = MagickGetImageWidth(wand);\n"
    "    size_t h = MagickGetImageHeight(wand);\n"
    "    printf(\"read %zux%zu from %s\\n\", w, h, argv[1]);\n"
    "    if (w != 128 || h != 96) {\n"
    "        fprintf(stderr, \"unexpected geometry %zux%zu\\n\", w, h);\n"
    "        return 3;\n"
    "    }\n"
    "\n"
    "    MagickSetImageColorspace(wand, sRGBColorspace);\n"
    "\n"
    "    PixelWand *pw = NewPixelWand();\n"
    "    MagickGetImagePixelColor(wand, 0, 0, pw);\n"
    "    printf(\"top-left pixel: %s\\n\", PixelGetColorAsString(pw));\n"
    "    MagickGetImagePixelColor(wand, 0, (ssize_t)h - 1, pw);\n"
    "    printf(\"bottom-left pixel: %s\\n\", PixelGetColorAsString(pw));\n"
    "    pw = DestroyPixelWand(pw);\n"
    "\n"
    "    if (MagickResizeImage(wand, 64, 48, LanczosFilter) == MagickFalse) {\n"
    "        fprintf(stderr, \"resize failed\\n\"); return 4;\n"
    "    }\n"
    "\n"
    "    /* Force a true-colour (RGBA) PNG on write; the PNG32: pseudo-format\n"
    "       disables palette / grey optimisation so the artefact survives any\n"
    "       downstream RGB-only consumer. */\n"
    "    char out[4096];\n"
    "    int n = snprintf(out, sizeof(out), \"PNG32:%s\", argv[2]);\n"
    "    if (n < 0 || (size_t)n >= sizeof(out)) {\n"
    "        fprintf(stderr, \"output path too long\\n\"); return 7;\n"
    "    }\n"
    "    if (MagickWriteImage(wand, out) == MagickFalse) {\n"
    "        fprintf(stderr, \"write failed: %s\\n\", out); return 6;\n"
    "    }\n"
    "    printf(\"wrote %s (%zux%zu RGBA PNG)\\n\", out,\n"
    "           MagickGetImageWidth(wand), MagickGetImageHeight(wand));\n"
    "\n"
    "    wand = DestroyMagickWand(wand);\n"
    "    MagickWandTerminus();\n"
    "    return 0;\n"
    "}\n"
)


def _chmod_scripts(src):
    names = ['configure', 'config.guess', 'config.sub', 'install-sh', 'missing',
             'compile', 'depcomp', 'ltmain.sh', 'mkinstalldirs', 'test-driver',
             'ar-lib']
    for name in names:
        f = src / name
        if f.is_file():
            try:
                f.chmod(f.stat().st_mode | 0o111)
            except OSError:
                pass
    for f in src.rglob('*.sh'):
        try:
            f.chmod(f.stat().st_mode | 0o111)
        except OSError:
            pass


def _test_inventory(session, src):
    entries = []
    for rel in ['tests', 'Magick++/tests', 'MagickCore/tests']:
        d = src / rel
        if d.is_dir():
            for f in sorted(d.iterdir()):
                entries.append({'path': str(f.relative_to(src)),
                                'executable': os.access(f, os.X_OK),
                                'dir': f.is_dir()})
    session.write('test_inventory.json', entries)
    return entries


def do_run(input_dir, output_dir, jobs):
    rc = doctor(input_dir)
    if rc != 0:
        return rc
    session = buildkit.Session(input_dir, output_dir, jobs)
    jobs = session.jobs
    src = session.prepare()
    _chmod_scripts(src)
    prefix = session.install

    _test_inventory(session, src)

    session.run([str(src / 'configure'),
                 '--prefix=' + str(prefix),
                 '--enable-shared', '--disable-static',
                 '--without-x', '--without-perl',
                 '--with-quantum-depth=16',
                 '--with-png=yes', '--with-jpeg=yes', '--with-tiff=yes',
                 '--with-freetype=yes', '--with-gslib=yes'],
                cwd=session.build, phase='configure', name='configure',
                timeout=2400)

    session.run(['make', '-j%d' % jobs], cwd=session.build, phase='build',
                name='build', timeout=7200)

    session.run(['make', 'install'], cwd=session.build, phase='install',
                name='install', timeout=1800)

    magick = prefix / 'bin' / 'magick'
    if not magick.is_file():
        raise RuntimeError('install prefix missing %s' % magick)

    session.run([str(magick), '-list', 'configure'], cwd=session.consumer,
                phase='verify', name='list_configure', timeout=120)
    session.run([str(magick), '-list', 'format'], cwd=session.consumer,
                phase='verify', name='list_format', timeout=120)

    # Official upstream test run (post-install).
    session.test('make-check', ['make', 'check'], cwd=session.build, timeout=7200)

    consumer = session.consumer
    consumer.mkdir(parents=True, exist_ok=True)
    pc_dirs = [str(prefix / 'lib' / 'pkgconfig'),
               str(prefix / 'lib64' / 'pkgconfig')]
    pc_env = os.environ.copy()
    pc_env['PKG_CONFIG_PATH'] = os.pathsep.join(
        [p for p in pc_dirs if Path(p).is_dir()] +
        [pc_env.get('PKG_CONFIG_PATH', '')]).strip(os.pathsep)

    wand_pc = None
    for candidate in ('MagickWand-7.Q16HDRI', 'MagickWand-7.Q16', 'MagickWand'):
        try:
            ok = subprocess.run(['pkg-config', '--exists', candidate],
                                env=pc_env, capture_output=True).returncode == 0
        except Exception:
            ok = False
        if ok:
            wand_pc = candidate
            break
    if wand_pc is None:
        raise RuntimeError(
            'MagickWand pkg-config metadata not found in install prefix')

    cflags = subprocess.check_output(['pkg-config', '--cflags', wand_pc],
                                     env=pc_env).decode().split()
    libs = subprocess.check_output(['pkg-config', '--libs', wand_pc],
                                   env=pc_env).decode().split()

    cfile = consumer / 'consumer.c'
    cfile.write_text(CONSUMER_C)

    session.run(['gcc', '-O2', '-Wall', '-o', str(consumer / 'consumer'),
                 str(cfile)] + cflags + libs,
                cwd=consumer, phase='consumer', env=pc_env,
                name='compile_consumer', timeout=600)

    run_env = dict(os.environ)
    run_env['LD_LIBRARY_PATH'] = str(prefix / 'lib') + os.pathsep + \
        run_env.get('LD_LIBRARY_PATH', '')
    run_env['PATH'] = str(prefix / 'bin') + os.pathsep + run_env.get('PATH', '')

    session.run([str(magick), '-size', '128x96', 'gradient:red-blue',
                 '-type', 'TrueColorAlpha', str(consumer / 'input.tiff')],
                cwd=consumer, phase='consumer', env=run_env,
                name='make_input', timeout=180)

    session.run([str(consumer / 'consumer'),
                 str(consumer / 'input.tiff'), str(consumer / 'output.png')],
                cwd=consumer, phase='consumer', env=run_env,
                name='run_consumer', timeout=300)

    out_png = consumer / 'output.png'
    if not out_png.is_file():
        raise RuntimeError('consumer did not produce %s' % out_png)

    session.run([str(magick), 'identify', '-format', '%wx%h %m %[colorspace]',
                 str(out_png)],
                cwd=consumer, phase='consumer', env=run_env,
                name='verify_output', timeout=180)

    session.finish(features={
        'cli': 'magick',
        'sdk': ['MagickWand'],
        'formats': {'PNG': True, 'JPEG': True, 'TIFF': True},
        'quantum_depth': 16,
        'header_layout': 'MagickWand/MagickWand.h (ImageMagick 7)',
        'jobs_build': jobs,
        'jobs_test': 2,
    })
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='BUILDv1-C03',
        description='Build + test ImageMagick from the frozen source archive.')
    sub = parser.add_subparsers(dest='command')
    run_p = sub.add_parser('run', help='full build/install/test/consumer pipeline')
    run_p.add_argument('--input', required=True)
    run_p.add_argument('--output', required=True)
    run_p.add_argument('--jobs', type=int, default=4)
    doc_p = sub.add_parser('doctor', help='report missing sources/tools/dependencies')
    doc_p.add_argument('--input', required=True)
    args = parser.parse_args(argv)
    if args.command == 'doctor':
        return doctor(args.input)
    if args.command == 'run':
        return do_run(args.input, args.output, args.jobs)
    parser.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
