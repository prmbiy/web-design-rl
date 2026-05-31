FROM node:22-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    ffmpeg \
    git \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN npm install -g playwright \
    && mkdir -p /ms-playwright \
    && playwright install --with-deps chromium \
    && chmod -R a+rx /ms-playwright

RUN pip3 install --break-system-packages --no-cache-dir playwright

RUN useradd -m -s /bin/bash agent

RUN mkdir -p /app/site /task/screenshots /logs/agent /logs/verifier \
    && chown -R agent:agent /app /logs/agent

COPY --chown=root:root task_screenshots /task/screenshots
RUN chmod -R a+rX /task/screenshots

COPY --chown=root:root task_screenrecordings /task/screenrecordings
RUN chmod -R a+rX /task/screenrecordings

COPY --chown=root:root checker /opt/checker
RUN chmod -R go-rwx /opt/checker && chmod 700 /opt/checker

USER agent
WORKDIR /app
