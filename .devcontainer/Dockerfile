# [🎨 GUI Code Production Chat] ComfyVN Dev Container with full Qt stack
FROM mcr.microsoft.com/devcontainers/python:3.11

# Install libraries needed for PySide6 and Qt GUI rendering
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libxkbcommon-x11-0 \
    libxcb-cursor0 \
    libnss3 \
    xvfb \
    mesa-utils \
    libegl1 \
    libgbm1 \
    libgles2 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
