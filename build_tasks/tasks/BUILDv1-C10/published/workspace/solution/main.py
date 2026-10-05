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
import re
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
)

# Anchored suffix so both `TestFoo` and `<prefix>TestFoo` ctest names match.
TEST_REGEX = "(" + "|".join(CORE_TESTS) + ")$"

REQUIRED_TOOLS = ("cmake", "ninja", "c++")

# VTK 9.4.2 `vtk_module_scan` prints these actionable messages when a module
# selected through the `VTK_BUILD_TESTING=WANT` dependency closure lists a
# REQUIRED dependency that the current module-selection did not enable.  VTK's
# own text tells the user to explicitly enable the missing module, which is
# exactly what `_configure_with_dependency_fix` does below: it re-runs the
# *official* `cmake` configure with an added `-DVTK_MODULE_ENABLE_VTK_<dep>=YES`
# for each reported dependency until configure succeeds.  Nothing in the VTK
# source tree is patched or mocked; only cache entries are added, exactly as a
# human would do interactively.
DEP_MISSING_RE = re.compile(
    r'The\s+(VTK::[A-Za-z0-9_]+)\s+dependency is missing for\s+(VTK::[A-Za-z0-9_]+)')

CONSUMER_CMAKE = r'''cmake_minimum_required(VERSION 3.12)
project(vtk_core_consumer LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(VTK REQUIRED COMPONENTS
  CommonCore
  CommonDataModel
  CommonExecutionModel
  FiltersCore
  FiltersGeneral
  FiltersSources
  IOLegacy
  IOXML)

add_executable(vtkconsumer main.cxx)

if (COMMAND vtk_module_autoinit)
  vtk_module_autoinit(TARGETS vtkconsumer MODULES ${VTK_LIBRARIES})
endif ()

target_link_libraries(vtkconsumer PRIVATE ${VTK_LIBRARIES})
'''

