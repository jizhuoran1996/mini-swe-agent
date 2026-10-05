Actual native build and BOTH check-llvm-unit and check-clang passed, and fresh C/C++ consumers printed42. Final ELF check is wrong: readelf output uses human-readable Machine: Advanced Micro Devices X86-64, not EM_X86_64 literal. Validate ELF e_machine=62 by struct.unpack or accept the documented GNU readelf rendering, retain ELF64/endian/X86 architecture verification and every upstream test. Do not modify target scope, expected output or disable cases. Previous ELF log:
ELF Header:
  Magic:   7f 45 4c 46 02 01 01 00 00 00 00 00 00 00 00 00
  Class:                             ELF64
  Data:                              2's complement, little endian
  Version:                           1 (current)
  OS/ABI:                            UNIX - System V
  ABI Version:                       0
  Type:                              DYN (Shared object file)
  Machine:                           Advanced Micro Devices X86-64
  Version:                           0x1
  Entry point address:               0x1050
  Start of program headers:          64 (bytes into file)
  Start of section headers:          13992 (bytes into file)
  Flags:                             0x0
  Size of this header:               64 (bytes)
  Size of program headers:           56 (bytes)
  Number of program headers:         13
  Size of section headers:           64 (bytes)
  Number of section headers:         30
  Section header string table index: 29
