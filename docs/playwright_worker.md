# Playwright-worker — архитектура и runbook

Документ описывает сервис **`playwright-worker`** в контуре PropRadar: зачем он нужен, как правильно поднимать профили Docker и как диагностировать проблемы **без правок кода** (скрипты в `/tmp` внутри контейнера).

## Оглавление

- [Назначение](#назначение)
- [Диагностические эндпоинты](#диагностические-эндпоинты)
- [Контракт `POST /enrich` и связь с CLI](#контракт-post-enrich-и-связь-с-cli)
- [Переменные окружения (enrich)](#переменные-окружения-enrich)
- [Изображения карточки и PDF](#изображения-карточки-и-pdf)
- [Архитектура контейнера](#архитектура-контейнера)
- [Профили Compose](#профили-compose-почему---profile-infra---profile-enricher-а-не-только---profile-app)
- [Runbook: деплой и smoke](#runbook-деплой-и-smoke)
- [Диагностический инструментарий](#диагностический-инструментарий-скрипты-в-tmp)
- [См. также](#см-также)

## Назначение

- **HTTP API** (FastAPI, порт контейнера **8001**): фоновое обогащение **myhome** через Playwright (**`phone`**, **`pdf`**) и HTTP-детали (**`detail`**), автологин, health.
- **Контракт с n8n:** `POST …/enrich` — успех **только HTTP 202**; готовность батча **`phase=phone`** — по **`GET /status`** (`idle`), см. `docs/n8n_myhome_workflow.md`. Тело **202** не несёт счётчиков enrich.
- **`phase=phone`:** `enrich_batch` drain волнами (cap **500**); JWT — `_AccessTokenProvider` (lock, proactive **90** с, 401-retry); `relogin_fn` → `myhome_login.py` subprocess из `main.py`.

## Диагностические эндпоинты

Реализация: **`src/worker/main.py`** (версия API **0.3.0**). Базовый URL в Docker: `http://playwright-worker:8001`.

| Метод | Путь | Назначение |
|-------|------|------------|
| `GET` | `/health` | Процесс жив (`{"status":"ok"}`) |
| `GET` | `/proxy/check` | Туннель через `PLAYWRIGHT_PROXY_*` (ipify); без proxy → `{"ok":true,"skipped":true}`; ошибка → **503** `{"ok":false,"reason":"…"}` |
| `GET` | `/session/check` | JWT в `MYHOME_SESSION_PATH`: `ok`, `exists`, `remaining_seconds`, `expires_at` |
| `GET` | `/status` | `_job_lock`: `idle` / `running`, `job`, `elapsed_seconds` |
| `POST` | `/session/reset` | Удалить файл сессии (без login) |
| `GET` | `/queue` | `pending` — COUNT лидов без телефона (`phone_retries < 3`) |
| `GET` | `/metrics` | In-memory счётчики `phase=phone` (сброс при рестарте) |

**n8n (v4):** перед `POST /enrich` `phase=phone` — `GET /proxy/check`; при `ok !== true` enrich **не** вызывается.

Примеры (на хосте с пробросом **8001**):

```bash
curl -sS http://127.0.0.1:8001/proxy/check
curl -sS http://127.0.0.1:8001/session/check
curl -sS http://127.0.0.1:8001/status
curl -sS http://127.0.0.1:8001/queue
curl -sS http://127.0.0.1:8001/metrics
```

## Контракт `POST /enrich` и связь с CLI

| `phase` | Что выполняется | Очередь в БД (кратко) |
|---------|----------------|------------------------|
| `detail` | `GET` Statements API → обновление полей лида | `source=myhome`, нет адреса или нет `price_gel` |
| `phone` | HTTP: **2captcha** → **`POST …/phone/show`** (**`MyHomePhoneHttpEnricher`**, 5 потоков) | `phone` пустой, **`phone_retries < 3`**; **`TWOCAPTCHA_API_KEY`**, **`MYHOME_SESSION_PATH`** |
| `phone_playwright` | Playwright fallback: карточка → клик → **`phone/show`** | та же очередь, **`claim_pending_phone_enrichment`** (SKIP LOCKED); **не параллелить** с активным `phase=phone` |
| `pdf` | Playwright: открытие карточки → **`page.pdf()`** | `pdf_url` пустой при заполненном адресе; каталог **`MYHOME_PDF_OUTPUT_DIR`** |

Реализация: **`src/worker/main.py`**. Лимиты размера батча и URL API те же, что у **`Settings`** в пакетном скрипте **`scripts/run_myhome_enricher.py`**: CLI последовательно гоняет **все три фазы** в одном процессе и печатает **один JSON** в stdout (`detail_enriched`, `detail_failed`, `detail_errors`, `phone_*`, `pdf_*`). Воркер обрабатывает **одну** фазу за вызов в фоне; итог по лидам смотрите в БД или в логе строки **`enrich done {…}`**.

## Переменные окружения (enrich)

Задаются в **корневом** `.env` (см. `docs/DEPLOY_SERVER.md`). Минимум для работы очередей:

| Переменная | Где нужна | Назначение |
|------------|-----------|------------|
| `DATABASE_URL` | `api`, `playwright-worker`, CLI на хосте | Подключение к **leads-db** |
| `MYHOME_API_BASE_URL` | `api`, воркер (`detail`) | Базовый URL Statements API |
| `MYHOME_SESSION_PATH` | воркер, CLI (`phone`, `phone_playwright`) | Путь к JSON storage state (cookie **AccessToken**) |
| `TWOCAPTCHA_API_KEY` | воркер (`phone`) | Ключ 2captcha (секрет, только `.env`) |
| `MYHOME_RECAPTCHA_SITE_KEY` | воркер (`phone`) | Site key reCAPTCHA v3 myhome.ge |
| `MYHOME_PHONE_HTTP_WORKERS` | воркер (`phone`) | Параллельные потоки (1–10, default **5**) |
| `MYHOME_PHONE_HTTP_ENABLED` | воркер (`phone`) | **`false`** — откат без деплоя кода |
| `PLAYWRIGHT_PROXY_*` | HTTP phone + Playwright + **`myhome_login.py`** | Прокси для исходящих запросов (`playwright_launch_kwargs_from_settings`) |
| `MYHOME_PDF_OUTPUT_DIR` | воркер, CLI (`pdf`) | Каталог файлов PDF |
| `MYHOME_PDF_PUBLIC_BASE_URL` | воркер, CLI (`pdf`, опц.) | Префикс публичного URL в поле `pdf_url` |

**Примечание (PDF):** в **`MyHomePdfEnricher`** при передаче **`headless=True`** Chromium для печати всё равно поднимается в **видимом** режиме (см. лог воркера и код **`src/parsers/adapters/myhome/pdf.py`**): это осознанный обход ограничений движка печати.

## Изображения карточки и PDF

API myhome и CDN отдают **несколько вариантов превью** для одного и того же **image id** (например с водяным знаком/логотипом и без). Текущий PDF-обогатитель **не выбирает** вариант на уровне API: он печатает **страницу листинга** в браузере. Если для выгрузки нужен конкретный URL изображения — операторски сверяйте параметры превью у CDN / в **`myhome_statement_json`**; автоматический выбор «нужного» варианта для PDF — **backlog**.

## Архитектура контейнера

| Компонент | Описание |
|-----------|----------|
| Образ | `docker/app/playwright-worker.Dockerfile` (базовый образ Playwright for Python). |
| Процесс | `uvicorn` на **:8001**, при необходимости Xvfb для headful/headless Chromium (см. entrypoint в репозитории). |
| Код | Монтируется/копируется в образ согласно Dockerfile; `PYTHONPATH` указывает на `src`. |
| БД | `DATABASE_URL` — PostgreSQL **`leads-db`** в сети **`propradar`** (тот же хост, что и у API). |
| Сессии Playwright | Том **`adapter_playwright_sessions`** → **`/data/adapter_sessions`**; путь к JSON сессии myhome задаётся **`MYHOME_SESSION_PATH`** (по умолчанию см. `docker/app/docker-compose.yml`). |

## Профили Compose: почему **`--profile infra --profile enricher`**, а не только **`--profile app`**

- Сервис **`leads-db`** объявлен во фрагменте **`docker/infra/docker-compose.yml`** с профилем **`infra`**. Без **`--profile infra`** контейнер БД **не поднимается**.
- **`playwright-worker`** объявлен во фрагменте **`docker/app/docker-compose.yml`** с профилями **`enricher`** и **`workers`**. Для сценария обогащения через n8n обычно достаточно **`enricher`**.
- У **`playwright-worker`** в compose указано **`depends_on: leads-db`** с условием **`service_healthy`**. Если **`leads-db`** не в проекте (не включён **`infra`**), разрешение зависимостей и старт воркера будут некорректны.

**Итог:** для воркера с БД из репозитория почти всегда нужно:

```bash
docker compose --profile infra --profile enricher up -d
```

(из **корня** репозитория, где лежит `compose.yaml`; сеть **`propradar`** должна существовать: `docker network create propradar`.)

**Зачем не ограничиваться `--profile app`:** профиль **`app`** поднимает, в частности, **`api`**, который также зависит от **`leads-db`**. Если поднять только **`app`** без **`infra`**, сервис **`leads-db`** не стартует — в корневом merge это проявляется как проблема зависимостей (см. известный баг в `docs/PropRadar_STATUS.md`).

## Runbook: деплой и smoke

1. **`git pull`** в каталоге репозитория на сервере.
2. Убедиться, что в **корневом** `.env` заданы **`MYHOME_EMAIL`**, **`MYHOME_PASSWORD`**, при необходимости **`MYHOME_SESSION_PATH`**, **`DATABASE_URL`** (см. `docs/DEPLOY_SERVER.md`).
3. Пересборка образа воркера (при изменении Dockerfile или зависимостей):

   ```bash
   docker compose --profile infra --profile enricher build playwright-worker
   ```

4. Запуск / обновление:

   ```bash
   docker compose --profile infra --profile enricher up -d playwright-worker
   ```

5. **Smoke:**
   - `curl -fsS http://127.0.0.1:8001/health` с хоста (если порт **8001** проброшен) или из контейнера в той же сети: `curl -fsS http://playwright-worker:8001/health` → ожидается **HTTP 200**.
   - При необходимости — `POST /login` или полный цикл n8n с **`phase=phone`** и проверкой **202**.

## Диагностический инструментарий (скрипты в `/tmp`)

Ниже — **типовые имена** утилит, которые оператор держит на хосте (например в **`/tmp/check_*.py`**) и при необходимости копирует в контейнер. В репозитории они **не обязаны** присутствовать; это шаблон процесса отладки.

| Скрипт | Назначение |
|--------|------------|
| **`check_form.py`** | Дамп всех **`input`** на странице (тип, name, id, видимость). |
| **`check_selector.py`** | Проверка одного CSS/XPath селектора (count, visible). |
| **`check_candidates.py`** | Перебор кандидатов из списка вроде **`EMAIL_SELECTORS`** (какой первый видимый). |
| **`check_network.py`** | Лог сетевых ответов при сабмите формы (фильтр по URL/статусу, **без** вывода телефонов/JWT в общий лог). |
| **`check_auth_response.py`** | Зафиксировать тело/статус ответа **`accounts.tnet.ge/.../user/auth`** (осторожно с секретами — не сохранять в открытые файлы). |
| **`check_redirect.py`** | Мониторинг **`page.url`** после сабмита (цепочка **auth.tnet.ge** → **auth.myauto.ge** → **myhome.ge**). |

### Копирование и запуск в контейнере

```bash
# имя контейнера подставьте из `docker ps` (часто propradar-playwright-worker-1 или см. compose)
docker cp /tmp/check_form.py <container>:/tmp/check_form.py
docker exec <container> python3 /tmp/check_form.py
```

Для скриптов, которым нужен Playwright внутри контейнера, используйте то же окружение (**`PYTHONPATH`**, переменные **`MYHOME_*`**) что и у воркера.

## См. также

- `docs/myhome_login.md` — автологин и сессия myhome.
- `docs/phone_extraction.md` — телефон и ограничения HTTP.
- `docs/DEPLOY_SERVER.md` — секреты и серверный деплой.
- `docs/INGRESS_ARCHITECTURE.md` — поток n8n → worker → БД.