CONSUMER_MAIN = r'''#include <vtkCleanPolyData.h>
#include <vtkDataArray.h>
#include <vtkDataObject.h>
#include <vtkDataSet.h>
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

  // vtkElevationFilter::GetOutput() is declared on vtkDataSetAlgorithm and
  // therefore returns vtkDataSet*.  The documented contract of the
  // elevation filter is that it passes its input through unchanged (a
  // vtkPolyData here), so use the official vtkPolyData::SafeDownCast helper
  // and reject any surprise instead of a permissive reinterpretation.
  vtkDataSet* elevationOutput = elevation->GetOutput();
  if (elevationOutput == nullptr)
  {
    return fail("elevation filter produced a null output");
  }
  vtkPolyData* surface = vtkPolyData::SafeDownCast(elevationOutput);
  if (surface == nullptr)
  {
    return fail("vtkElevationFilter did not preserve the vtkPolyData type");
  }
  if (surface->GetNumberOfPoints() < 100)
  {
    return fail("sphere/elevation produced too few points");
  }
  const vtkIdType sourcePoints = surface->GetNumberOfPoints();

  vtkNew<vtkCleanPolyData> clean;
  clean->SetInputData(surface);
  clean->Update();
  vtkPolyData* cleaned = clean->GetOutput();
  if (cleaned == nullptr)
  {
    return fail("clean poly data produced a null output");
  }
  const vtkIdType cleanPoints = cleaned->GetNumberOfPoints();
  const vtkIdType cleanCells = cleaned->GetNumberOfCells();
  if (cleanPoints <= 0 || cleanCells <= 0)
  {
    return fail("clean poly data produced empty output");
  }

  vtkNew<vtkXMLPolyDataWriter> writer;
  writer->SetFileName(outFile.c_str());
  writer->SetInputData(cleaned);
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
  double reloadedRange[2] = {0.0, 0.0};
  reloadedElevation->GetRange(reloadedRange);
  if (!(reloadedRange[1] > reloadedRange[0]))
  {
    return fail("XML round trip lost the Elevation range");
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
    # ------------------------------------------------------------------
    # Offline data policy: use VTK's *official* supported option
    # `VTK_DATA_EXCLUDE_FROM_ALL` (see CMake/vtkExternalData.cmake and the
    # top-level CMakeLists.txt).  It marks the `VTKData` aggregate download
    # target as EXCLUDE_FROM_ALL so the default `ninja all` build never tries
    # to fetch any ExternalData object.  The fetch rules, `ExternalData_Add_Test`
    # registrations and every sha512 baseline hash remain registered untouched;
    # any test whose fixture is truly missing therefore fails honestly instead
    # of being silently downloaded or skipped.  `VTK_FORBID_DOWNLOADS` is not
    # required for the same reason and is left at its upstream default so the
    # module system behaves normally everywhere else.
    #
    # Module scoping: force the exact core SDK module set explicitly (`YES`)
    # and set every irrelevant group to `DONT_WANT`, including StandAlone, so
    # that only the requested modules and the test-dependency closure of
    # `VTK_BUILD_TESTING=WANT` get scheduled.  Missing REQUIRED dependencies
    # inside that closure (for example `VTK::exodusII` for `VTK::IOExodus`)
    # are reported by CMake with an actionable message; `_configure_with_
    # dependency_fix` re-runs `cmake` with the exact extra
    # `-DVTK_MODULE_ENABLE_VTK_<module>=YES` flags VTK's own diagnostics ask
    # for, so no upstream CMake command is patched or disabled.
    # ------------------------------------------------------------------
    defines = [
        "-G", "Ninja",
        "-DCMAKE_INSTALL_PREFIX=%s" % session.install,
        "-DCMAKE_BUILD_TYPE=Release",
        "-DBUILD_SHARED_LIBS=ON",
        "-DVTK_INSTALL_SDK=ON",
        "-DVTK_BUILD_TESTING=WANT",
        # Official supported data-download exclusion; see comment above.
        "-DVTK_DATA_EXCLUDE_FROM_ALL=ON",
        "-DVTK_DATA_EXCLUDE_FROM_ALL_NO_WARNING=ON",
        "-DVTK_USE_MPI=OFF",
        "-DVTK_WRAP_PYTHON=OFF",
        "-DVTK_WRAP_JAVA=OFF",
        "-DVTK_ENABLE_WRAPPING=OFF",
        "-DVTK_ENABLE_REMOTE_MODULES=OFF",
        "-DVTK_USE_X=OFF",
        "-DVTK_GROUP_ENABLE_StandAlone=DONT_WANT",
        "-DVTK_GROUP_ENABLE_Rendering=DONT_WANT",
        "-DVTK_GROUP_ENABLE_Qt=DONT_WANT",
        "-DVTK_GROUP_ENABLE_Web=DONT_WANT",
        "-DVTK_GROUP_ENABLE_Tk=DONT_WANT",
        "-DVTK_GROUP_ENABLE_MPI=DONT_WANT",
        "-DVTK_GROUP_ENABLE_Charts=DONT_WANT",
        "-DVTK_GROUP_ENABLE_Views=DONT_WANT",
        "-DVTK_GROUP_ENABLE_Geovis=DONT_WANT",
        "-DVTK_GROUP_ENABLE_Infovis=DONT_WANT",
        "-DVTK_GROUP_ENABLE_Imaging=DONT_WANT",
        "-DVTK_GROUP_ENABLE_Domains=DONT_WANT",
        "-DVTK_GROUP_ENABLE_Interaction=DONT_WANT",
    ]
    defines += ["-DVTK_MODULE_ENABLE_VTK_%s=YES" % m for m in ENABLE_MODULES]
    return defines


def _configure_with_dependency_fix(session: Session):
    """Run the *official* `cmake` configure, iteratively enabling any module
    whose absence VTK's own `vtk_module_scan` reports as an error.  CMake is
    the only tool invoked here; the VTK source tree is never patched."""
    defines = _configure_defines(session)
    last_log = None
    for attempt in range(1, 11):
        log = session.run(
            ["cmake", "-S", str(session.src), "-B", str(session.build), *defines],
            cwd=str(session.build), phase="configure",
            name="configure_attempt_%02d" % attempt, timeout=1800, check=False)
        last_log = log
        if session.commands[-1]['exit_code'] == 0:
            return defines
        text = log.read_text(errors="replace")
        matches = DEP_MISSING_RE.findall(text)
        if not matches:
            tail = text[-5000:]
            raise RuntimeError("configure failed without an actionable VTK "
                               "dependency message:\n" + tail)
        added = False
        for dep, _module in matches:
            name = dep.split("::", 1)[1]
            flag = "-DVTK_MODULE_ENABLE_VTK_%s=YES" % name
            if flag not in defines:
                defines.append(flag)
                added = True
        if not added:
            raise RuntimeError("configure still failing after enabling every "
                               "reported missing module:\n" + text[-5000:])
    raise RuntimeError("configure exceeded retry budget (see %s)" % last_log)


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
    session.prepare()

    build = session.build
    final_defines = _configure_with_dependency_fix(session)

    # Record the final, canonical configure invocation so the successful cache
    # state is reproducible from a single command.
    session.run(
        ["cmake", "-S", str(session.src), "-B", str(build), *final_defines],
        cwd=str(build), phase="configure_final", timeout=1800)

    session.run(
        ["cmake", "--build", str(build), "--parallel", str(session.jobs)],
        cwd=str(build), phase="build", timeout=9600)
    session.run(
        ["cmake", "--install", str(build)],
        cwd=str(build), phase="install", timeout=1800)

    # Preserve the exact official test inventory before executing anything.
    session.run(
        ["ctest", "--test-dir", str(build), "-N"],
        cwd=str(build), phase="test_discovery", timeout=900)
    session.test(
        "vtk_core_cxx_tests",
        ["ctest", "--test-dir", str(build), "--output-on-failure",
         "-R", TEST_REGEX],
        cwd=str(build), timeout=3600)

    _build_consumer(session)

    session.finish(features={
        "profile": "core",
        "scope": "Common/Filters/IO non-rendering SDK",
        "modules": list(ENABLE_MODULES),
        "render_backend": "none (reference profile owns RenderingOpenGL2/EGL)",
        "python_wrapping": False,
        "official_tests": list(CORE_TESTS),
        "data_download_policy": "VTK_DATA_EXCLUDE_FROM_ALL=ON (official upstream option)",
        "dependency_closure": "CMake `vtk_module_scan` actionable errors drive "
                              "additional -DVTK_MODULE_ENABLE_VTK_<module>=YES cache entries",
        "consumer": "find_package(VTK)+vtk_module_autoinit, out-of-tree, "
                    "vtkPolyData::SafeDownCast on the elevation filter output",
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
