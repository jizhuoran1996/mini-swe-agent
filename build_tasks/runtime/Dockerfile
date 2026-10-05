FROM ubuntu:24.04
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gfortran clang lld llvm-dev cmake ninja-build meson pkg-config \
    autoconf automake libtool bison flex gettext texinfo swig patch diffutils file \
    git curl wget ca-certificates xz-utils zip unzip locales perl libperl-dev tcl expect dejagnu \
    python3 python3-dev python3-pip python3-venv python3-packaging python3-distutils-extra \
    ruby ruby-dev rake nodejs npm golang-go cargo rustc openjdk-21-jdk-headless maven ant \
    libssl-dev zlib1g-dev libbz2-dev liblzma-dev liblz4-dev libzstd-dev libpcre2-dev \
    libnghttp2-dev libssh2-1-dev libkrb5-dev libsqlite3-dev libreadline-dev libffi-dev \
    libncurses-dev libgdbm-dev libgdbm-compat-dev libexpat1-dev uuid-dev libdb-dev \
    libxml2-dev libxslt1-dev libpng-dev libjpeg-dev libtiff-dev libgif-dev libwebp-dev \
    libopenjp2-7-dev libfreetype-dev libfontconfig-dev libharfbuzz-dev libfribidi-dev \
    libpango1.0-dev libcairo2-dev libglib2.0-dev libgirepository1.0-dev \
    libsdl2-dev libx11-dev libxcb1-dev libegl1-mesa-dev libgl1-mesa-dev libgles2-mesa-dev \
    libdrm-dev libwayland-dev libxkbcommon-dev libasound2-dev libpulse-dev \
    libogg-dev libvorbis-dev libopus-dev libmp3lame-dev libvpx-dev libtheora-dev \
    libx264-dev libx265-dev libopenexr-dev libopenimageio-dev libboost-all-dev \
    libproj-dev libgeos-dev libnetcdf-dev libhdf5-dev libopenblas-dev liblapacke-dev \
    libeigen3-dev libgtest-dev libgmock-dev libsnappy-dev libunwind-dev libnuma-dev \
    libedit-dev libicu-dev libcurl4-openssl-dev libcap-dev libaio-dev liburing-dev \
    libio-socket-ssl-perl libsocket6-perl libwww-perl ffmpeg ghostscript fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/build-tools && /opt/build-tools/bin/pip install \
    build==1.2.2.post1 wheel==0.45.1 setuptools==80.9.0 meson==1.8.3 meson-python==0.18.0 \
    ninja==1.11.1.4 cython==3.0.12 pythran==0.18.0 pybind11==2.13.6 \
    numpy==2.2.6 scipy==1.15.3 pytest==8.3.5 pytest-xdist pytest-cov hypothesis==6.135.3 \
    expecttest sympy networkx jinja2 typing_extensions fsspec requests packaging pyyaml \
    protobuf==5.29.5 absl-py ml-dtypes psutil opt_einsum patchelf scons mako \
    && mkdir /opt/wheelhouse && /opt/build-tools/bin/pip freeze > /opt/python-packages.txt \
    && /opt/build-tools/bin/pip download -r /opt/python-packages.txt -d /opt/wheelhouse \
    && rm -rf /root/.cache/pip
RUN dpkg-query -W > /opt/system-packages.txt \
    && groupadd --gid 1009 sbench && useradd --uid 1009 --gid 1009 --no-create-home --home-dir /tmp/sbench-home sbench
ENV PATH=/opt/build-tools/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LANG=C.UTF-8 LC_ALL=C.UTF-8 \
    OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4 \
    PIP_NO_INDEX=1 PIP_FIND_LINKS=/opt/wheelhouse PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CMAKE_BUILD_PARALLEL_LEVEL=4 CTEST_PARALLEL_LEVEL=2 DO_NOT_TRACK=1
WORKDIR /workspace
