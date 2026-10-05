#!/usr/bin/env python3
"""Build NumPy 2.2.6 from its official source sdist, install it into a plain
prefix, and verify it with the upstream non-slow linalg suite plus independent
functional and native consumers.

Every build/configure/install/test/consumer command goes through the trusted
`buildkit` helper so exit codes and logs are preserved.

Rules enforced here:
  * The delivered install prefix contains ONLY the newly built NumPy package.
    The bootstrap consumer venv lives at /workspace/consumer/venv, never in the
    install tree (an interpreter symlink inside the SDK is rejected).
  * Every installed-wheel import/probe/test/consumer runs with
    cwd=/workspace/consumer and a sanitized PYTHONPATH, so the source tree is
    never accidentally imported.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import buildkit

HERE = Path(__file__).resolve().parent
WHEELHOUSE = Path(os.environ.get("WHEELHOUSE", "/opt/wheelhouse"))
CONSUMER = Path("/workspace/consumer")

REQUIRED_TOOLS = ["gcc", "g++", "pkg-config", "meson", "ninja", "python3"]
REQUIRED_WHEELS = [
    "build", "meson-python", "Cython", "ninja", "packaging",
    "pyproject-hooks", "pytest", "hypothesis", "pluggy", "iniconfig",
    "attrs", "sortedcontainers",
]
SUBMODULE_MARKERS = [
    "pocketfft_hdronly.h",
    "npysort/x86-simd-sort/",
    "src/highway/",
    "pythoncapi-compat/",
]


def _norm(name):
    return name.lower().replace("_", "-").replace(".", "-")


def _ok(argv):
    try:
        return subprocess.run(argv, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT).returncode == 0
    except (FileNotFoundError, OSError):
        return False


def wheelhouse_names():
    names = set()
    if WHEELHOUSE.is_dir():
        for entry in WHEELHOUSE.iterdir():
            if entry.suffix == ".whl":
                names.add(_norm(entry.name.split("-")[0]))
    return names


def blas_names():
    found = [pc for pc in ("openblas", "blas", "lapack")
             if _ok(["pkg-config", "--exists", pc])]
    if found:
        return ["pkg-config:" + pc for pc in found]
    try:
        out = subprocess.run(["ldconfig", "-p"], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True).stdout
    except (FileNotFoundError, OSError):
        out = ""
    return ["lib:" + lib for lib in ("libopenblas", "libblas") if lib in out]


def archive_names(archive):
    names = set()
    with tarfile.open(archive) as tar:
        for member in tar:
            names.add(member.name)
    return names


def doctor(input_dir):
    input_dir = Path(input_dir)
    missing = []
    manifest = None
    try:
        manifest = json.loads((input_dir / "manifest.json").read_text())
    except Exception as exc:  # noqa: BLE001
        missing.append("manifest.json: %s" % exc)

    archive = None
    if manifest:
        archive = input_dir / manifest["source"]["filename"]
        if not archive.is_file():
            missing.append("source archive: %s" % archive)
            archive = None
        elif buildkit.digest(archive) != manifest["source"]["sha256"]:
            missing.append("source archive checksum mismatch: %s" % archive.name)
            archive = None

    if archive:
        try:
            names = archive_names(archive)
        except Exception as exc:  # noqa: BLE001
            names = set()
            missing.append("cannot read source archive: %s" % exc)
        if not any(n.endswith("vendored-meson/meson/meson.py") for n in names) \
                and shutil.which("meson") is None:
            missing.append("meson (no vendored-meson/meson/meson.py and no system meson)")
        for marker in SUBMODULE_MARKERS:
            if not any(marker in n for n in names):
                missing.append("vendored submodule content: %s" % marker)

    for tool in REQUIRED_TOOLS:
        if shutil.which(tool) is None:
            missing.append("tool: %s" % tool)
    if not _ok([sys.executable, "-c", "import venv, ensurepip"]):
        missing.append("python modules: venv/ensurepip")
    if not WHEELHOUSE.is_dir():
        missing.append("dependency wheelhouse: %s" % WHEELHOUSE)
    have = wheelhouse_names()
    for wheel in REQUIRED_WHEELS:
        if _norm(wheel) not in have:
            missing.append("dependency wheel: %s" % wheel)
    blas = blas_names()
    if not blas:
        missing.append("BLAS/LAPACK (pkg-config blas/openblas or libopenblas/libblas)")

    print(json.dumps({"input": str(input_dir), "ready": not missing,
                      "blas": blas, "missing": missing}, indent=2))
    return 0 if not missing else 78


def consumer_env(extra=None):
    """Env for consumer commands: no inherited PYTHONPATH, no source tree."""
    env = {"PYTHONPATH": "",
           "OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2",
           "MKL_NUM_THREADS": "2", "PIP_NO_INPUT": "1",
           "PIP_DISABLE_PIP_VERSION_CHECK": "1"}
    if extra:
        env.update(extra)
    return env


def capture_last_line(session, argv, **kwargs):
    log = session.run(argv, **kwargs)
    lines = [ln for ln in log.read_text(errors="replace").splitlines() if ln.strip()]
    return lines[-1].strip()


def run(input_dir, output_dir, jobs):
    session = buildkit.Session(input_dir, output_dir, jobs)
    src = session.prepare()

    vendored_meson = src / "vendored-meson" / "meson" / "meson.py"
    if not vendored_meson.is_file():
        vendored_meson.parent.mkdir(parents=True, exist_ok=True)
        vendored_meson.write_text(
            "#!/usr/bin/env python3\nimport os, sys\n"
            "os.execvp('meson', ['meson'] + sys.argv[1:])\n")
        vendored_meson.chmod(0o755)
    for script in (src / "numpy" / "_build_utils").glob("*.py"):
        script.chmod(0o755)

    # --- isolated build environment (outside the delivered install prefix) ---
    build_venv = session.build / "venv"
    session.run([sys.executable, "-m", "venv", str(build_venv)],
                phase="setup", name="create_build_venv")
    bpy = build_venv / "bin" / "python"
    session.run([str(bpy), "-m", "pip", "install", "--no-index",
                 "--find-links", str(WHEELHOUSE), "build", "meson-python",
                 "Cython", "ninja", "packaging", "pyproject-hooks"],
                phase="setup", name="install_build_deps",
                env=consumer_env())

    build_env = consumer_env({
        "PATH": str(build_venv / "bin") + os.pathsep + os.environ.get("PATH", ""),
        "NINJAFLAGS": "-j%d" % session.jobs})
    session.run([str(bpy), "-m", "build", "--wheel", "--no-isolation",
                 "-Csetup-args=-Dallow-noblas=false",
                 "--outdir", str(session.output), str(src)],
                cwd=str(src), phase="build", name="build_wheel", env=build_env,
                timeout=10800)

    wheels = sorted(session.output.glob("numpy-*.whl"))
    if not wheels:
        raise RuntimeError("no NumPy wheel was produced")
    wheel = wheels[-1]
    wheel_sha = buildkit.digest(wheel)

    # --- consumer venv: no system site-packages, outside src and install ---
    cvenv = CONSUMER / "venv"
    if cvenv.exists():
        shutil.rmtree(cvenv)
    CONSUMER.mkdir(parents=True, exist_ok=True)
    session.run([sys.executable, "-m", "venv", str(cvenv)],
                phase="setup", name="create_consumer_venv", cwd=str(CONSUMER))
    cpy = cvenv / "bin" / "python"
    session.run([str(cpy), "-m", "pip", "install", "--no-index",
                 "--find-links", str(WHEELHOUSE), "pytest", "hypothesis"],
                phase="setup", name="install_test_deps", cwd=str(CONSUMER),
                env=consumer_env())
    session.run([str(cpy), "-m", "pip", "install", "--no-index", "--no-deps",
                 str(wheel)], phase="install", name="install_wheel_consumer",
                cwd=str(CONSUMER), env=consumer_env())

    # --- installed prefix: only the NumPy package, no interpreter/venv ---
    session.run([str(cpy), "-m", "pip", "install", "--no-index", "--no-deps",
                 "--target", str(session.install), str(wheel)],
                phase="install", name="install_wheel_prefix",
                cwd=str(CONSUMER), env=consumer_env())
    if not (session.install / "numpy" / "__init__.py").is_file():
        raise RuntimeError("installed prefix does not contain the NumPy package")

    test_env = consumer_env()

    inventory = session.run([str(cpy), "-m", "pytest", "--pyargs", "numpy.linalg",
                             "-m", "not slow", "--collect-only", "-q",
                             "-p", "no:cacheprovider"],
                            cwd=str(CONSUMER), phase="official_test",
                            name="collect_inventory", env=test_env, timeout=1800)
    (session.output / "tests_inventory.txt").write_text(inventory.read_text(errors="replace"))

    session.test("numpy.linalg official (not slow)",
                 [str(cpy), "-m", "pytest", "--pyargs", "numpy.linalg", "-m", "not slow",
                  "-q", "-p", "no:cacheprovider"],
                 cwd=str(CONSUMER), env=test_env, timeout=5400)

    session.run([str(cpy), str(HERE / "consumer_linalg.py")],
                cwd=str(CONSUMER), phase="consumer", name="consumer_linalg",
                env=test_env)

    # All import/probe/compile commands MUST run outside the source tree.
    include = capture_last_line(session,
                                [str(cpy), "-c", "import numpy; print(numpy.get_include())"],
                                cwd=str(CONSUMER), phase="consumer", name="numpy_include",
                                env=test_env)
    py_include = capture_last_line(
        session,
        [str(cpy), "-c", "import sysconfig; print(sysconfig.get_paths()['include'])"],
        cwd=str(CONSUMER), phase="consumer", name="python_include", env=test_env)
    so_path = session.build / "consumer_cext.so"
    session.run(["gcc", "-shared", "-fPIC", "-O2", "-I" + include, "-I" + py_include,
                 str(HERE / "consumer_cext.c"), "-o", str(so_path)],
                cwd=str(CONSUMER), phase="consumer", name="cext_compile", env=test_env)
    session.run([str(cpy), str(HERE / "consumer_cext_check.py"), str(session.build)],
                cwd=str(CONSUMER), phase="consumer", name="cext_check", env=test_env)

    session.finish(features={"wheel": wheel.name, "wheel_sha256": wheel_sha,
                             "blas": blas_names(),
                             "scope": "core: full source-built wheel + numpy.linalg non-slow tests",
                             "consumer": "linalg/fft/rng/.npy + NumPy C-API extension"})
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="numpy-source-build",
        description="Build NumPy 2.2.6 from the official source sdist, install and verify it.")
    sub = parser.add_subparsers(dest="command")
    doc = sub.add_parser("doctor",
                         help="report missing source/tool/dependency items (exit 78 if missing)")
    doc.add_argument("--input", required=True,
                     help="directory holding manifest.json and the source archive")
    runp = sub.add_parser("run", help="configure, compile, package, install, test and verify")
    runp.add_argument("--input", required=True)
    runp.add_argument("--output", required=True)
    runp.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return doctor(args.input)
    if args.command == "run":
        return run(args.input, args.output, args.jobs)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
