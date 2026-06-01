FROM node:22-alpine

RUN apk add --no-cache \
    bash \
    ca-certificates \
    chromium \
    chromium-chromedriver \
    curl \
    ffmpeg \
    font-freefont \
    git \
    nss \
    freetype \
    harfbuzz \
    ttf-freefont

ENV PLAYWRIGHT_BROWSERS_PATH=/dev/null
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium-browser

RUN npm install -g playwright @anthropic-ai/claude-code \
    && chmod -R a+rw /usr/local/lib/node_modules \
    && chmod -R a+rw /usr/local/bin

RUN adduser -D -s /bin/bash agent

RUN mkdir -p /app/site /task/screenshots /logs/agent /logs/verifier \
    && chown -R agent:agent /app /logs/agent

COPY --chown=root:root task_screenshots /task/screenshots
RUN chmod -R a+rX /task/screenshots

COPY --chown=root:root checker /opt/checker
RUN cd /opt/checker && npm install playwright
RUN chmod -R go-rwx /opt/checker && chmod 700 /opt/checker

USER agent
WORKDIR /app
