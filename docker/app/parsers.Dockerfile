FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY pyproject.toml README.md /app/
COPY src /app/src

RUN pip install --no-cache-dir -e .

# Браузеры Playwright в образ не ставим (тяжёлый слой); парсеры в контейнере — заглушка.

CMD ["sleep", "infinity"]
