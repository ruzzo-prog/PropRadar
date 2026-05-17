# Changelog

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/).

## [Unreleased]

### Fixed

- **myhome phone HTTP — JWT mid-batch (PR1):** `_AccessTokenProvider` в `phone_http.py` — `threading.Lock`, проактивный relogin при `remaining < 90` с, на **401** один relogin + retry `phone/show` **без** `phone_retries++` при успехе; `relogin_fn` из `main.py` (`_run_myhome_login_subprocess`). Порог pre-job в воркере — по-прежнему `MYHOME_SESSION_MIN_REMAINING_SECONDS` (**40** с).

- **myhome phone HTTP — drain очереди (PR2):** `enrich_batch` — волны по `MYHOME_PHONE_HTTP_WORKERS` до `claim==0` или `processed>=limit` (cap **500**); n8n шлёт `limit=pending` (без cap 150). **n8n** `yG1JxQnR6kX0Vlgt` — Wait **480** с → poll **30** с + `GET /status` до `idle` (таймаут execution **3600** с → TG alert).

- **P1 / myhome login через proxy:** общий хелпер `playwright_launch_kwargs_from_settings` (`playwright_proxy.py`); `scripts/myhome_login.py` — `chromium.launch(**launch_kw)` с `PLAYWRIGHT_PROXY_*` (как `phone.py`); login-if-needed больше не ходит на `auth.tnet.ge` с прямого IP Hetzner.

### Added

- **playwright-worker — диагностические эндпоинты:** `GET /proxy/check`, `GET /session/check`, `GET /status`, `POST /session/reset`, `GET /queue`, `GET /metrics` (`src/worker/main.py`, v0.3.0). Proxy check — `httpx_client_kwargs_from_settings()` + ipify; метрики in-memory для `phase=phone`. **n8n** `yG1JxQnR6kX0Vlgt` — gate `GET /proxy/check` перед `POST /enrich` `phase=phone`. **Проверки:** `pytest tests/unit/test_playwright_worker_api.py`.

### Fixed

- **playwright-worker `POST /enrich` — `limit` в теле:** `EnrichRequest.limit` (опционально) пробрасывается в `_run_myhome_enrich_phase`; без поля — `settings.myhome_enrich_limit` (default **50**). n8n может задавать `MIN(pending, 150)` вместо фиксированных 50.

### Fixed

- **myhome phone claim — резерв очереди:** при `claim_pending_phone_enrichment` — `status_reason = phone_enriching`, `updated_at` (без `phone_retries`); очередь + TTL **`PHONE_ENRICH_STALE_MINUTES`**; `sweep_stale_phone_enriching` в начале `enrich_batch`; **`phone_retries += 1` только в `release_phone_enrich_after_failure`** при реальной ошибке; после успеха `status_reason = NULL` в `update_enriched_fields`. Устраняет повторный claim и ложные retries при claim/краше воркера.

### Added

- **n8n myhome v4 (`yG1JxQnR6kX0Vlgt`):** после «TG: Обогащение запущено» — **Wait 240 с** → SQL статистика телефонов по `leads` (`source=myhome`) → «TG: Обогащение завершено» (with_phone / failed / pending / total).

### Fixed

- **Metabase админ-дашборды:** таблица «Последние лиды» — этаж без дубля `13/13`, «Состояние» из `myhome_statement_json.condition` (JOIN `leads`); карта — swap `map.latitude_column`/`longitude_column`, скаляры «Всего точек» и «Средняя цена USD» на дашборде карты.

### Added

- **Metabase админ-дашборды (API):** `scripts/create_metabase_dashboards.py` + `scripts/metabase_api_common.py` — **«PropRadar — Мониторинг»** (10 плиток, `leads_client`, TZ `Asia/Tbilisi`) и **«PropRadar — Карта объектов»**; bundles `metabase/monitoring_admin_dashboard.json`, `metabase/map_objects_dashboard.json`; идемпотентное пересоздание по имени. **Smoke:** только человек (`METABASE_*`).

### Fixed

- **myhome `room_type_id` → `leads.rooms`:** `resolve_rooms()` в `statement_snapshot.py` — fallback после `room`; `statement_to_lead_updates` и `parse_list_item`; миграция **`012_backfill_rooms_from_room_type_id.sql`** для существующих лидов.

### Changed

- **playwright-worker / `phase=phone` — login-if-needed:** перед `enrich_batch` проверка JWT (`session_needs_login` в `phone_http.py`); при `remaining < MYHOME_SESSION_MIN_REMAINING_SECONDS` (default **40**, p95 login ~8 с + 30 с) — `myhome_login.py` в том же `_job_lock`; при `exit_code != 0` enrich **не** стартует (`login_failed_exit_*`). JWT payload — **base64url** с корректным padding; невалидный env → warning + default 40. n8n шлёт только **`POST /enrich`**; cron login **`MvaHceZGVlUxDIHM`** — **inactive**.

- **n8n orchestration (login / enrich split):** отдельный workflow **`PropRadar myhome session login`** (`MvaHceZGVlUxDIHM`, cron `3-59/9 * * * *` → `POST /login`) — **деактивирован**; основной **`PropRadar — myhome v4`** (`yG1JxQnR6kX0Vlgt`) — ingest → `POST /enrich` `phase=phone` **без** `/login` в том же execution (устранение silent drop при `_job_lock`).

### Fixed

- **P1 / `fetch-ids` `limit` в пагинации:** `fetch_all_list_items_sync` принимает `limit` и останавливает обход страниц; `fetch_all_external_ids_sync` пробрасывает `limit` только при `since_days is None` (n8n `limit=N` укладывается в таймаут 30 с). **Проверки:** `pytest tests/unit/test_myhome_list_ids.py tests/unit/test_myhome_http_api.py` — PASS.

### Changed

- **phone_http P1 — 5 параллельных потоков:** `enrich_batch` — до `limit` задач в `ThreadPoolExecutor`, каждая **`claim_pending_phone_enrichment(limit=1)`** → 2captcha → phone/show; лог **`phone_http_ok … thread=… latency_ms=…`**; `MYHOME_PHONE_HTTP_WORKERS` (default 5). **`_job_lock`** в worker без изменений.

### Added

