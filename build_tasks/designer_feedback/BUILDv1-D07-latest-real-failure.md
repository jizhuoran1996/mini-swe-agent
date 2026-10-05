Real upstream PreLoad.cmake rejects your LDFLAGS=-fuse-ld=lld and CMAKE_C_FLAGS/CMAKE_CXX_FLAGS=-g0 before configure. Remove these custom CFLAGS/CXXFLAGS/LDFLAGS and injected compiler flags; unset inherited variables through normal environment cleanup. Use realClang19/LLD19 through upstream supported linker/toolchain variables only. Never patch/bypass PreLoad.cmake or fake flags/headers. Full132 genuine gitlinks and originalssl.h.in are ready. Preserve fullclickhouse+unit_tests_dbms aggregate, officialColumnObject.* tests and localSQL/JSON consumers; no smaller target or altered expected tests. An explicitly supported upstream debug-info setting may be used/recorded. Return full files.

Actual failure:
Traceback (most recent call last):
  File "/workspace/solution/main.py", line 451, in <module>
    sys.exit(main())
             ^^^^^^
  File "/workspace/solution/main.py", line 445, in main
    return run_build(str(input_dir), str(output_dir), args.jobs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/workspace/solution/main.py", line 355, in run_build
    session.run(
  File "/opt/controller/buildkit.py", line 122, in run
    raise RuntimeError(f'{phase} command failed ({process.returncode}): {argv}\n{tail}')
RuntimeError: configure command failed (1): ['/usr/bin/cmake', '-S', '/workspace/src', '-B', '/workspace/build', '-G', 'Ninja', '-DCMAKE_MAKE_PROGRAM=/opt/build-tools/bin/ninja', '-DCMAKE_BUILD_TYPE=Release', '-DENABLE_TESTS=ON', '-DENABLE_RUST=OFF', '-DCMAKE_C_COMPILER=/usr/bin/clang-19', '-DCMAKE_CXX_COMPILER=/usr/bin/clang++-19', '-DCMAKE_C_FLAGS=-g0', '-DCMAKE_CXX_FLAGS=-g0']
CFLAGS: 
CXXFLAGS: 
LDFLAGS: -fuse-ld=lld
CMAKE_C_FLAGS: -g0
CMAKE_CXX_FLAGS: -g0
CMAKE_EXE_LINKER_FLAGS: 
CMAKE_SHARED_LINKER_FLAGS: 
CMAKE_MODULE_LINKER_FLAGS: 
CMAKE_C_FLAGS_INIT: 
CMAKE_CXX_FLAGS_INIT: 
CMAKE_EXE_LINKER_FLAGS_INIT: 
CMAKE_MODULE_LINKER_FLAGS_INIT: 
CMake Error at PreLoad.cmake:41 (message):
  

          Some of the variables like CFLAGS, CXXFLAGS, LDFLAGS are not empty.
          It is not possible to build ClickHouse with custom flags.
          These variables can be set up by previous invocation of some other build tools.
          You should cleanup these variables and start over again.

  

          Run the `env` command to check the details.
          You will also need to remove the contents of the build directory.

  

          Note: if you don't like this behavior, you can manually edit the cmake files, but please don't complain to developers.


-- Configuring incomplete, errors occurred!

