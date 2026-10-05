#!/usr/bin/env python3
"""OpenCV 4.11.0 CPU core SDK source builder (frozen CORE profile).

The official suites are invoked with the real upstream option
``--gtest_catch_exceptions=0`` (implemented by the bundled gtest copy and
read via ``::testing::GTEST_FLAG(catch_exceptions)`` at
modules/ts/src/ts.cpp:293 and :565).  It disables the setjmp/longjmp
SIGABRT handler so a first signal is reported once and terminates the
process instead of an endless stack-canary catch-loop.

Zlib configuration: OpenCV's own ``BUILD_ZLIB=ON`` publishes a bare
``zlib`` target that leaks into the link line of the Debian-packaged
OpenEXR/Imath stack (which uses ``find_dependency(ZLIB)``); the linker
then cannot resolve ``zlib``.  We therefore run with ``BUILD_ZLIB=OFF``
and pin the genuine preinstalled system zlib (``libz.so`` plus
``/usr/include``) so OpenEXR/TIFF/PNG all share a coherent system zlib.
No codec, test, or expectation is disabled.
"""
import argparse
import json
import os
import shutil
import sys
import tarfile
from pathlib import Path

from buildkit import Session, digest  # trusted plumbing

TARGET_MODULES = ["core", "imgproc", "imgcodecs", "ts"]
MANDATORY_TESTS = ["opencv_test_core", "opencv_test_imgproc", "opencv_test_imgcodecs"]
REQUIRED_TOOLS = ["cmake", "ninja", "gcc", "g++"]

GTEST_CATCH_EXCEPTIONS_ARG = "--gtest_catch_exceptions=0"
GTEST_CATCH_EXCEPTIONS_ENV = "GTEST_CATCH_EXCEPTIONS"

# The canonical hydrated location declared by manifest.opencv_official_testdata.path.
CANONICAL_TESTDATA = Path("/workspace/cache/opencv_extra/testdata")

CONSUMER_CPP = r'''#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/imgcodecs.hpp>
#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

static void require(bool cond, const std::string& msg) {
    if (!cond) { std::cerr << "FAIL: " << msg << "\n"; std::exit(2); }
}

int main(int argc, char** argv) {
    std::string outdir = argc > 1 ? argv[1] : ".";
    std::cout << "OpenCV version: " << CV_VERSION << "\n";

    cv::Mat img(200, 300, CV_8UC3, cv::Scalar(30, 30, 30));
    cv::rectangle(img, cv::Rect(50, 50, 100, 80), cv::Scalar(0, 0, 255), cv::FILLED);
    cv::circle(img, cv::Point(220, 120), 40, cv::Scalar(0, 255, 0), cv::FILLED);

    std::vector<uchar> buf;
    require(cv::imencode(".png", img, buf), "imencode failed");
    cv::Mat decoded = cv::imdecode(buf, cv::IMREAD_COLOR);
    require(!decoded.empty() && decoded.size() == img.size(), "imdecode size mismatch");
    require(cv::norm(decoded, img, cv::NORM_INF) <= 1, "PNG round-trip mismatch");

    cv::Mat gray;
    cv::cvtColor(img, gray, cv::COLOR_BGR2GRAY);
    cv::Mat mask;
    cv::inRange(img, cv::Scalar(0, 0, 200), cv::Scalar(60, 60, 255), mask);
    int red = cv::countNonZero(mask);
    require(red > 7000 && red < 8200, "red region size unexpected");

    cv::Mat blur, edges;
    cv::GaussianBlur(gray, blur, cv::Size(5, 5), 1.2);
    cv::Canny(blur, edges, 40, 120);
    int edge_nz = cv::countNonZero(edges);
    require(edge_nz > 100, "canny produced too few edges");

    cv::Mat small;
    cv::resize(img, small, cv::Size(), 0.5, 0.5, cv::INTER_AREA);
    require(small.cols == 150 && small.rows == 100, "resize dims");

    require(cv::imwrite(outdir + "/consumer_original.png", img), "imwrite original");
    require(cv::imwrite(outdir + "/consumer_mask.png", mask), "imwrite mask");
    require(cv::imwrite(outdir + "/consumer_edges.png", edges), "imwrite edges");

    std::cout << "OK red_pixels=" << red << " edges=" << edge_nz
              << " size=" << img.cols << "x" << img.rows << "\n";
    return 0;
}
'''