- **Metabase:** карточка **«Карта лидов»** (position 11, map по **`leads.geo_lat`/`geo_lng`**); **`setup_metabase_dashboard.py`** — идемпотентный **PUT** карточки 7 и upsert карточки 11 при существующем дашборде; обновлён SQL **«Последние лиды»** (колонка **rooms**, укороченный набор полей).

### Fixed

- **P1 myhome mapping (rooms, images, JSON snapshot):** **`parse_list_item`** — **`list.room`** → **`leads.rooms`**; **`statement_snapshot.py`** — снимок **`myhome_statement_json`**: без **`large`** в **`images`** (только **`thumb`**/**`blur`**, **`is_main`** первым), удаление 15 шумных ключей, **`comment`** без HTML; только **новые** записи. **Gap:** **`room_type_id` → rooms** — вне scope. **Проверки:** **`pytest tests/unit/`** — PASS.

### Fixed

- **Очередь телефона Playwright = HTTP claim:** `phase=phone_playwright` и CLI fallback вызывают **`claim_pending_phone_enrichment`** (SKIP LOCKED), не **`list_*`** — `src/worker/main.py`, `scripts/run_myhome_enricher.py`. **`phone.py`** без изменений. n8n: **`phone_playwright`** только после батча HTTP.

- **`phone_http.py` — concurrency hardening:** per-thread **`httpx.Client`** (myhome + 2captcha), без общего клиента в **`ThreadPoolExecutor`**; безопасное закрытие при падении **`TwoCaptchaClient.__init__`**. **Проверки:** **`pytest tests/unit/test_myhome_phone_http.py`** — **PASS**.

- **P0 hotfix / `phone_http.py` — 401 retry + утечка httpx:** **`phone/show` HTTP 401** → **`PhoneShowError(..., retryable=True)`** и **`phone_retries += 1`** (JWT истёк — добивка следующим батчем после **`POST /login`**); при падении **`load_access_token`** **`finally`** закрывает оба **`httpx.Client`** (myhome + 2captcha). **Проверки:** **`pytest tests/unit/test_myhome_phone_http.py`** — **11 passed** (2026-05-15).

### Added

- **MyHome HTTP phone enricher (2captcha):** основной путь телефона — **`src/parsers/adapters/myhome/phone_http.py`** (reCAPTCHA v3 через **2captcha**, **`POST /v1/statements/phone/show`**, **~16 с/лид**, **5** потоков); **`phase=phone`** в **`playwright-worker`** → HTTP; **`phase=phone_playwright`** → прежний **`MyHomePhoneEnricher`** без правок **`phone.py`**. Миграция **`migrations/011_add_phone_retries.sql`** — **`phone_retries`**, очередь **`phone_retries < 3`**, исчерпание → **`status_reason=phone_enrich_failed`** (**`status`** остаётся **`new`**). Репозиторий: **`claim_pending_phone_enrichment`** (**`SKIP LOCKED`**), **`increment_phone_retry`**, **`mark_phone_enrich_exhausted`**. Env: **`TWOCAPTCHA_API_KEY`**, **`MYHOME_RECAPTCHA_SITE_KEY`**, **`MYHOME_PHONE_HTTP_WORKERS`**, **`MYHOME_PHONE_HTTP_ENABLED`**, **`MYHOME_PHONE_PLAYWRIGHT_FALLBACK`** (CLI). **Проверки:** **`pytest`** — **23 passed** (unit phone HTTP + enricher + worker API, 2026-05-15); **Scanner** и smoke на сервере — **человек**.

### Fixed

- **P0 hotfix / `src/parsers/adapters/myhome/phone.py` — `phone/show` HTTP 204:** API **`api-statements.tnet.ge/v1/statements/phone/show`** отвечает **204 No Content** (номер в DOM после React); фильтр **`status == 200`** в **`expect_response`** давал таймаут **30 s** + **`save_timeout_shot`** (~**81+ s/лид**). **`expect_response`** принимает **200** и **204**; при **204** — **`body.inner_text()`** + **`\+?995[\s\d]{9,14}`** → **`+995…`**; при **200** — **`parse_phone_response`**. **Вне scope:** прокси, паузы между лидами, **`save_timeout_shot`**, pkill/waitpid. **Проверки:** **`pytest tests/unit/test_myhome_enricher.py`** — **10 passed** (2026-05-15); smoke на **3 лидах** и rebuild **`playwright-worker`** — **человек**.

- **`src/parsers/adapters/myhome/phone.py` — сеть по `phone/show` и парс телефона:** ожидание ответа по URL **`phone/show`** без ограничения **`status == 200`**; выбор видимой кнопки телефона — перебор **`nth(i)`** с проверкой **`bounding_box`**, без привязки к **`.first`**; для ответа **HTTP 204** — ожидание **1000 ms**, номер берётся из **`inner_text`** выбранной видимой кнопки, извлечение по **`\+?[0-9]{9,13}`**; для ответов с телом сохранена ветка **`parse_phone_response(response)`**. **Вне scope этого фикса:** прокси, **`user_agent`**, stealth, **`storage_state`**, навигация. **Проверки:** **Scanner** — **PASS** (человек); **`pytest tests/unit/test_myhome_enricher.py tests/unit/test_playwright_worker_api.py`** — **13 passed** (2026-05-10).

### Removed

- **SnapOtter / `snapotter.usluga-market.ru` (полный откат из репо):** решение человека — AI на CPU нестабилен; не-AI инструменты (resize/compress/convert) переносятся на **Python/Pillow**. Удалены сервис **`snapotter`** и том **`snapotter_data`** из **`docker/app/docker-compose.yml`**, **`docker/reverse-proxy/nginx/conf.d/snapotter.conf`**, монты **`SNAPOTTER_TLS_*`** в **`docker/reverse-proxy/docker-compose.yml`**, **`check_one`** snapotter и упоминания **`SNAPOTTER_TLS_*`** в **`00-tls-preflight.sh`**. Документация: **`docs/TLS_LETSENCRYPT.md`**, **`docker/reverse-proxy/README.md`**, **`CHANGELOG.md`**, **`docs/PropRadar_STATUS.md`**. **На сервере (человек):** остановить и удалить контейнер и volume данных SnapOtter; убрать **`SNAPOTTER_TLS_*`** из **`.env`**; **`docker compose --profile proxy up -d --force-recreate reverse-proxy`**. Сертификат LE для **`snapotter.usluga-market.ru`** на диске **оставить**.

### Documented

- **Сессия 2026-05-10 (аудит документации / myhome enrich):** **`README.md`** — оглавление, разделение **CLI `run_myhome_enricher.py`** vs **`playwright-worker` `POST /enrich`** (`detail`/`phone`/`pdf`), точные ключи stdout JSON; **`docs/INGRESS_ARCHITECTURE.md`**, **`docs/n8n_myhome_workflow.md`**, **`docs/playwright_worker.md`** — фазы воркера, **`DATABASE_URL`** / **`MYHOME_SESSION_PATH`**, связка с n8n; **`docs/phone_extraction.md`** — stealth, статус **паузы** до мобильного прокси **GE IP**; **`docs/API.md`** — уточнение про пакетный enricher; матрица портов **`playwright-worker:8001`** в **`docs/DEPLOY_SERVER.md`**; оглавления/запуск Metabase через **`--profile tools`** в **`docs/METABASE_SETUP.md`**; оглавление-конспект в **`docs/TLS_LETSENCRYPT.md`**; порт Metabase в **`docs/AI_GOVERNANCE.md`**. **`docs/PropRadar_STATUS.md`**, **`CHANGELOG.md`** — запись о сессии.

- **Сессия 2026-05-09 (Hetzner / reverse-proxy, LE для трёх доменов):** в **`docs/DEPLOY_SERVER.md`** — раздел **«Единый процесс Let's Encrypt (n8n, Evolution, Metabase)»**: предусловия (**UFW 80/443**, одна **A** на домен), три команды **`certbot certonly --standalone`**, все **шесть** переменных **`N8N_TLS_*`**, **`EVOLUTION_TLS_*`**, **`METABASE_TLS_*`** с путями **`/etc/letsencrypt/live/<домен>/`**, пересоздание **`reverse-proxy`** (`docker compose --profile proxy up -d --force-recreate reverse-proxy`), проверка **`curl -vI https://<домен>`** + **`grep`** по **SSL/HTTP**; блок **Metabase** сведён к ссылке на единый процесс + site URL.

- **Сессия 2026-05-09 (myhome: вход, телефон, воркер):** добавлены runbook **`docs/playwright_worker.md`** (архитектура **`playwright-worker`**, профили **`infra` + enricher**, smoke, диагностические скрипты **`/tmp/check_*.py`**) и **`docs/myhome_login.md`** (переменные, volume сессии, SSO **auth.myauto.ge** + **`AccessToken`**, headless, **`networkidle`**). Обновлён **`docs/phone_extraction.md`** — раздел про **Cloudflare** и итог **Playwright-only**. Сводка исправлений за день: **`EMAIL_SELECTORS`** — **`input[name="Email"]`**; **`_run_auto_login`** — **`wait_until="networkidle"`** + **`wait_for_timeout(3000)`** перед локацией полей; **`_wait_auth_success`** — успех при **myhome.ge** или **auth.myauto.ge?…AccessToken=…**, таймаут ожидания URL **30 s**; оперативная смена пароля в **`.env`** на стороне оператора; **расследование:** HTTP-телефон с **www.myhome.ge** невозможен (**Cloudflare**); **revert:** удалены **`phone_extractor`** и тесты, канон телефона снова **только Playwright** (**`docs/AI_GOVERNANCE.md`**, **`docs/INGRESS_ARCHITECTURE.md`**).

### Fixed

- **P1 hotfix / `src/parsers/adapters/myhome/phone.py` — снова `headless=False` под Xvfb (playwright-worker):** коммит **`c4dfd4d`** (`headless=True` по умолчанию) на воркере с **Docker + Xvfb** (**`DISPLAY=:99`**, см. **`docker/app/playwright-worker-entrypoint.sh`**) привёл к усиленной антибот-защите (**Cloudflare**/капча) и **TimeoutError** на обогащении **phone**; восстановлено поведение как до **`c4dfd4d`**: дефолт **`headless=False`**, **`chromium.launch(headless=False)`** (2 строки в **`phone.py`**). **Проверки:** **`pytest tests/unit/test_myhome_enricher.py tests/unit/test_playwright_worker_api.py`** — **13 passed** (2026-05-09). **Коммит:** **`d0e03d1`**.

