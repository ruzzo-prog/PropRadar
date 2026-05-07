#!/bin/sh
set -eu

# xvfb-run не подходит для PID1/долгоживущего uvicorn в этом образе (uvicorn не стартует).
# Паттерн: Xvfb в фоне → DISPLAY → exec uvicorn (основной процесс контейнера).
Xvfb :99 -screen 0 1280x1024x24 -nolisten tcp &
XVFB_PID=$!
export DISPLAY=:99

# Короткая выдержка, чтобы сокет X был готов до Playwright/Chromium.
i=0
while [ "$i" -lt 50 ]; do
  if kill -0 "$XVFB_PID" 2>/dev/null && [ -S /tmp/.X11-unix/X99 ]; then
    break
  fi
  i=$((i + 1))
  sleep 0.1
done
if ! kill -0 "$XVFB_PID" 2>/dev/null; then
  echo "playwright-worker-entrypoint: Xvfb exited" >&2
  exit 1
fi

exec uvicorn worker.main:app --host 0.0.0.0 --port 8001
