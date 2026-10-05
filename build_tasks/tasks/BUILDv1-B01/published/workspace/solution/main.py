#!/usr/bin/env python3
"""Core-profile source build driver for LLVM/Clang.

Implements the frozen BUILDv1-B01 core scope: X86 target, clang enabled, lld
intentionally absent, official checks check-llvm-unit and check-clang.
"""
import argparse
import json
import re
import shutil
import struct
import sys
from pathlib import Path

import buildkit
from buildkit import Session, digest


REQUIRED_TOOLS = ["cmake", "ninja", "gcc", "g++", "python3", "ld", "tar"]


# ELF constants used for architecture verification (System V gABI).
ELFMAG = b"\x7fELF"
ELFCLASS64 = 2
ELFDATA2LSB = 1
EM_X86_64 = 62


def doctor(input_dir):
    inp = Path(input_dir).resolve()
    missing = []
    manifest = inp / "manifest.json"
    if not manifest.is_file():
        missing.append(f"source manifest not found: {manifest}")
    else:
        try:
            data = json.loads(manifest.read_text())
            source = data.get("source", {})
            archive = inp / source.get("filename", "source.tar.gz")
            if not archive.is_file():
                missing.append(f"source archive not found: {archive}")
            elif digest(archive) != source.get("sha256"):
                missing.append(f"source archive sha256 mismatch: {archive}")
        except Exception as exc:
            missing.append(f"source manifest unreadable: {manifest}: {exc}")
    for tool in REQUIRED_TOOLS:
        if shutil.which(tool) is None:
            missing.append(f"required tool missing from PATH: {tool}")
    if missing:
        print("doctor: NOT READY")
        for item in missing:
            print(f"MISSING {item}")
        return 78
    print("doctor: READY")
    return 0


def parse_lit_counts(log_path):
    text = Path(log_path).read_text(errors="replace")
    counts = {}
    for label, pattern in [
        ("expected_passes", r"Expected Passes\s*:\s*(\d+)"),
        ("expected_failures", r"Expected Failures\s*:\s*(\d+)"),
        ("unsupported", r"Unsupported Tests\s*:\s*(\d+)"),
        ("unexpected_passes", r"Unexpected Passes\s*:\s*(\d+)"),
        ("unexpected_failures", r"Unexpected Failures\s*:\s*(\d+)"),
        ("passed_with_retry", r"Passed With Retry\s*:\s*(\d+)"),
    ]:
        found = re.search(pattern, text)
        if found:
            counts[label] = int(found.group(1))
    return counts


def elf_identity(path):
    """Return structural ELF identity by parsing raw header bytes."""
    with Path(path).open("rb") as stream:
        header = stream.read(64)
    if len(header) < 64 or header[:4] != ELFMAG:
        raise RuntimeError(f"not an ELF file: {path}")
    ei_class = header[4]
    ei_data = header[5]
    # e_machine is a 16-bit field at offset 18, endianness per EI_DATA.
    endian = "<" if ei_data == ELFDATA2LSB else ">"
    e_machine = struct.unpack(endian + "H", header[18:20])[0]
    return {
        "ei_class": ei_class,
        "ei_class_name": "ELF64" if ei_class == ELFCLASS64 else f"class_{ei_class}",
        "ei_data": ei_data,
        "ei_data_name": "little-endian" if ei_data == ELFDATA2LSB else f"data_{ei_data}",
        "e_machine": e_machine,
        "e_machine_name": "EM_X86_64" if e_machine == EM_X86_64 else f"machine_{e_machine}",
    }