- **P1 / `src/parsers/adapters/myhome/phone.py` — MyHomePhoneEnricher без дисплея:** убран принудительный **`chromium.launch(headless=False)`** и лог про «игнорирование» **`headless=True`**; дефолт параметра конструктора **`headless=True`**; запуск **`headless=self._headless`**. Загрузка **`storage_state`** из **`MYHOME_SESSION_PATH`** / переданного пути — без изменений. **Проверки:** **Scanner** — **PASS** (человек); **`pytest tests/unit/test_myhome_enricher.py tests/unit/test_playwright_worker_api.py`** — **13 passed** (2026-05-09). **Коммит:** **`c4dfd4d`**. *(На воркере с Xvfb итог заменён hotfix **`d0e03d1`** — см. пункт выше.)*

- **`scripts/myhome_login.py` — `_wait_auth_success` / SSO TNET:** после успешного auth API браузер может остановиться на **`auth.myauto.ge`** с параметром **`AccessToken`** без финального редиректа на **myhome.ge** (типично в headless). Ожидание успеха расширено: **myhome.ge** (как раньше) или **auth.myauto.ge** с **`AccessToken`** в query; таймаут ожидания URL снижен до **30 s** (вместо 90 s). Значения токенов в лог не пишутся.

### Reverted

- **MyHome HTTP-first телефона:** после деплоя выявлено, что **`www.myhome.ge`** отдаёт **Cloudflare Managed Challenge** для простых HTTP-клиентов (`httpx`, `curl`; 403 на сервере/локально); рабочий путь — только **Playwright** с браузером. Откат: удалены **`src/parsers/adapters/myhome/phone_extractor.py`**, **`tests/unit/test_phone_extractor.py`**; **`src/parsers/adapters/myhome/phone.py`** снова **только Playwright**; восстановлены формулировки в **`docs/AI_GOVERNANCE.md`** (§9) и **`docs/INGRESS_ARCHITECTURE.md`**. Причина внедрения без проверки live до выкладки зафиксирована постмортем. Файл **`docs/phone_extraction.md`** при откате **не менялся**; позже в тот же день переписан в **`### Documented`** (Cloudflare, исторический **`__NEXT_DATA__`**, итог Playwright-only).

