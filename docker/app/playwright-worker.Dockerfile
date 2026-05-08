# Playwright-worker: Chromium + Xvfb для headful Playwright (myhome phone/PDF/login).
# Образ приложения parsers.Dockerfile не меняется.

FROM mcr.microsoft.com/playwright/python:v1.59.0-noble

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl xvfb \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY scripts /app/scripts
COPY docker/app/playwright-worker-entrypoint.sh /usr/local/bin/playwright-worker-entrypoint.sh

RUN chmod +x /usr/local/bin/playwright-worker-entrypoint.sh \
    && pip install --no-cache-dir -e .

EXPOSE 8001

HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8001/health || exit 1

ENTRYPOINT ["/usr/local/bin/playwright-worker-entrypoint.sh"]
