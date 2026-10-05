RealBazel7.6 binary contains genuine bundledembedded_tools, but your --nofetch prevents itsLOCAL bazel_tools repository initialization:@@bazel_tools//tools/build_defs/repo missing, fetch disabled. Container physically network=none; realpinned repo cache/external inputsgiven. Permit actualLOCAL repository initialization, remove--nofetch ifneeded, allowing binary's genuine bundledtools. Do not generate placeholdermodules/headers/repo markers or prebuilt targets. Preserve fullenvoy-static+originalheader_map_impl_test+realrouteHTTPconsumer, all source/toolchain/test expectations. Real external missingdeps should be reported for genuine preparation. Return fullfiles.

Actual failure:
Traceback (most recent call last):
  File "/workspace/solution/main.py", line 247, in <module>
    sys.exit(main())
             ^^^^^^
  File "/workspace/solution/main.py", line 241, in main
    return command_run(args)
           ^^^^^^^^^^^^^^^^^
  File "/workspace/solution/main.py", line 160, in command_run
    session.run([bazel] + startup_options() + ['build'] + build_options() +
  File "/opt/controller/buildkit.py", line 122, in run
    raise RuntimeError(f'{phase} command failed ({process.returncode}): {argv}\n{tail}')
RuntimeError: build command failed (1): ['/opt/bazel/7.6.0/bazel', '--output_base=/workspace/cache/bazel_output', 'build', '--repository_cache=/workspace/cache/bazel_repository', '--config=clang', '--jobs=4', '--local_ram_resources=24000', '--nofetch', '-c', 'opt', '//source/exe:envoy-static']
Extracting Bazel installation...
Starting local Bazel server and connecting to it...
WARNING: ignoring JAVA_TOOL_OPTIONS in environment.
[35mWARNING: [0mOption 'local_ram_resources' is deprecated: --local_ram_resources is deprecated, please use --local_resources=memory= instead.
[32mComputing main repo mapping:[0m 
[31m[1mERROR: [0mError computing the main repository mapping: no such package '@@bazel_tools//tools/build_defs/repo': to fix, run
	bazel fetch //...
External repository @@bazel_tools not found and fetching repositories is disabled.
[0m