### Added

- **MyHome phone / прокси Playwright + Windows UA + детекция Cloudflare (`src/config/settings.py`, `src/parsers/adapters/myhome/phone.py`):** опциональные env **`PLAYWRIGHT_PROXY_SERVER`**, **`PLAYWRIGHT_PROXY_USER`**, **`PLAYWRIGHT_PROXY_PASS`** в **`Settings`**; при заданном сервере — **`chromium.launch(proxy=…)`**; всегда **`args`** с **`--disable-blink-features=AutomationControlled`** и фиксированный Windows Chrome **`user_agent`** в **`browser.new_context`**. Сразу после **`page.goto`**: если в заголовке есть **`Just a moment`** или в HTML — **`Turnstile`**, то **`logger.warning("cloudflare_block ext=%s", …)`**, **`save_timeout_shot`**, возврат из **`_enrich_one`** строки **`CloudflareBlock`** (без **`TimeoutError`** для этого случая). Логика **`phone/show`**, селекторы, **`TW_MS`**, **`storage_state`** не менялись. **Проверки:** **Scanner** — **PASS** (человек, 2026-05-10); **`pytest tests/unit/test_myhome_enricher.py tests/unit/test_playwright_worker_api.py`** — **13 passed** (2026-05-10). **На сервере (человек):** выставить **`PLAYWRIGHT_PROXY_*`** в **`.env`**, смоук egress IP и **myhome.ge** без капчи.

- **MyHome phone / обход Cloudflare (Playwright):** в **`pyproject.toml`** — зависимость **`playwright-stealth>=2.0.3`**; в **`src/parsers/adapters/myhome/phone.py`** после **`context.new_page()`** — **`Stealth().apply_stealth_sync(page)`** (пакет **`playwright_stealth`** 2.x) **до** первого **`goto`**; дефолт **`headless=True`**, **`chromium.launch(headless=self._headless)`**. Логика **`phone/show`**, селекторы, таймауты, **`storage_state`** — без изменений; **`playwright-worker.Dockerfile`** не менялся. **Автопроверки:** **`pytest tests/unit/test_myhome_enricher.py tests/unit/test_playwright_worker_api.py`** — **13 passed**; **`ruff`** **`phone.py`** — **PASS**. **Ручная приёмка:** **`https://www.myhome.ge/pr/24644149/`** без капчи и успешное обогащение телефона на **playwright-worker**.

- **Infra / Redis:** в **`docker/infra/docker-compose.yml`** сервис **`propradar-redis`** — образ **`redis:7.4.9-alpine`**, режим **`redis-server --appendonly yes`** (AOF), том **`propradar_redis_data`**, профиль **`infra`**; порты на хост **не публикуются** — доступ только из сети **`propradar`**; healthcheck через **`redis-cli ping`**.

- **Playwright worker (**коммит `52429d9`, feat worker**):** отдельный сервис **`src/worker/main.py`** (FastAPI **:8001**) — **`POST /enrich`** (**202**), **`POST /login`**, **`GET /health`**; Docker — **`docker/app/playwright-worker.Dockerfile`**, сервис в **`docker/app/docker-compose.yml`** с профилями **`enricher`** / **`workers`** и томом под файлы сессии Playwright. После успешного **`POST /api/myhome/ingest`** оркестратор n8n вызывает **`POST http://playwright-worker:8001/enrich`** с телом **`{"adapter":"myhome","phase":"phone"}`**; допустимый успешный ответ на стороне n8n — только **HTTP 202**, **polling** результата не выполняется. **`scripts/myhome_login.py`:** при ошибке автологина из **`MYHOME_EMAIL`** / **`MYHOME_PASSWORD`** — немедленный **`exit 1`** без паузы на ручной ввод (серверный сценарий).

- **Docker / корневой `compose.yaml`:** единая точка входа с `include` фрагментов `docker/infra`, `docker/app`, `docker/tools`, `docker/reverse-proxy`; профили **`infra`**, **`app`**, **`tools`**, **`proxy`**; project directory — корень репозитория (интерполяция `${VAR}` из корневого `.env`). Сервис **`api`**: `env_file` на **`../../.env`** (корень репо). Обновлены **`docs/DEPLOY_SERVER.md`**, **`README.md`**, примеры env.

- **Документация ingress:** заполнен **`Docs/INGRESS_ARCHITECTURE.md`** — четыре домена из канона, поток myhome.ge → PropRadar API → n8n → leads-db → WhatsApp (Evolution), схема узлов n8n, контракты `**/api/myhome/***` (сверка с кодом и `docs/API.md`), роли **`leads`** / **`leads_client`**, Docker/порты (**9000** локальный uvicorn vs **8000** compose), переменные окружения без секретов, ссылки на источники правды.
- **Деплой на сервер (VPS/Hetzner):** runbook `**docs/DEPLOY_SERVER.md**`; reverse-proxy слой в `**docker/reverse-proxy/**` (конфигурация репозитория); примеры окружения `**.env.example.local**` / `**.env.example.server**` (без секретов); в compose — `**healthcheck**` и `**depends_on**` для предсказуемого порядка старта; обновлены `**README.md**` и n8n-документация под серверный сценарий.

### Changed

- **Evolution API / Redis-кэш (`docker/tools`):** безопасный дефолт **`CACHE_REDIS_ENABLED=false`** (режим только **tools** не требует Redis); при **`CACHE_REDIS_ENABLED=true`** — **`CACHE_REDIS_URI`** по умолчанию **`redis://propradar-redis:6379`**, перед стартом выполняется **ожидание TCP** Redis (до **120** с); старт приложения — **`npm run db:deploy`**, **`npm run db:generate`**, **`npm run start:prod`** (вместо несуществующего **`deploy_database.sh`**); **`depends_on`** между **`evolution-api`** и Redis **убран**, чтобы исключить **cross-profile** проблемы Compose (**Redis** живёт во **`infra`**, Evolution в **`tools`** — поднимать вместе: **`--profile infra --profile tools`**). **`docker/tools/.env.example`** — блок комментариев про сценарий **infra+tools**. **Scanner** / **`@tester`** — **PASS** (2026-05-08).

