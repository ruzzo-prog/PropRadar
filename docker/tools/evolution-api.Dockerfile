# Chromium для Puppeteer/QR-потоков поверх официального образа Evolution API.
FROM atendai/evolution-api:latest

# Восстанавливаем runtime-пользователя базового образа после root-операций.
# При необходимости можно переопределить на build: --build-arg BASE_RUNTIME_USER=<user>
ARG BASE_RUNTIME_USER=node

USER root

RUN set -eu; \
    apk add --no-cache \
        chromium \
        nss \
        freetype \
        harfbuzz \
        ca-certificates \
        ttf-freefont \
    ; \
    if [ -x /usr/bin/chromium-browser ]; then \
      ln -sf /usr/bin/chromium-browser /usr/local/bin/puppeteer-chromium; \
    elif [ -x /usr/bin/chromium ]; then \
      ln -sf /usr/bin/chromium /usr/local/bin/puppeteer-chromium; \
    else \
      echo 'No chromium executable after apk add' >&2; \
      ls -la /usr/bin/chromium* >&2 || true; \
      exit 1; \
    fi; \
    if id -u "${BASE_RUNTIME_USER}" >/dev/null 2>&1; then \
      chown -R "${BASE_RUNTIME_USER}:${BASE_RUNTIME_USER}" /evolution; \
    else \
      echo "Base image has no user '${BASE_RUNTIME_USER}'; cannot switch USER" >&2; \
      exit 1; \
    fi

USER ${BASE_RUNTIME_USER}

ENV PUPPETEER_EXECUTABLE_PATH=/usr/local/bin/puppeteer-chromium
