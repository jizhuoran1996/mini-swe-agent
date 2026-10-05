#!/usr/bin/env python3
"""OpenCV 4.11.0 CPU core SDK source builder.

Frozen CORE profile: exact source build of
  core, imgproc, imgcodecs, ts
plus the official accuracy tests
  opencv_test_core, opencv_test_imgproc, opencv_test_imgcodecs,
an installed CMake package, and an independently compiled consumer that
links only the freshly installed tree.

Bounded diagnostic (from the retained failure):
  The full `opencv_test_core` run reached `BufferArea.bad/1` and then
  emitted ~7.9 GB of repeating glibc `*** stack smashing detected ***`
  messages until the 128 MiB per-command log cap killed it.

  The root cause of the *loop* lives in `modules/ts/src/ts.cpp`: OpenCV's
  ts framework installs a SIGABRT handler gated on
  `::testing::GTEST_FLAG(catch_exceptions)` (lines 293, 565).  The
  handler is built on `setjmp`/`longjmp`; the aborts raised by the glibc
  stack canary are caught, `longjmp` re-enters the failing path and the
  canary check fires again, forever.

  `modules/ts/src/ts_gtest.cpp` documents and implements the real
  supported option `--gtest_catch_exceptions=0` (and its env form
  `GTEST_CATCH_EXCEPTIONS=0`).  Passing it removes the recursive
  longjmp handler so the FIRST signal is reported once and the process
  terminates.  No case is filtered, no expectation is modified, no
  module is dropped and the stack protector is left enabled.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

from buildkit import Session, digest  # trusted plumbing

TARGET_MODULES = ["core", "imgproc", "imgcodecs", "ts"]
MANDATORY_TESTS = ["opencv_test_core", "opencv_test_imgproc", "opencv_test_imgcodecs"]
REQUIRED_TOOLS = ["cmake", "ninja", "gcc", "g++"]

# Real option shipped by OpenCV's ts copy of gtest: see
# modules/ts/src/ts_gtest.cpp and the GTEST_FLAG(catch_exceptions) checks
# at modules/ts/src/ts.cpp:293 and :565.  It is the supported way to
# disable the setjmp/longjmp SIGABRT handler so a first real fault is not
# turned into an endless catch-loop.
GTEST_CATCH_EXCEPTIONS_ARG = "--gtest_catch_exceptions=0"
GTEST_CATCH_EXCEPTIONS_ENV = "GTEST_CATCH_EXCEPTIONS"

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


def _find_test_data(input_dir):
    for candidate in (
        Path(input_dir) / "opencv_extra" / "testdata",
        Path("/workspace/input/opencv_extra/testdata"),
        Path("/workspace/opencv_extra/testdata"),
    ):
        if candidate.is_dir():
            return candidate
    return None


def doctor(input_dir):
    """Return the list of missing source/tool/dependency items."""
    input_dir = Path(input_dir).resolve()
    manifest_path = input_dir / "manifest.json"
    if not manifest_path.is_file():
        return [f"source manifest missing: {manifest_path}"]
    try:
        manifest = json.loads(manifest_path.read_text())
    except Exception as exc:  # noqa: BLE001
        return [f"source manifest unreadable: {exc}"]
    missing = []
    archive = input_dir / manifest["source"]["filename"]
    if not archive.is_file():
        missing.append(f"source archive missing: {archive}")
    else:
        try:
            if digest(archive) != manifest["source"]["sha256"]:
                missing.append(f"source archive sha256 mismatch: {archive}")
        except OSError as exc:
            missing.append(f"source archive unreadable: {exc}")
    for tool in REQUIRED_TOOLS:
        if shutil.which(tool) is None:
            missing.append(f"build tool missing on PATH: {tool}")
    return missing


def _configure_args(src, build, install, download):
    return [
        "cmake", "-S", str(src), "-B", str(build), "-G", "Ninja",
        f"-DCMAKE_INSTALL_PREFIX={install}",
        "-DCMAKE_BUILD_TYPE=Release",
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
        "-DBUILD_ZLIB=ON",
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
        "-DWITH_OPENEXR=OFF",
        "-DWITH_JASPER=OFF",
        "-DOPENCV_ENABLE_NONFREE=OFF",
        "-DOPENCV_GENERATE_PKGCONFIG=ON",
        f"-DOPENCV_DOWNLOAD_PATH={download}",
    ]


def _snapshot_test_binaries(bin_dir, diagnostic_dir, names):
    """Copy the upstream test binaries to output/diagnostic.

    These are preserved evidence -- the exact bits that produced the logs
    -- so the original core fault can be reproduced later without a
    rebuild.  They are NOT part of the installed delivery and are not
    placed under output/install, so they cannot be mistaken for the SDK.
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