- **playwright-worker (Docker):** базовый образ **`mcr.microsoft.com/playwright/python`** обновлён с **v1.49.1-noble** на **v1.59.0-noble** в **`docker/app/playwright-worker.Dockerfile`** (синхронизация с рабочим серверным образом).
- **Деплой / секреты:** в **`.env.example`**, **`docker/app/.env.example`**, **`.env.example.server`** добавлены плейсхолдеры **`MYHOME_EMAIL`** / **`MYHOME_PASSWORD`** и комментарии про обязательность для автологина **`playwright-worker`**; в **`docs/DEPLOY_SERVER.md`** — раздел **«Секреты playwright-worker»**.

- **Playwright-worker (порт):** **`uvicorn`** в контейнере и **`docker/app/docker-compose.yml`** (публикация **8001:8001**, healthcheck) выровнены с документированным **`http://playwright-worker:8001`** (ingress, n8n runbook); ранее использовался **8090**.

- **Docker compose фрагменты (`docker/*`):** у всех сервисов задан **profile** (`infra`, `app`, `tools`, `proxy`); прямой запуск `docker compose up` из подкаталога без `--profile` больше не поднимает сервисы — используйте корневой **`compose.yaml`** или добавляйте **`--profile …`**.

- **Reverse-proxy / TLS (n8n, Evolution):** конфиг nginx использует стабильные пути **`/etc/nginx/certs/{n8n,evolution}/`** внутри контейнера; на хосте пути к `fullchain.pem` / `privkey.pem` задаются через **`N8N_TLS_*`** и **`EVOLUTION_TLS_*`** (file bind-mount). Перед `nginx` выполняется preflight **`00-tls-preflight.sh`**, запуск **явно через `sh`**; проверки **`-f`** (обычный файл) и **читаемости** для всех четырёх PEM. Порты **5678** / **8080** на хост не публикуются (`docker/tools` без `ports` у n8n и evolution-api); внешний вход — **80/443** reverse-proxy. Подробности — `docker/reverse-proxy/README.md`; **Scanner** / **`@tester`** — **PASS** (2026-05-07); следующий гейт процесса — **`@process-guard` Diff Check**.

- **Reverse-proxy / TLS (Metabase, `metabase.usluga-market.ru`):** **Цель:** публичный **HTTPS** для Metabase по тому же паттерну, что n8n и Evolution (терминация на nginx, без обязательной публикации UI только на **3031**). **Реализация:** новый виртуальный хост **`docker/reverse-proxy/nginx/conf.d/metabase.conf`** (HTTP **80** — ACME **`/.well-known`**, редирект на HTTPS; HTTPS **443** — прокси на **`metabase:3000`** с заголовками forwarded); во фрагменте **`docker/reverse-proxy/docker-compose.yml`** — bind-mount **`METABASE_TLS_FULLCHAIN`** / **`METABASE_TLS_PRIVKEY`** → **`/etc/nginx/certs/metabase/{fullchain.pem,privkey.pem}`**; **`00-tls-preflight.sh`** — те же **`check_one`** для пары PEM Metabase и обновлённая подсказка по переменным при ошибке. Runbook и матрица портов — **`docs/DEPLOY_SERVER.md`**, переменные и smoke — **`docker/reverse-proxy/README.md`**. **Проверки:** **`docker compose config`**, сценарий preflight при отсутствии PEM — ожидаемый **`exit 1`**; smoke **HTTP→HTTPS** и браузер — по runbook (`curl -sI http://metabase.usluga-market.ru/`). **`@tester`** — **PASS** (2026-05-08).

### Verified

- **P0 / myhome_login submit-селекторы (`scripts/myhome_login.py`, коммит `9a10de0`):** **Scanner** — **PASS** (со слов человека); **`pytest tests/unit/test_myhome_login.py`** — **PASS**; полный **`pytest tests`** — **PASS** при корректном **`PYTHONPATH`** — **`@tester`** — **PASS** (2026-05-08).

- **P0 / myhome_login EMAIL-селектор `input[name="Email"]` (`scripts/myhome_login.py`):** **Scanner** — **PASS** (со слов человека); **`@tester`** — **PASS** (2026-05-09).

- **P0 / myhome_login тайминг SPA перед поиском полей (`scripts/myhome_login.py`):** **`wait_until="networkidle"`** и **`page.wait_for_timeout(3000)`** перед **`_locate_required_controls`**; **Scanner** — **PASS** (со слов человека); **`@tester`** — **PASS** (2026-05-09).

- **Reverse-proxy / Metabase HTTPS (`metabase.usluga-market.ru`):** **`docker compose config`**, preflight (**6** PEM: n8n, Evolution, Metabase), smoke **`curl -sI http://metabase.usluga-market.ru/`** (редирект на **https**) и UI в браузере — **`@tester`** — **PASS** (2026-05-08).

- **Infra Redis + Evolution (кэш default off, старт npm):** **Scanner** — **PASS**; **`@tester`** — **PASS** (сессия 2026-05-08).

- **Деплой-готовность (reverse-proxy, env-профили, runbook):** **Scanner** — **PASS** (подтверждение человека); `**@tester`** — **PASS** (сессия 2026-05-07).
- **PropRadar API / myhome HTTP:** **Scanner** — **PASS**; `**pytest tests`** — **40 passed**, **2 skipped**; HTTP-эндпоинты `**/api/myhome/*`** с `**X-API-Key**`; n8n-runbook переведён на HTTP (`docs/n8n_myhome_workflow.md`); цепочка до `**@release-check**` — сессия 2026-05-06.
- **Myhome / n8n-синхронизация (список ID, discover, ingest по detail):** **Scanner** — **PASS**; `**pytest tests`** — **30 passed**, **2 skipped** (интеграция myhome); цепочка до `**@release-check`** завершена в сессии 2026-05-06.
- **Leads client / migration 009:** контрольная точка **3** — **PASS**; smoke подтверждён человеком; `city_name` и `owner_name` синхронизируются из statement JSON, Metabase карточка 7 использует их в клиентской выдаче.
- **Leads client v2 / миграция 008:** пересоздание `**leads_client`** под контракт **v2**; **Scanner** — **PASS**; `**@tester`** — **PASS**.
- **Myhome / цены (закрытие цикла):** контрольная точка **3** — **PASS**; **Smoke** подтверждён человеком; для **20** лидов `**price_usd`** и `**price_gel**` совпадают с ожиданием; задача закрыта.
- **Chain completion:** финальный `@release-check` — **PASS**; ручной smoke после деплоя подтверждён человеком.
- **Leads client / финальная проверка:** контрольная точка **3** — **PASS**; Smoke подтверждён человеком; `leads_client` создана и синхронизируется через trigger, готово к финальному деплою.

