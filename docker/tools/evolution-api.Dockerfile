# Chromium для Puppeteer/QR-потоков поверх официального образа Evolution API.
FROM atendai/evolution-api:latest

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
    fi

ENV PUPPETEER_EXECUTABLE_PATH=/usr/local/bin/puppeteer-chromium