CONSUMER_CMAKE = r'''cmake_minimum_required(VERSION 3.10)
project(vision_consumer CXX)
set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(OpenCV REQUIRED COMPONENTS core imgproc imgcodecs)
message(STATUS "Using OpenCV include: ${OpenCV_INCLUDE_DIRS}")
message(STATUS "Using OpenCV libraries: ${OpenCV_LIBS}")
add_executable(vision_consumer main.cpp)
target_link_libraries(vision_consumer PRIVATE ${OpenCV_LIBS})
'''


def _valid_testdata(path):
    """A real opencv_extra/testdata tree always contains a cv/ subtree."""
    try:
        p = Path(path)
    except Exception:  # noqa: BLE001
        return None
    if p.is_dir() and (p / "cv").is_dir():
        return p
    return None


def _declared_testdata_paths(manifest):
    """Manifest-declared testdata locations, in priority order."""
    paths = []
    if not isinstance(manifest, dict):
        return paths
    td = manifest.get("opencv_official_testdata") or {}
    declared = td.get("path")
    if declared:
        base = Path(declared)
        paths.extend([base, base / "testdata", base.parent / "testdata"])
    for cache in manifest.get("dependency_caches") or []:
        dest = cache.get("destination") if isinstance(cache, dict) else None
        if dest:
            base = Path(dest)
            paths.extend([base, base / "testdata"])
    return paths


def _find_test_data(input_dir, output_dir, manifest=None):
    """Locate a real upstream opencv_extra/testdata tree; never fabricate one."""
    input_dir = Path(input_dir)
    candidates = []
    env_value = os.environ.get("OPENCV_TEST_DATA_PATH")
    if env_value:
        candidates.append(Path(env_value))
    candidates.extend(_declared_testdata_paths(manifest))
    candidates.extend([
        CANONICAL_TESTDATA,
        Path("/workspace/cache/opencv_extra"),
        Path("/workspace/cache/testdata"),
        input_dir / "opencv_extra" / "testdata",
        input_dir / "opencv_extra",
        input_dir / "testdata",
        Path("/workspace/opencv_extra/testdata"),
        Path("/opt/opencv_extra/testdata"),
    ])
    for candidate in candidates:
        found = _valid_testdata(candidate)
        if found is not None:
            return found

    for root in (input_dir, Path("/workspace/cache")):
        if not root.exists():
            continue
        try:
            for candidate in root.rglob("testdata"):
                found = _valid_testdata(candidate)
                if found is not None:
                    return found
        except OSError:
            pass

    extract_root = Path(output_dir) / "extracted_testdata"
    for bundle_root in (input_dir, Path("/workspace/cache")):
        if not bundle_root.exists():
            continue
        bundles = (list(bundle_root.glob("opencv_extra*.tar*")) +
                   list(bundle_root.glob("opencv_extra*.tgz")))
        for bundle in bundles:
            if not bundle.is_file():
                continue
            extract_root.mkdir(parents=True, exist_ok=True)
            try:
                with tarfile.open(bundle) as archive:
                    for member in archive.getmembers():
                        parts = Path(member.name).parts
                        if not parts or ".." in parts or Path(member.name).is_absolute():
                            raise ValueError("unsafe archive member")
                        archive.extract(member, extract_root, filter="data")
            except Exception:  # noqa: BLE001
                continue
            for candidate in extract_root.rglob("testdata"):
                found = _valid_testdata(candidate)
                if found is not None:
                    return found
    return None


def _find_system_zlib():
    """Locate the preinstalled zlib development shared object.

    ``BUILD_ZLIB=OFF`` links the whole image-codec stack (PNG/TIFF/OpenEXR)
    against system zlib, so a real ``libz.so`` must exist.  Nothing is
    fabricated here -- an absent library is reported honestly.
    """
    candidates = []
    try:
        import ctypes.util
        found = ctypes.util.find_library("z")
        if found:
            candidates.append(Path(found))
    except Exception:  # noqa: BLE001
        pass
    candidates.extend([
        Path("/usr/lib/x86_64-linux-gnu/libz.so"),
        Path("/lib/x86_64-linux-gnu/libz.so"),
        Path("/usr/lib64/libz.so"),
        Path("/usr/lib/libz.so"),
    ])
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            pass
    for root in (Path("/usr/lib"), Path("/usr/lib64"), Path("/lib")):
        if not root.exists():
            continue
        try:
            for candidate in root.rglob("libz.so*"):
                if candidate.is_file():
                    return candidate
        except OSError:
            pass
    return None