### Fixed

- **P0 / `scripts/myhome_login.py` — тайминг React SPA перед поиском полей:** в `_run_auto_login` для перехода на auth.tnet.ge используется `wait_until="networkidle"` и добавлена пауза `page.wait_for_timeout(3000)` перед `_locate_required_controls`.
- **P0 / `scripts/myhome_login.py` — EMAIL selector для auth.tnet.ge:** в `EMAIL_SELECTORS` добавлен кандидат `input[name="Email"]` (поле логина с `name` в верхнем регистре по DOM auth.tnet.ge) без изменения остальной логики входа.
- **P0 / `scripts/myhome_login.py` — submit без `:has-text()` (коммит `9a10de0`):** **Цель:** убрать хрупкие submit-селекторы на **`:has-text()`** и усилить предсказуемость автологина. **Реализация:** устойчивые стратегии отправки формы; лог **выбранной стратегии** для сценариев с accessibility-ролями; в лог — **версия пакета Playwright**. **Scope:** `scripts/myhome_login.py`, `tests/unit/test_myhome_login.py`. **Проверки:** **Scanner** — **PASS** (со слов человека); **`pytest tests/unit/test_myhome_login.py`** — **PASS**; полный **`pytest tests`** — **PASS** при корректном **`PYTHONPATH`**. **Следующий гейт процесса:** `@process-guard` **Diff Check**.

- **P1 hotfix / `scripts/myhome_login.py` (scanner-driven fixes, финальный коммит `1f29087`):** **Симптом:** нестабильность сценария автологина Playwright под **Scanner** (инициализация/очистка контекста, трассировка, сохранение сессии). **Исправления:** единая **error handling**; **tracing lifecycle** и **сохранение сессии** при сбое **trace stop**; выравнивание ошибки **`new_page`** с login-flow; **нейтральный лог** при **`new_page_failed`**. **Scope:** `scripts/myhome_login.py`, `tests/unit/test_myhome_login.py`. **Проверки:** **Scanner** — **PASS** (по человеку); **`python -m pytest tests`** — **68 passed**, **2 skipped**; **ruff** целевых путей — **PASS**. **Следующий гейт процесса:** `@process-guard` **Diff Check**.

- **Bug 1 / Evolution API — runtime и Prisma (`docker/tools/docker-compose.yml`):** **Симптом:** контейнер **`evolution-api`** мог завершаться с ошибкой на этапе подготовки БД (в т. ч. из‑за обращения к отсутствующему в образе **`deploy_database.sh`**). **Причина:** актуальный сценарий Evolution v2 выполняет миграции и генерацию Prisma через **npm**-скрипты; отдельный shell-скрипт с таким именем в цепочке старта не гарантирован. **Исправление:** в **`command`** — последовательно **`npm run db:deploy`**, **`npm run db:generate`**, затем **`exec npm run start:prod`** (корректный основной процесс контейнера); оболочка — **`set -euo pipefail`**. **Проверки:** **`docker compose config --quiet`**; **`python -m pytest tests`** — **54 passed**, **2 skipped** (@tester **PASS**, 2026-05-08).

- **P1 hotfix / Evolution API — сборка из корня (`docker/tools/docker-compose.yml`):** у **`evolution-api`** **`build.context`** исправлен с **`docker/tools`** на **`.`** (корень репозитория при запуске из корневого **`compose.yaml`**), чтобы **`docker compose --profile tools build evolution-api`** находил контекст и **`evolution-api.Dockerfile`**. **Симптом:** ошибка сборки при выполнении build из корня. **Проверки:** **`docker compose config --quiet`**, **`docker compose --profile tools build evolution-api`**, **`python -m pytest tests`** — **54 passed**, **2 skipped** (@tester **PASS**, 2026-05-08).

- **P1 hotfix / playwright-worker (Xvfb, entrypoint):** в **`docker/app/playwright-worker-entrypoint.sh`** вместо **`xvfb-run … uvicorn`** — **Xvfb :99** в фоне, **`DISPLAY=:99`**, **`exec uvicorn`** как PID 1 (симптом: **unhealthy**, **uvicorn** отсутствовал в **`ps`**).

