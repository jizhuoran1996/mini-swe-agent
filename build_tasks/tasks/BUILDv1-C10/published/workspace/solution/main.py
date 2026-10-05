#!/usr/bin/env python3
"""BUILDv1-C10 (core profile) - build, install, test and consume a
non-rendering VTK Common/Filters/IO SDK from the frozen source release.

Every artifact verified by the consumer step is produced by the CMake
configure/build/install commands recorded through :mod:`buildkit`; no
prebuilt VTK binary or wheel is ever substituted.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from buildkit import Session, digest

# ---------------------------------------------------------------------------
# Frozen profile constants (core scope: Common / Filters / IO, no rendering).
# ---------------------------------------------------------------------------
CORE_TESTS = (
    "TestArrayAPI",
    "TestSmartPointer",
    "TestNew",
    "TestCleanPolyData",
    "TestThreshold",
    "TestXMLWriteRead",
)

ENABLE_MODULES = (
    "CommonCore",
    "CommonDataModel",
    "CommonExecutionModel",
    "FiltersCore",
    "FiltersGeneral",
    "FiltersSources",
    "IOLegacy",
    "IOXML",
    # VTK 9.4.2: the `ENABLE_TESTS WANT` scan reaches VTK::RenderingLabel via
    # the test dependency closure, and that module hard-requires
    # VTK::octree (CMake/vtkModule.cmake:2856 known-issue check).
    # Enabling the leaf module explicitly is the documented fix and keeps
    # the official test closure intact.
    "octree",
)

# Non-anchored suffix so both `TestFoo` and `<prefix>TestFoo` ctest names match.
TEST_REGEX = "(" + "|".join(CORE_TESTS) + ")$"

REQUIRED_TOOLS = ("cmake", "ninja", "c++")

CONSUMER_CMAKE = r'''cmake_minimum_required(VERSION 3.12)
project(vtk_core_consumer LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(VTK REQUIRED COMPONENTS
  CommonCore
  CommonDataModel
  CommonExecutionModel
  FiltersCore
  FiltersSources
  IOLegacy
  IOXML)

add_executable(vtkconsumer main.cxx)

if (COMMAND vtk_module_autoinit)
  vtk_module_autoinit(TARGETS vtkconsumer MODULES ${VTK_LIBRARIES})
endif ()

target_link_libraries(vtkconsumer PRIVATE ${VTK_LIBRARIES})
'''

CONSUMER_MAIN = r'''#include <vtkAutoInit.h>
#include <vtkCleanPolyData.h>
#include <vtkDataArray.h>
#include <vtkDataObject.h>
#include <vtkElevationFilter.h>
#include <vtkNew.h>
#include <vtkPointData.h>
#include <vtkPolyData.h>
#include <vtkSphereSource.h>
#include <vtkThreshold.h>
#include <vtkUnstructuredGrid.h>
#include <vtkXMLPolyDataReader.h>
#include <vtkXMLPolyDataWriter.h>

#include <iostream>
#include <string>

static int fail(const std::string& message)
{
  std::cerr << "CONSUMER_FAIL: " << message << std::endl;
  return 1;
}

int main(int argc, char** argv)
{
  const std::string outFile = (argc > 1) ? argv[1] : "vtk_consumer_out.vtp";

  vtkNew<vtkSphereSource> sphere;
  sphere->SetThetaResolution(24);
  sphere->SetPhiResolution(24);
  sphere->Update();

  vtkNew<vtkElevationFilter> elevation;
  elevation->SetInputConnection(sphere->GetOutputPort());
  elevation->SetLowPoint(0.0, 0.0, -1.0);
  elevation->SetHighPoint(0.0, 0.0, 1.0);
  elevation->Update();

  vtkPolyData* surface = elevation->GetOutput();
  if (surface == nullptr || surface->GetNumberOfPoints() < 100)
  {
    return fail("sphere/elevation produced too few points");
  }
  const vtkIdType sourcePoints = surface->GetNumberOfPoints();

  vtkNew<vtkCleanPolyData> clean;
  clean->SetInputData(surface);
  clean->Update();
  const vtkIdType cleanPoints = clean->GetOutput()->GetNumberOfPoints();
  const vtkIdType cleanCells = clean->GetOutput()->GetNumberOfCells();
  if (cleanPoints <= 0 || cleanCells <= 0)
  {
    return fail("clean poly data produced empty output");
  }

  vtkNew<vtkXMLPolyDataWriter> writer;
  writer->SetFileName(outFile.c_str());
  writer->SetInputData(clean->GetOutput());
  if (!writer->Write())
  {
    return fail("XML poly data write failed");
  }

  vtkNew<vtkXMLPolyDataReader> reader;
  reader->SetFileName(outFile.c_str());
  reader->Update();
  vtkPolyData* reloaded = reader->GetOutput();
  if (reloaded == nullptr || reloaded->GetNumberOfPoints() != cleanPoints)
  {
    return fail("XML round trip point count mismatch");
  }
  vtkDataArray* reloadedElevation = reloaded->GetPointData()->GetArray("Elevation");
  if (reloadedElevation == nullptr ||
      reloadedElevation->GetNumberOfTuples() != cleanPoints)
  {
    return fail("XML round trip lost the Elevation array");
  }

  vtkNew<vtkThreshold> threshold;
  threshold->SetInputData(reloaded);
  threshold->SetInputArrayToProcess(
    0, 0, 0, vtkDataObject::FIELD_ASSOCIATION_POINTS, "Elevation");
  threshold->SetLowerThreshold(0.5);
  threshold->SetUpperThreshold(1.0);
  threshold->SetThresholdFunction(vtkThreshold::THRESHOLD_BETWEEN);
  threshold->Update();
  vtkUnstructuredGrid* selected = threshold->GetOutput();
  const vtkIdType selectedCells = selected ? selected->GetNumberOfCells() : 0;
  if (selectedCells <= 0 || selectedCells >= cleanCells)
  {
    return fail("threshold did not select a proper subset of cells");
  }

  std::cout << "CONSUMER_OK source_points=" << sourcePoints
            << " clean_points=" << cleanPoints
            << " clean_cells=" << cleanCells
            << " threshold_cells=" << selectedCells << std::endl;
  return 0;
}
'''


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------
def _inspect_input(input_dir: Path):
    missing = []
    manifest_path = input_dir / "manifest.json"
    if not manifest_path.is_file():
        missing.append("manifest file: %s" % manifest_path)
        return missing, None
    try:
        manifest = json.loads(manifest_path.read_text())
    except Exception as exc:  # noqa: BLE001
        missing.append("manifest unreadable: %s" % exc)
        return missing, None

    source = manifest.get("source") or {}
    filename = source.get("filename")
    if not filename:
        missing.append("manifest source.filename")
        return missing, manifest

    archive = input_dir / filename
    if not archive.is_file():
        missing.append("source archive: %s" % archive)
        return missing, manifest

    expected = source.get("sha256")
    if expected:
        actual = digest(archive)
        if actual != expected:
            missing.append(
                "source archive sha256 mismatch (have %s, want %s)" % (actual, expected))
    return missing, manifest


def cmd_doctor(args):
    missing, manifest = _inspect_input(Path(args.input))
    for tool in REQUIRED_TOOLS:
        if shutil.which(tool) is None:
            missing.append("required build tool not on PATH: %s" % tool)
    report = {
        "task_id": (manifest or {}).get("task_id", "BUILDv1-C10"),
        "profile": (manifest or {}).get("profile", "core"),
        "input_dir": str(Path(args.input).resolve()),
        "missing": missing,
        "ready": not missing,
    }
    print(json.dumps(report, indent=2))
    return 0 if not missing else 78


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------
def _find_vtk_config(install: Path) -> Path:
    for name in ("vtk-config.cmake", "VTKConfig.cmake"):
        hits = sorted(install.rglob(name))
        if hits:
            return hits[0]
    raise RuntimeError("no VTK CMake package config found in the install tree")


def _library_path(install: Path) -> str:
    dirs = sorted({str(p.parent) for p in install.rglob("*.so*")})
    return os.pathsep.join(dirs)


def _configure_defines(session: Session):
    defines = [
        "-G", "Ninja",
        "-DCMAKE_INSTALL_PREFIX=%s" % session.install,
        "-DCMAKE_BUILD_TYPE=Release",
        "-DBUILD_SHARED_LIBS=ON",
        "-DVTK_INSTALL_SDK=ON",
        "-DVTK_BUILD_TESTING=WANT",
        "-DVTK_USE_MPI=OFF",
        "-DVTK_WRAP_PYTHON=OFF",
        "-DVTK_WRAP_JAVA=OFF",
        "-DVTK_ENABLE_WRAPPING=OFF",
        "-DVTK_ENABLE_REMOTE_MODULES=OFF",
        "-DVTK_USE_X=OFF",
        "-DVTK_GROUP_ENABLE_Rendering=DONT_WANT",
        "-DVTK_GROUP_ENABLE_Qt=NO",
        "-DVTK_GROUP_ENABLE_Web=NO",
        "-DVTK_GROUP_ENABLE_Tk=NO",
    ]
    defines += ["-DVTK_MODULE_ENABLE_VTK_%s=YES" % m for m in ENABLE_MODULES]
    return defines


def _build_consumer(session: Session):
    consumer = session.consumer
    (consumer / "CMakeLists.txt").write_text(CONSUMER_CMAKE)
    (consumer / "main.cxx").write_text(CONSUMER_MAIN)
    consumer_build = consumer / "build"

    config = _find_vtk_config(session.install)
    session.run(
        ["cmake", "-S", str(consumer), "-B", str(consumer_build), "-G", "Ninja",
         "-DCMAKE_BUILD_TYPE=Release", "-DVTK_DIR=%s" % config.parent],
        cwd=str(consumer), phase="consumer_configure", timeout=900)
    session.run(
        ["cmake", "--build", str(consumer_build), "--parallel", str(session.jobs)],
        cwd=str(consumer), phase="consumer_build", timeout=1800)

    executable = consumer_build / "vtkconsumer"
    if not executable.is_file():
        raise RuntimeError("independent consumer executable was not produced")

    env = {"LD_LIBRARY_PATH": _library_path(session.install)}
    session.test(
        "vtk_core_consumer",
        [str(executable), str(consumer / "vtk_consumer_out.vtp")],
        cwd=str(consumer), env=env, timeout=600)


def _run(session: Session):
    source = session.prepare()
    build = session.build

    session.run(
        ["cmake", "-S", str(source), "-B", str(build), *_configure_defines(session)],
        cwd=str(build), phase="configure", timeout=1800)
    session.run(
        ["cmake", "--build", str(build), "--parallel", str(session.jobs)],
        cwd=str(build), phase="build", timeout=7800)
    session.run(
        ["cmake", "--install", str(build)],
        cwd=str(build), phase="install", timeout=1800)

    # Preserve the exact official test inventory before executing anything.
    session.run(
        ["ctest", "--test-dir", str(build), "-N"],
        cwd=str(build), phase="test_discovery", timeout=900)
    session.test(
        "vtk_core_cxx_tests",
        ["ctest", "--test-dir", str(build), "--output-on-failure", "-R", TEST_REGEX],
        cwd=str(build), timeout=3600)

    _build_consumer(session)

    session.finish(features={
        "profile": "core",
        "scope": "Common/Filters/IO non-rendering SDK",
        "modules": list(ENABLE_MODULES),
        "render_backend": "none (reference profile owns RenderingOpenGL2/EGL)",
        "python_wrapping": False,
        "official_tests": list(CORE_TESTS),
        "consumer": "find_package(VTK)+vtk_module_autoinit, out-of-tree",
    })


def cmd_run(args):
    session = Session(args.input, args.output, args.jobs)
    try:
        _run(session)
    except Exception as exc:  # noqa: BLE001
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1
    return 0


# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="BUILDv1-C10 core profile VTK SDK builder")
    sub = parser.add_subparsers(dest="command")

    doctor = sub.add_parser("doctor", help="check source/tool prerequisites")
    doctor.add_argument("--input", required=True)

    run = sub.add_parser("run", help="configure/build/install/test/consume")
    run.add_argument("--input", required=True)
    run.add_argument("--output", required=True)
    run.add_argument("--jobs", type=int, default=4)

    args = parser.parse_args(argv)
    if args.command == "doctor":
        return cmd_doctor(args)
    if args.command == "run":
        return cmd_run(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