def doctor(input_dir):
    """Report exact missing source / tool / dependency items; 78 if missing."""
    input_dir = Path(input_dir).resolve()
    missing = []
    manifest_path = input_dir / "manifest.json"
    if not manifest_path.is_file():
        return [f"source manifest missing: {manifest_path}"]
    try:
        manifest = json.loads(manifest_path.read_text())
    except Exception as exc:  # noqa: BLE001
        return [f"source manifest unreadable: {exc}"]

    source = manifest.get("source") or {}
    archive = input_dir / str(source.get("filename", "source.tar.gz"))
    if not archive.is_file():
        missing.append(f"source archive missing: {archive}")
    else:
        try:
            if digest(archive) != source.get("sha256"):
                missing.append(f"source archive sha256 mismatch: {archive}")
        except OSError as exc:
            missing.append(f"source archive unreadable: {exc}")

    for tool in REQUIRED_TOOLS:
        if shutil.which(tool) is None:
            missing.append(f"build tool missing on PATH: {tool}")

    if _find_system_zlib() is None:
        missing.append(
            "system zlib development library missing; BUILD_ZLIB=OFF "
            "requires /usr/lib/x86_64-linux-gnu/libz.so (or libz.so* ) "
            "plus /usr/include/zlib.h")
    if not Path("/usr/include/zlib.h").is_file():
        missing.append("system zlib header missing: /usr/include/zlib.h")

    declared = _declared_testdata_paths(manifest)
    if declared and not any(_valid_testdata(p) is not None for p in declared):
        missing.append(
            "official opencv_extra/testdata not hydrated (no cv/ subdir at any declared path): "
            + ", ".join(str(p) for p in declared))
    return missing


def _configure_args(src, build, install, download, zlib_lib):
    return [
        "cmake", "-S", str(src), "-B", str(build), "-G", "Ninja",
        f"-DCMAKE_INSTALL_PREFIX={install}",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_PREFIX_PATH=/usr",
        "-DBUILD_SHARED_LIBS=ON",
        f"-DBUILD_LIST={','.join(TARGET_MODULES)}",
        "-DBUILD_TESTS=ON",
        "-DBUILD_PERF_TESTS=OFF",
        "-DBUILD_EXAMPLES=OFF",
        "-DBUILD_DOCS=OFF",
        "-DBUILD_opencv_apps=OFF",
        "-DBUILD_JAVA=OFF",
        "-DBUILD_opencv_python2=OFF",
        "-DBUILD_opencv_python3=OFF",
        "-DBUILD_JPEG=ON",
        "-DBUILD_PNG=ON",
        "-DBUILD_TIFF=ON",
        # Coherent system zlib: never publish a bare ``zlib`` target that
        # leaks into the Debian OpenEXR/Imath link interface.
        "-DBUILD_ZLIB=OFF",
        f"-DZLIB_LIBRARY={zlib_lib}",
        f"-DZLIB_LIBRARIES={zlib_lib}",
        "-DZLIB_INCLUDE_DIR=/usr/include",
        "-DZLIB_ROOT=/usr",
        "-DBUILD_WEBP=OFF",
        "-DBUILD_OPENEXR=OFF",
        "-DBUILD_JASPER=OFF",
        "-DWITH_CUDA=OFF",
        "-DWITH_OPENCL=OFF",
        "-DWITH_GTK=OFF",
        "-DWITH_QT=OFF",
        "-DWITH_IPP=OFF",
        "-DWITH_ITT=OFF",
        "-DWITH_TBB=OFF",
        "-DWITH_OPENMP=OFF",
        "-DWITH_EIGEN=OFF",
        "-DWITH_LAPACK=OFF",
        "-DWITH_FFMPEG=OFF",
        "-DWITH_V4L=OFF",
        "-DWITH_GSTREAMER=OFF",
        "-DWITH_PROTOBUF=OFF",
        "-DBUILD_PROTOBUF=OFF",
        "-DOPENCV_ENABLE_NONFREE=OFF",
        "-DOPENCV_GENERATE_PKGCONFIG=ON",
        f"-DOPENCV_DOWNLOAD_PATH={download}",
    ]