- **Evolution API / `docker/tools` — `Database provider invalid`:** для **`evolution-api`** заданы переменные **`DATABASE_*`** и согласованный **`DATABASE_CONNECTION_URI`** (хост **`leads-db`** в Docker-сети **`propradar`**); fallback'и в **`docker/tools/docker-compose.yml`** выровнены; **`docker/tools/.env.example`** дополнен примерами и комментариями. **Scanner** / **`@tester`** — **PASS** (2026-05-07); следующий гейт процесса — **`@process-guard` Diff Check**.
- **P1 / myhome `list_ids` — регрессия `since_days`:** параметр снова учитывается при отборе external ID в постраничном списке Statements API; правка в `src/parsers/adapters/myhome/list_ids.py`, регрессионное покрытие в `tests/unit/test_myhome_list_ids.py` (@tester: целевые unit — PASS; полный `pytest tests` — **51 passed**, **2 skipped**).
- **P0 / myhome list property filter upstream:** в `src/parsers/adapters/myhome/list_ids.py` ключ типа имущества переключён на `real_estate_types` (вместо `object_types`) по результатам аудита live API; добавлена защита от рассинхронизации `category` vs `object_type`.
- **P1 / `fetch-ids` refactor (`limit`):** в `/api/myhome/fetch-ids` убран `since_days`, добавлен `limit=all|N`; в `list_ids` отключена обработка окна по датам и добавлена ранняя остановка по лимиту ID. Обновлены unit-тесты и API/n8n документация.
- **P0 / myhome list filters (`object_types`):** в `src/parsers/adapters/myhome/list_ids.py` заменён неверный ключ `real_estate_types` на `object_types` для фильтрации типа имущества; ограничение по квартирам снова применяется корректно. (@tester: unit + full pytest PASS).
- **P0 / загрузка API (`api.myhome`):** при старте uvicorn возможны `**ModuleNotFoundError`** или неоднозначность пакета `**api**` на `**sys.path**`. Исправление: в `**api/main.py**` — `**from .myhome import router**`; в `**api/myhome.py**` — `**from .auth import ...**` (внутрипакетные импорты, `**PYTHONPATH=src**` без изменений). (@tester: `**pytest tests**` — PASS).
- **P1 / циклический импорт пакета `api`:** убран eager-import `**app`** из `**api/__init__.py**` (цикл с `**api.main**`). Последующий **P0**: в `**api/main.py`** и `**api/myhome.py**` — только **относительные** импорты внутри пакета (@tester: `**pytest`** — PASS).
- **P1 / `scripts/setup_metabase_dashboard.py`:** дашборд собирался только из жёсткого списка из **6** заголовков — игнорировались **«Средняя цена (GEL)»** и карточки **8–10** из `**metabase/propradar_dashboard.json`**. Исправление: чтение **всех** элементов `**cards`**, сортировка по `**position**`, лог `**Processing card {position} {title_ru}**`, раскладка `**_LAYOUT_BY_POSITION**` для позиций **1–10** (@tester: проверка загрузки bundle и ключей layout).
- `**sync_myhome_status.py`:** ошибки CLI (`**parser.error`**, `**SystemExit**`) не перехватывались как `**Exception**` → при неверных аргументах выводится JSON ошибки и код выхода **2** вместо traceback; в `**cmd_discover`** для пустого источника API — `**ValueError**`; интеграционная проверка — `**tests/unit/test_sync_myhome_status_cli.py**` (@tester **PASS**).
- `**ingest_detail`:** в БД сохраняется тот же `**external_id`**, что в запросе к `**GET /v1/statements/{id}**`; при расхождении с `**statement.id**` — запись без save и код `**detail_id_mismatch**` (@tester **PASS**).
- **P1 / Metabase (карточка 7, колонки города и владельца):** в `**metabase/propradar_dashboard.json`** для позиции **7** колонка **«Город»** переведена на `**city_name`** (вместо `**urban_name**`); добавлен `**owner_name**` (**«Имя владельца»**) (@tester **PASS**).
- **P1 / Metabase (карточка 7 «Последние лиды»):** в `**metabase/propradar_dashboard.json`** SQL позиции **7** выводит только **клиентские** столбцы `**leads_client`**; убраны `**lead_id**` и служебные/технические поля из представления таблицы (@tester **PASS**).
- **P1 / Metabase (KeyError):** `**title_ru`** скаляра USD в `**metabase/propradar_dashboard.json**` синхронизирован со скриптом `**scripts/setup_metabase_dashboard.py**` (`**Средняя цена объекта (USD)**`); устранено падение при автосборке дашборда (@tester **PASS**).
- **Ретро после P1 hotfix (Diff Check):** в `**metabase/propradar_dashboard.json`** SQL переведены с `**price_total_usd**` на `**price_usd**`; `**data/myhome_pdf/**` в `**.gitignore**` (PDF enricher не коммитятся); `**src/parsers/adapters/myhome/myhome_api_schema.csv**` согласован с `**price_gel**` / `**price_usd**` (@tester **PASS**).
- **Myhome / `description`:** при маппинге из API удаляются HTML-теги (в т.ч. `**<br />`**), чтобы в **leads-db** сохранялся обычный текст (@tester: unit **PASS**, интеграция **SKIP**).
- **Leads / цены:** добавлена колонка `**price_gel`**, колонка `**price_total_usd**` переименована в `**price_usd**`; миграция `**migrations/006_add_price_gel_rename_price_usd.sql**` (применять после **005**). В Metabase и сохранённых SQL заменить обращения к `**price_total_usd`** на `**price_usd**`.
- **Pending enrichment / `phone`:** `list_pending_enrichment` для лидов **new** учитывает `**phone IS NULL OR phone = ''`**, чтобы пустая строка не исключала запись из очереди и enricher не завершался с `**enriched=0**` при наличии кандидатов; реализация — коммит `**8d347ce**` (@tester: `pytest`/`ruff` PASS, интеграция skipped).
- **Windows / `zoneinfo`:** добавлена зависимость `**tzdata`** в `**pyproject.toml**`, чтобы `**ZoneInfo("Asia/Tbilisi")**` и пайплайн даты публикации myhome не падали на Windows без системной IANA-базы; проверено: `**ZoneInfo**` OK и `**scripts/run_myhome_enricher.py**` без ошибки (@tester PASS).

### Changed

- **Проекция `leads_client` v2:** миграция `**migrations/008_recreate_leads_client_v2.sql`** (после **007**) — пересоздание таблицы; **PK `(source, external_id)`**; **26** столбцов; без `**lead_id`**, `**source_listing_uuid**`, языковых `***_lang**`; триггер/функция синхронизации с `**leads**` сохранены по смыслу (см. SQL). Bundle `**metabase/propradar_dashboard.json**`: `**schema_reference**` и native-SQL выровнены под **008** (Scanner **PASS**, `@tester` **PASS**).
- **Metabase / bundle `metabase/propradar_dashboard.json`:** все native-SQL карточки переведены на таблицу `**leads_client`**; обновлены **«Последние лиды»** (столбцы и сортировка по `**COALESCE(published_at, synced_at)`**); добавлены/уточнены скаляры **средней цены USD** и **GEL** (`ROUND(AVG(...), 2)` по `**price_usd`** / `**price_gel**`); в JSON — `**schema_reference**` (эволюция **007** → актуальный контракт **008**) и `**operator_instructions_ru`** для высоты карточки и прокрутки таблицы в UI Metabase (Scanner **PASS**, `@tester` **PASS**).
- **Myhome / detail-очередь:** `list_pending_detail_enrichment` для `**source=myhome`**, `**status=new**` — условие `**address IS NULL OR price_gel IS NULL**`, чтобы после миграции **006** снова обрабатывались лиды без `**price_gel`** (Scanner **PASS**, @tester **PASS**).
- **Myhome обогащение (архитектура):** поля карточки снимаются с **Statements API** (`**GET /v1/statements/{id}`**, см. `**myhome_api_schema.csv**`); телефон (`**phone/show**`) и PDF (`**page.pdf()**`) остаются на Playwright; очереди в БД разделены на **detail** / **phone** / **pdf** (миграция `**005_myhome_api_first.sql`**).
- Enricher и репозиторий: идемпотентные обновления при повторном обогащении (не перезаписывать уже совпадающие значения).
- Разбор `published_at` с текста страницы: интерпретация в **Asia/Tbilisi**, хранение **UTC** (`parse_published_at_from_text`).
- Парсер списка myhome (`published_at` из API): нормализация к **UTC** для согласованности с enricher.
- Выравнивание конфигурации Cursor (`.cursor/rules`, `.cursor/agents`, `.cursor/skills`) под канон PropRadar (`Docs/AI_GOVERNANCE.md`): единые пути `Docs/PropRadar_STATUS.md`, `Docs/INGRESS_ARCHITECTURE.md`, `Docs/AI_GOVERNANCE.md`; удалены отсылки к чужому репозиторию `dispatch-backend`.

