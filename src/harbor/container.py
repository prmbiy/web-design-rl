def render_dockerfile(has_animations: bool) -> str:
    recordings_copy = (
        "\nCOPY --chown=root:root task_screenrecordings /task/screenrecordings\n"
        "RUN chmod -R a+rX /task/screenrecordings\n"
        if has_animations
        else ""
    )

    return f"""FROM node:22-slim

RUN apt-get update && apt-get install -y --no-install-recommends \\
    ca-certificates \\
    curl \\
    ffmpeg \\
    git \\
    python3 \\
    python3-pip \\
    python3-venv \\
    && rm -rf /var/lib/apt/lists/*

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN npm install -g playwright \\
    && mkdir -p /ms-playwright \\
    && playwright install --with-deps chromium \\
    && chmod -R a+rx /ms-playwright

RUN useradd -m -s /bin/bash agent

RUN mkdir -p /app/site /task/screenshots /logs/agent /logs/verifier \\
    && chown -R agent:agent /app /logs/agent

COPY --chown=root:root task_screenshots /task/screenshots
RUN chmod -R a+rX /task/screenshots
{recordings_copy}
COPY --chown=root:root checker /opt/checker
RUN cd /opt/checker && npm install playwright
RUN chmod -R go-rwx /opt/checker && chmod 700 /opt/checker

USER agent
WORKDIR /app
"""