def run(args):
    session = Session(args.input, args.output, args.jobs)
    src = session.prepare()
    llvm_src = src / "llvm"
    if not (llvm_src / "CMakeLists.txt").is_file():
        raise RuntimeError(f"LLVM source CMakeLists.txt not found under {llvm_src}")

    jobs = session.jobs
    test_jobs = min(2, jobs)
    install = session.install
    build = session.build
    env = {"CC": "gcc", "CXX": "g++"}
    configure_args = [
        "cmake", "-S", str(llvm_src), "-B", str(build), "-G", "Ninja",
        "-DCMAKE_BUILD_TYPE=Release",
        f"-DCMAKE_INSTALL_PREFIX={install}",
        "-DLLVM_ENABLE_PROJECTS=clang",
        "-DLLVM_TARGETS_TO_BUILD=X86",
        "-DLLVM_INCLUDE_TESTS=ON",
        "-DLLVM_BUILD_TESTS=ON",
        "-DCLANG_INCLUDE_TESTS=ON",
        "-DCLANG_BUILD_TESTS=ON",
        "-DLLVM_ENABLE_ASSERTIONS=OFF",
        "-DLLVM_INCLUDE_EXAMPLES=OFF",
        "-DLLVM_INCLUDE_BENCHMARKS=OFF",
        "-DLLVM_PARALLEL_LINK_JOBS=1",
        "-DCMAKE_C_COMPILER=gcc",
        "-DCMAKE_CXX_COMPILER=g++",
    ]
    session.run(configure_args, cwd=session.src, phase="configure", name="cmake_configure", env=env, timeout=1800)

    cache = build / "CMakeCache.txt"
    if cache.is_file():
        shutil.copy2(cache, session.output / "CMakeCache.txt")
    session.write("source_dependency_manifest.json", {
        "task_id": session.manifest.get("task_id"),
        "profile": "core: X86 + clang; lld disabled",
        "source": session.manifest.get("source"),
        "configure_args": configure_args,
        "build_jobs": jobs,
        "test_jobs": test_jobs,
        "parallel_link_jobs": 1,
    })

    session.run(["cmake", "--build", str(build), "--parallel", str(jobs)],
                cwd=session.src, phase="build", name="cmake_build", timeout=10800)

    lit = build / "bin" / "llvm-lit"
    discovery = []
    if lit.is_file():
        for label, target in [("check-llvm-unit", build / "unittests"),
                              ("check-clang", build / "tools" / "clang" / "test")]:
            if target.exists():
                log = session.run([sys.executable, str(lit), "--show-tests", str(target)],
                                  cwd=build, phase="discovery", name=f"inventory_{label}",
                                  check=False, timeout=1800)
                discovery.append({"selector": label, "target": str(target),
                                  "log": str(log.relative_to(session.output))})
    session.write("test_inventory.json", discovery)

    test_env = {"LLVM_LIT_ARGS": "-sv"}
    for selector in ["check-llvm-unit", "check-clang"]:
        log = session.test(selector, ["ninja", "-C", str(build), "-j", str(test_jobs), selector],
                           cwd=build, env=test_env, timeout=7200)
        counts = parse_lit_counts(log)
        if counts:
            session.write(f"lit_counts_{selector}.json", counts)

    session.run(["cmake", "--install", str(build)], cwd=session.src,
                phase="install", name="cmake_install", timeout=3600)
    session.run(["tar", "-czf", str(session.output / "toolchain.tar.gz"),
                 "-C", str(session.output), "install"],
                cwd=session.output, phase="package", name="package_toolchain", timeout=3600)

    bin_clang = install / "bin" / "clang"
    bin_clangxx = install / "bin" / "clang++"
    llvm_ar = install / "bin" / "llvm-ar"
    llvm_readelf = install / "bin" / "llvm-readelf"
    for path in [bin_clang, bin_clangxx, llvm_ar, llvm_readelf]:
        if not path.exists():
            raise RuntimeError(f"installed target artifact missing: {path}")

    consumer = session.consumer
    cpp_src = consumer / "cpp_src"
    c_src = consumer / "c_src"
    cpp_build = consumer / "cpp_build"
    c_build = consumer / "c_build"
    for path in [cpp_src, c_src, cpp_build, c_build]:
        path.mkdir(parents=True, exist_ok=True)
    (cpp_src / "lib.hpp").write_text("#pragma once\nint add(int a, int b);\nint fail_if(bool c);\n")
    (cpp_src / "lib.cpp").write_text(
        '#include "lib.hpp"\n#include <stdexcept>\n'
        'int add(int a, int b) { return a + b; }\n'
        'int fail_if(bool c) { if (c) throw std::runtime_error("expected failure"); return 42; }\n')
    (cpp_src / "main.cpp").write_text(
        '#include "lib.hpp"\n#include <iostream>\n#include <stdexcept>\n#include <string>\n'
        'int main() {\n'
        '  int x = add(20, 22);\n'
        '  if (x != 42) return 1;\n'
        '  try { fail_if(true); return 2; }\n'
        '  catch (const std::runtime_error& e) { if (std::string(e.what()) != "expected failure") return 3; }\n'
        '  if (fail_if(false) != 42) return 4;\n'
        '  std::cout << "cpp-ok " << x << "\\n";\n'
        '  return 0;\n} \n')
    (c_src / "c_hello.c").write_text(
        '#include <stdio.h>\nint main(void) { printf("c-ok 42\\n"); return 0; }\n')

    session.run([str(bin_clangxx), "--version"], cwd=consumer, phase="consumer",
                name="consumer_clangxx_version")
    session.run([str(bin_clang), "--version"], cwd=consumer, phase="consumer",
                name="consumer_clang_version")
    session.run([str(bin_clangxx), "-print-prog-name=ld"], cwd=consumer, phase="consumer",
                name="consumer_print_ld")

    session.run([str(bin_clangxx), "-std=c++17", "-fPIC", "-c", str(cpp_src / "lib.cpp"),
                 "-o", str(cpp_build / "lib.o")], cwd=consumer, phase="consumer",
                name="consumer_cpp_lib_compile")
    session.run([str(llvm_ar), "rcs", str(cpp_build / "libconsumer.a"), str(cpp_build / "lib.o")],
                cwd=consumer, phase="consumer", name="consumer_cpp_archive")
    session.run([str(bin_clangxx), "-std=c++17", "-c", str(cpp_src / "main.cpp"),
                 "-o", str(cpp_build / "main.o")], cwd=consumer, phase="consumer",
                name="consumer_cpp_main_compile")
    session.run([str(bin_clangxx), str(cpp_build / "main.o"), "-L", str(cpp_build),
                 "-lconsumer", "-o", str(cpp_build / "consumer_cpp")],
                cwd=consumer, phase="consumer", name="consumer_cpp_link")
    cpp_log = session.run([str(cpp_build / "consumer_cpp")], cwd=consumer, phase="consumer",
                          name="consumer_cpp_run")
    cpp_text = cpp_log.read_text(errors="replace")
    if "cpp-ok 42" not in cpp_text:
        raise RuntimeError("C++ consumer produced unexpected output")

    session.run([str(bin_clang), "-std=c11", "-c", str(c_src / "c_hello.c"),
                 "-o", str(c_build / "c_hello.o")], cwd=consumer, phase="consumer",
                name="consumer_c_compile")
    session.run([str(bin_clang), str(c_build / "c_hello.o"), "-o", str(c_build / "c_hello")],
                cwd=consumer, phase="consumer", name="consumer_c_link")
    c_log = session.run([str(c_build / "c_hello")], cwd=consumer, phase="consumer",
                        name="consumer_c_run")
    c_text = c_log.read_text(errors="replace")
    if "c-ok 42" not in c_text:
        raise RuntimeError("C consumer produced unexpected output")

    # Primary architecture verification: parse raw ELF header bytes (e_machine=62).
    c_binary = c_build / "c_hello"
    cpp_binary = cpp_build / "consumer_cpp"
    c_elf = elf_identity(c_binary)
    cpp_elf = elf_identity(cpp_binary)
    for label, ident in (("c_hello", c_elf), ("consumer_cpp", cpp_elf)):
        if ident["ei_class"] != ELFCLASS64:
            raise RuntimeError(f"{label} is not ELF64: {ident}")
        if ident["ei_data"] != ELFDATA2LSB:
            raise RuntimeError(f"{label} is not little-endian: {ident}")
        if ident["e_machine"] != EM_X86_64:
            raise RuntimeError(f"{label} e_machine is not EM_X86_64(62): {ident}")

    # Secondary evidence: preserve llvm-readelf's human-readable rendering and
    # accept the documented GNU/LLVM spelling for the X86-64 machine field.
    elf_log = session.run([str(llvm_readelf), "-h", str(c_binary)],
                          cwd=consumer, phase="consumer", name="consumer_elf_header")
    elf_text = elf_log.read_text(errors="replace")
    if not re.search(r"Advanced Micro Devices X86-64|EM_X86_64", elf_text):
        raise RuntimeError("llvm-readelf did not report X86-64 machine")
    if "ELF64" not in elf_text or "little endian" not in elf_text:
        raise RuntimeError("llvm-readelf did not confirm ELF64 little-endian")

    resolved = bin_clangxx.resolve()
    if str(install.resolve()) not in str(resolved):
        raise RuntimeError(f"installed clang++ resolves outside install tree: {resolved}")
    session.write("consumer_evidence.json", {
        "installed_clang": str(bin_clang),
        "installed_clangxx_realpath": str(resolved),
        "c_program_output": c_text.strip(),
        "cpp_program_output": cpp_text.strip(),
        "c_elf_identity": c_elf,
        "cpp_elf_identity": cpp_elf,
        "readelf_machine_render": "Advanced Micro Devices X86-64",
        "readelf_log": str(elf_log.relative_to(session.output)),
    })
    session.finish(features={"scope": "X86+clang", "lld": False,
                             "tests": ["check-llvm-unit", "check-clang"],
                             "consumer": "c-static+cpp-static-exceptions",
                             "elf_check": "parse_e_machine_62 + readelf_render"})


def main(argv=None):
    parser = argparse.ArgumentParser(prog="llvm-core-build")
    sub = parser.add_subparsers(dest="command")
    doctor_p = sub.add_parser("doctor")
    doctor_p.add_argument("--input", required=True)
    run_p = sub.add_parser("run")
    run_p.add_argument("--input", required=True)
    run_p.add_argument("--output", required=True)
    run_p.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return doctor(args.input)
    if args.command == "run":
        run(args)
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
