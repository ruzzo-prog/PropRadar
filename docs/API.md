# PropRadar HTTP API

Сервис FastAPI (`uvicorn api.main:app`) оркестрирует CLI в `scripts/` для интеграции с **n8n** без `Execute Command`.

## Запуск

Из корня репозитория (с зависимостями из `pyproject.toml`):

```bash
set PYTHONPATH=src
uvicorn api.main:app --host 0.0.0.0 --port 9000
```

На Linux/macOS:

```bash
PYTHONPATH=src uvicorn api.main:app --host 0.0.0.0 --port 9000
```

**Примечание:** Если порт **9000** занят другими сервисами (Docker, другие проекты), укажите другой свободный порт в `--port` и согласуйте его с базовым URL клиентов (например `PROPRADAR_API_URL` в n8n).

Переменные окружения: см. `config/settings` и раздел ниже.

## OpenAPI

Интерактивная схема и «Try it out»:

- **Swagger UI:** `http://localhost:9000/docs`
- **OpenAPI JSON:** `http://localhost:9000/openapi.json`

Сохранить схему в файл (для архивации):

```bash
curl -s http://localhost:9000/openapi.json -o openapi-propradar.json
```

## Аутентификация

Все маршруты под префиксом **`/api/myhome`** требуют заголовок:

```http
X-API-Key: <значение PROPRADAR_API_KEY>
```

| `APP_ENV` | `PROPRADAR_API_KEY` | Поведение |
|-----------|---------------------|-----------|
| `development` / `dev` / `local` | не задан | доступ **без** заголовка (локальная отладка) |
| `development` / `dev` / `local` | задан | заголовок **опционален**; если передан — должен совпадать с ключом |
| любое иное (production и т.д.) | не задан или пустой | **403** на все запросы к `/api/myhome/*` |
| любое иное | задан | без заголовка или при неверном ключе → **403** |

Маршрут **`GET /health`** без ключа.

## Переменные окружения (минимум)

| Переменная | Назначение |
|------------|------------|
| `DATABASE_URL` | PostgreSQL leads-db (как у CLI). |
| `APP_ENV` | `development` vs production-подобный режим для политики API-ключа. |
| `PROPRADAR_API_KEY` | Секрет для заголовка `X-API-Key` в production. |
| `PROPRADAR_REPO_ROOT` | Корень репозитория с каталогом `scripts/` (в Docker: `/srv`, см. compose). |
| `MYHOME_CLI_TIMEOUT_SECONDS` | Таймаут subprocess (по умолчанию 3600 с). |

Остальные переменные myhome — как в `Settings` (`MYHOME_API_BASE_URL`, сессия и т.д.).

## Эндпоинты myhome

Базовый путь: **`/api/myhome`**. Примеры для `http://localhost:9000` и ключа `secret` (подставьте свой).

### `GET /api/myhome/fetch-ids`

Параметры query:

| Параметр | По умолчанию | Описание |
|----------|---------------|----------|
| `since_days` | `7` | Окно публикации (дни), если `full=false`. |
| `full` | `false` | Полный список ID (`--full`), без `since_days`. |
| `max_pages` | `500` | Лимит страниц API. |

Пример:

```bash
curl -sS -H "X-API-Key: secret" "http://localhost:9000/api/myhome/fetch-ids?since_days=7"
```

Ответ: JSON-массив строк/чисел ID.

### `POST /api/myhome/ingest`

Тело JSON:

```json
{"ids": ["123", "456"]}
```

Пустой `ids` или только пустые строки → **`200`** и `{"parsed":0,"new":0,"errors":[]}` без вызова CLI.

Пример:

```bash
curl -sS -X POST -H "X-API-Key: secret" -H "Content-Type: application/json" \
  -d "{\"ids\":[\"1\"]}" http://localhost:9000/api/myhome/ingest
```

Ответ: объект с полями `parsed`, `new`, `errors` (как stdout `run_myhome_parser.py`).

### `POST /api/myhome/sync-status`

Вызов `sync_myhome_status.py discover --fetch-api`.

Query: `max_pages` (по умолчанию `500`).

```bash
curl -sS -X POST -H "X-API-Key: secret" \
  "http://localhost:9000/api/myhome/sync-status?max_pages=500"
```

Ответ: `{"disappeared":[...], "counts":{...}}`.

### `POST /api/myhome/mark-rejected`

Тело JSON:

```json
{"ids": ["1", "2"], "reason": "disappeared_from_api"}
```

Поле `reason` по умолчанию `disappeared_from_api`.

```bash
curl -sS -X POST -H "X-API-Key: secret" -H "Content-Type: application/json" \
  -d "{\"ids\":[\"1\"],\"reason\":\"disappeared_from_api\"}" \
  http://localhost:9000/api/myhome/mark-rejected
```

Ответ: `{"updated": N, "reason": "..."}`.

## Коды ошибок

| Код | Когда |
|-----|--------|
| 403 | Нет/неверный API-ключ (см. политику выше). |
| 400 | Некорректное тело (например пустые `ids` в `mark-rejected`). |
| 502 | CLI завершился с ненулевым кодом или невалидный JSON в stdout. |
| 503 | Файл скрипта не найден относительно `PROPRADAR_REPO_ROOT`. |
| 504 | Превышен `MYHOME_CLI_TIMEOUT_SECONDS`. |

## Docker

Сервис **`api`** в `docker/app/docker-compose.yml`: монтирование репозитория в `/srv`, `PYTHONPATH=/srv/src`, `depends_on: leads-db` при **совместном** запуске с `docker/infra/docker-compose.yml`. Подробности — комментарии в compose-файле.

## Идемпотентность

Повторный `mark-rejected` с теми же ID зависит от поведения репозитория и состояния лидов; при проектировании n8n учитывайте возможные повторные execution.
