The independent EGL consumer source is embedded in `solution/main.py` as the
raw string `EGL_C`. At run time it is written to
`/workspace/consumer/egl_offscreen/consumer.c`, compiled with `gcc` against the
newly installed EGL and GLESv2 libraries under the install prefix, and executed
with `LD_LIBRARY_PATH` pointing only at that install prefix. There is no
reference in the consumer build or run environment to any system Mesa library.