def run_build(args):
    input_dir = Path(args.input).resolve()
    if not (input_dir / "manifest.json").is_file():
        print("MISSING: manifest.json", file=sys.stderr)
        raise SystemExit(78)

    session = Session(args.input, args.output, jobs=args.jobs)
    session.prepare()
    src, build_dir, install_dir = session.src, session.build, session.install
    download_dir = Path(args.output) / "opencv_download"
    download_dir.mkdir(parents=True, exist_ok=True)
    xml_dir = (Path(args.output) / "xml").resolve()
    xml_dir.mkdir(parents=True, exist_ok=True)
    diagnostic_dir = (Path(args.output) / "diagnostic").resolve()

    session.run(_configure_args(src, build_dir, install_dir, download_dir),
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

    # Preserve the exact upstream test binaries as bounded diagnostic
    # evidence before running them.
    copied = _snapshot_test_binaries(bin_dir, diagnostic_dir, MANDATORY_TESTS)
    session.write("diagnostic_binaries.json", copied)

    env = {
        "OPENCV_TEST_NUM_THREADS": "1",
        GTEST_CATCH_EXCEPTIONS_ENV: "0",
    }
    test_data = _find_test_data(input_dir)
    if test_data is not None:
        env["OPENCV_TEST_DATA_PATH"] = str(test_data)

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
                "disables the setjmp/longjmp SIGABRT handler so the first "
                "signal is reported once and terminates the process instead "
                "of an endless stack-canary catch-loop"),
        },
        "filtering_applied": None,
        "cases_excluded": [],
        "modules_removed": [],
        "stack_protector_changes": None,
    })

    session.run(["ls", "-1", str(bin_dir)], cwd=bin_dir, phase="test_discovery",
                name="test_inventory", timeout=120)

    test_argv = [
        GTEST_CATCH_EXCEPTIONS_ARG,
        "--gtest_color=no",
    ]
    for name in MANDATORY_TESTS:
        xml = xml_dir / f"{name}.xml"
        session.test(name,
                     [str(bin_dir / name)]
                     + test_argv
                     + [f"--gtest_output=xml:{xml}"],
                     cwd=bin_dir, env=env, timeout=3600)

    # Independent consumer outside the source tree, linked only against install.
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
    log = session.run([str(consumer / "build" / "vision_consumer"), str(consumer / "out")],
                      cwd=consumer, phase="consumer", name="consumer_run", timeout=300,
                      env={"LD_LIBRARY_PATH": str(install_dir / "lib")})
    text = log.read_text(errors="replace")
    if "OK red_pixels=" not in text:
        raise RuntimeError("consumer functional verification failed:\n" + text[-2000:])

    session.finish(features={
        "modules": TARGET_MODULES,
        "official_tests": MANDATORY_TESTS,
        "install_prefix": str(install_dir),
        "consumer": "vision_consumer",
        "test_data_path": str(test_data) if test_data else None,
        "test_options": [GTEST_CATCH_EXCEPTIONS_ARG],
        "diagnostic_binaries": [c["name"] for c in copied],
    })


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="solution/main.py", description="OpenCV 4.11.0 CPU core SDK source builder")
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

    run_build(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