def _snapshot_test_binaries(bin_dir, diagnostic_dir, names):
    """Copy upstream test binaries to output/diagnostic for offline evidence.

    Deliberately OUTSIDE output/install so they can never be mistaken for
    the delivered SDK.
    """
    diagnostic_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in names:
        src = bin_dir / name
        if src.is_file():
            dst = diagnostic_dir / name
            shutil.copy2(src, dst)
            copied.append({"name": name, "path": str(dst),
                           "bytes": dst.stat().st_size, "sha256": digest(dst)})
    return copied


def _package_install(session):
    files = [p for p in session.install.rglob("*") if p.is_file() and not p.is_symlink()]
    session.write("install_manifest.json",
                  [{"path": str(p.relative_to(session.install)),
                    "bytes": p.stat().st_size,
                    "sha256": digest(p)} for p in files])
    if files:
        with tarfile.open(session.output / "install.tar.gz", "w:gz") as archive:
            archive.add(session.install, arcname="install")
    return files


def run_build(args):
    input_dir = Path(args.input).resolve()
    if not (input_dir / "manifest.json").is_file():
        print("MISSING: manifest.json", file=sys.stderr)
        return 78

    session = Session(args.input, args.output, jobs=args.jobs)
    session.prepare()
    src, build_dir, install_dir = session.src, session.build, session.install

    download_dir = Path(args.output) / "opencv_download"
    download_dir.mkdir(parents=True, exist_ok=True)
    xml_dir = (Path(args.output) / "xml").resolve()
    xml_dir.mkdir(parents=True, exist_ok=True)
    diagnostic_dir = (Path(args.output) / "diagnostic").resolve()

    zlib_lib = _find_system_zlib()
    if zlib_lib is None:
        print("MISSING: system zlib development library (BUILD_ZLIB=OFF)",
              file=sys.stderr)
        return 78
    if not Path("/usr/include/zlib.h").is_file():
        print("MISSING: /usr/include/zlib.h (system zlib development)",
              file=sys.stderr)
        return 78

    session.run(_configure_args(src, build_dir, install_dir, download_dir, zlib_lib),
                cwd=src, phase="configure", name="cmake_configure", timeout=2400)
    session.run(["cmake", "--build", str(build_dir), "--parallel", str(session.jobs)],
                cwd=build_dir, phase="build", name="cmake_build", timeout=14400)
    session.run(["cmake", "--install", str(build_dir)],
                cwd=build_dir, phase="install", name="cmake_install", timeout=1800)

    opencv_dir = install_dir / "lib" / "cmake" / "opencv4"
    if not (opencv_dir / "OpenCVConfig.cmake").is_file():
        raise RuntimeError(f"install did not produce CMake package: {opencv_dir}")

    bin_dir = build_dir / "bin"
    for name in MANDATORY_TESTS:
        if not (bin_dir / name).is_file():
            raise RuntimeError(f"mandatory test binary missing: {bin_dir / name}")

    copied = _snapshot_test_binaries(bin_dir, diagnostic_dir, MANDATORY_TESTS)
    session.write("diagnostic_binaries.json", copied)

    # LC_ALL=C: OpenCV FileStorage numeric parsing and the ts gtest float
    # comparisons assume the classic C locale (see the upstream comment in
    # modules/core/test/test_misc.cpp).
    test_env = {
        "LC_ALL": "C",
        "LANG": "C",
        "LC_NUMERIC": "C",
        GTEST_CATCH_EXCEPTIONS_ENV: "0",
    }

    test_data = _find_test_data(input_dir, args.output, session.manifest)
    if test_data is not None:
        test_env["OPENCV_TEST_DATA_PATH"] = str(test_data)
    session.write("test_environment.json", {
        "env": dict(test_env),
        "test_data_path": str(test_data) if test_data else None,
        "test_data_found": test_data is not None,
        "canonical_testdata": str(CANONICAL_TESTDATA),
        "canonical_testdata_valid": _valid_testdata(CANONICAL_TESTDATA) is not None,
        "system_zlib": str(zlib_lib),
    })

    session.write("test_options.json", {
        "gtest_catch_exceptions": {
            "arg": GTEST_CATCH_EXCEPTIONS_ARG,
            "env": {GTEST_CATCH_EXCEPTIONS_ENV: "0"},
            "defined_by": [
                "modules/ts/src/ts_gtest.cpp (implementation)",
                "modules/ts/src/ts.cpp:293 (GTEST_FLAG(catch_exceptions) gate)",
                "modules/ts/src/ts.cpp:565 (GTEST_FLAG(catch_exceptions) gate)",
            ],
            "reason": (
                "disables the setjmp/longjmp SIGABRT handler so the first signal "
                "is reported once and terminates the process instead of an "
                "endless stack-canary catch-loop"),
        },
        "filtering_applied": None,
        "cases_excluded": [],
        "modules_removed": [],
        "stack_protector_changes": None,
    })

    session.run(["ls", "-1", str(bin_dir)], cwd=bin_dir, phase="test_discovery",
                name="test_inventory", timeout=120)

    base_test_argv = [GTEST_CATCH_EXCEPTIONS_ARG, "--gtest_color=no"]
    if test_data is not None:
        base_test_argv.append(f"--test_data_path={test_data}")

    failed_tests = []
    for name in MANDATORY_TESTS:
        xml = xml_dir / f"{name}.xml"
        argv = [str(bin_dir / name)] + base_test_argv + [f"--gtest_output=xml:{xml}"]
        try:
            session.test(name, argv, cwd=bin_dir, env=test_env, timeout=3600)
        except RuntimeError as exc:
            failed_tests.append({"name": name, "reason": str(exc)[:4000]})
            print(f"OFFICIAL TEST FAILED: {name}", file=sys.stderr)

    consumer = session.consumer
    (consumer / "src").mkdir(parents=True, exist_ok=True)
    (consumer / "build").mkdir(parents=True, exist_ok=True)
    (consumer / "out").mkdir(parents=True, exist_ok=True)
    (consumer / "src" / "main.cpp").write_text(CONSUMER_CPP)
    (consumer / "src" / "CMakeLists.txt").write_text(CONSUMER_CMAKE)

    session.run(["cmake", "-S", str(consumer / "src"), "-B", str(consumer / "build"),
                 "-G", "Ninja", f"-DOpenCV_DIR={opencv_dir}", "-DCMAKE_BUILD_TYPE=Release"],
                cwd=consumer, phase="consumer", name="consumer_configure", timeout=900)
    session.run(["cmake", "--build", str(consumer / "build")],
                cwd=consumer, phase="consumer", name="consumer_build", timeout=900)
    run_log = session.run([str(consumer / "build" / "vision_consumer"), str(consumer / "out")],
                          cwd=consumer, phase="consumer", name="consumer_run", timeout=300,
                          env={"LD_LIBRARY_PATH": str(install_dir / "lib")})
    run_text = run_log.read_text(errors="replace")
    if "OK red_pixels=" not in run_text:
        raise RuntimeError("consumer functional verification failed:\n" + run_text[-2000:])

    if failed_tests:
        _package_install(session)
        session.write("official_test_failures.json", {
            "failed": failed_tests,
            "count": len(failed_tests),
            "test_data_path": str(test_data) if test_data else None,
            "test_data_found": test_data is not None,
        })
        print(
            "Official OpenCV accuracy tests failed; refusing to declare "
            "successful completion. See output/logs and output/xml.\n"
            f"Failing selectors: {[t['name'] for t in failed_tests]}",
            file=sys.stderr)
        return 1

    if not session.tests:
        raise RuntimeError("no official test evidence recorded")

    session.finish(features={
        "modules": TARGET_MODULES,
        "official_tests": MANDATORY_TESTS,
        "install_prefix": str(install_dir),
        "consumer": "vision_consumer",
        "test_data_path": str(test_data) if test_data else None,
        "gtest_options": [GTEST_CATCH_EXCEPTIONS_ARG, f"{GTEST_CATCH_EXCEPTIONS_ENV}=0"],
        "system_zlib": str(zlib_lib),
        "diagnostic_binaries": [c["name"] for c in copied],
    })
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="solution/main.py",
        description="OpenCV 4.11.0 CPU core SDK source builder")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run", help="configure, build, install, test and verify")
    run_p.add_argument("--input", required=True, help="read-only input directory")
    run_p.add_argument("--output", required=True, help="writable output directory")
    run_p.add_argument("--jobs", type=int, default=4, help="build parallelism (<=4)")
    doc_p = sub.add_parser("doctor", help="report missing source/tool/dependency items")
    doc_p.add_argument("--input", required=True)
    args = parser.parse_args(argv)

    if args.cmd == "doctor":
        missing = doctor(args.input)
        if missing:
            for item in missing:
                print(f"MISSING: {item}")
            return 78
        print("READY")
        return 0

    return run_build(args)


if __name__ == "__main__":
    sys.exit(main())
