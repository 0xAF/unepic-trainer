FROM python:3.12-bookworm@sha256:5560e9ab8709f459489e5b8aa696eda8a07ef821e14bb122be62d91234bfa98b
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc gdb curl ca-certificates file desktop-file-utils squashfs-tools \
    libegl1 libgl1 libopengl0 libxkbcommon0 libxkbcommon-x11-0 \
    libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
    libxcb-render-util0 libxcb-xinerama0 libxcb-xkb1 libxcb-shape0 libdbus-1-3 libgtk-3-0 \
    fonts-dejavu-core xvfb xauth \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-build.txt /tmp/requirements-build.txt
RUN pip install --no-cache-dir -r /tmp/requirements-build.txt
WORKDIR /src