### Added

- **PropRadar HTTP API (myhome для n8n):** `**src/api/myhome.py`**, `**src/api/auth.py**`; эндпоинты `**/api/myhome/fetch-ids**`, `**/ingest**`, `**/sync-status**`, `**/mark-rejected**` (subprocess к существующим `**scripts/*.py**`); `**docs/API.md**`; `**tests/unit/test_myhome_http_api.py**`. В `**docker/app/docker-compose.yml**` — донастройка сервиса `**api**` (volume репозитория в `**/srv**`, `**PYTHONPATH**`, `**depends_on: leads-db**` при merge с infra).
- **Myhome / оркестрация n8n:** `**scripts/fetch_myhome_ids.py`** (полный список ID или окно `**--since-days**`); `**scripts/sync_myhome_status.py**` (подкоманды `**discover**`, `**mark-rejected**`); `**docs/n8n_myhome_workflow.md**` — сценарий Schedule → fetch → парсер → discover → Evolution API → mark-rejected. Без секретов Evolution в репозитории.
- **Миграция `migrations/010_add_status_reason_to_leads.sql`:** колонка `**status_reason`** в `**leads**` (код причины, например `**disappeared_from_api**`). Домен `**Lead.status_reason**`; репозиторий: `**list_external_ids_by_source_and_status**`, `**mark_leads_by_external_ids**` (только из `**status=new**`).
- **Пакеты myhome:** `**src/parsers/adapters/myhome/list_ids.py`** (постраничный список API), `**ingest_detail.py**` (ингест по detail ID). `**scripts/run_myhome_parser.py`:** опция `**--ingest-ids-json`**. Unit-тесты: `**tests/unit/test_myhome_list_ids.py**`, `**tests/unit/test_ingest_detail.py**`, `**tests/unit/test_sync_myhome_status_cli.py**`.
- `**leads_client` / миграция 009:** колонки `**city_name`** и `**owner_name**` в проекции; backfill и синхронизация из `**leads.myhome_statement_json**` по ключам `**city_name**` / `**owner_name**` (соединение `**(source, external_id)**`); `**sync_leads_client_from_lead**` — маппинг в **INSERT** и **ON CONFLICT DO UPDATE**; источник — только JSON statement (**не** `**leads.city_name`**). Файл: `**migrations/009_add_city_name_to_leads_client.sql**` (после **008**).
- **Проекция `leads_client`:** таблица денормализованного представления `**leads`** для клиентских выборок; миграция `**migrations/007_create_leads_client_table.sql**` (после **006**): функция `**sync_leads_client_from_lead`**, триггер `**trg_leads_sync_client**` на `**leads**` (**INSERT**/**UPDATE**), индексы на `**external_id`** и `**district_name**`, начальное заполнение из `**leads**` (Scanner **PASS**, @tester **PASS**).
- `**scripts/backfill_price_gel.py`** — backfill `**price_gel**` для myhome: только `**status=new**` и `**price_gel IS NULL**`, тот же HTTP-путь, что у enricher (`**GET /v1/statements/{id}**`), параметр `**--limit**` (Scanner **PASS**, @tester **PASS**).
- Myhome **API-first** и enricher: канон полей `**src/parsers/adapters/myhome/myhome_api_schema.csv`**; пакет `**src/parsers/adapters/myhome/**` (`parser.py`, `schema.py`, `enricher.py` с HTTP-деталями, `phone.py`, `pdf.py`, извлечение полей, локаль страницы, разбор даты публикации); фасады `**src/parsers/myhome.py**`, `**src/parsers/myhome_enricher.py**` (реэкспорт публичного API); миграция `**005_myhome_api_first.sql**`; очереди `**list_pending_detail_enrichment**` / `**list_pending_phone_enrichment**` / `**list_pending_pdf_enrichment**`; колонки `**geo_lat**`, `**geo_lng**`, `**listing_views**`, `**myhome_statement_json**`, `**pdf_url**`.
- Миграция `migrations/004_add_text_lang_columns.sql`: колонки `address_lang`, `district_lang`, `description_lang` в `leads`.
- Стартовый скелет приложения: `src/` (parsers, domain, repositories, services, api, config), `tests/`, `migrations/001_init_leads.sql`, `scripts/setup_venv.ps1`, Docker (`docker/infra`, `docker/tools`, `docker/app`), корневые `pyproject.toml`, `.env.example`, `.gitignore`, `.python-version`.
- Metabase: `**docker/tools**` (таймзона UTC), `**metabase/propradar_dashboard.json**`, `**docs/METABASE_SETUP.md**`, переменные `**LEADS_DB_***` в `**docker/tools/.env.example**`; скрипт `**scripts/setup_metabase_dashboard.py**` (API: дашборд «PropRadar — Лиды», идемпотентность); `**ruff**` охватывает `**scripts/**`.
- Парсер **myhome.ge**: `src/parsers/myhome.py`, `PostgresLeadRepository`, `migrations/002_add_myhome_listing_fields.sql`, `scripts/run_myhome_parser.py`, unit- и integration-тесты (`MYHOME_INTEGRATION=1` для live API); настройка `MYHOME_API_BASE_URL`.
- Обогащение **myhome.ge**: `migrations/003_add_lead_details.sql`, `src/parsers/myhome_enricher.py`, `src/parsers/exceptions.py`, расширение `Lead` и `LeadRepository`, `scripts/myhome_login.py`, `scripts/run_myhome_enricher.py`, unit-тесты `tests/unit/test_myhome_enricher.py`; сессия Playwright в `scripts/myhome_session.json` (в `.gitignore`).
- Минимальный unit-тест `tests/unit/test_api_health.py` для `GET /health`.