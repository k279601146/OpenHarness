FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    bc curl git gzip less net-tools poppler-utils psmisc socat tar unzip wget zip sudo ca-certificates gnupg ripgrep xz-utils iputils-ping && \
    curl -fsSL https://nodejs.org/dist/v22.13.0/node-v22.13.0-linux-x64.tar.xz | tar -xJ --strip-components=1 -C /usr/local && \
    corepack enable && \
    rm -rf /var/lib/apt/lists/*  # 只在这里清理一次

RUN useradd -m -s /bin/bash ohuser && \
    echo "ohuser ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

USER ohuser