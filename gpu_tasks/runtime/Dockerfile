FROM ubuntu:24.04
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip ca-certificates libgomp1 libstdc++6 libglib2.0-0 libgl1 ffmpeg git curl && rm -rf /var/lib/apt/lists/*
RUN ln -s /usr/bin/python3 /usr/local/bin/python
RUN groupadd --gid 1009 sbench && useradd --uid 1009 --gid 1009 --no-create-home --home-dir /tmp/sbench-home --shell /usr/sbin/nologin sbench
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4 TOKENIZERS_PARALLELISM=false HF_HUB_DISABLE_TELEMETRY=1 DO_NOT_TRACK=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /workspace
