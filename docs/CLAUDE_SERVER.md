# PropRadar — справочник сервера для Claude

> Обновляй этот файл при каждом существенном изменении архитектуры.
> Актуально на: 2026-05-17.

---

## 1. Сервер

| Параметр | Значение |
|----------|---------|
| IP | `178.104.79.236` |
| OS | Ubuntu / Linux 6.8 |
| Корень проекта | `/srv/propradar` |
| Docker network | `propradar` |
| Текущий пользователь | `claude` (uid=1000), группа `docker` |

---

## 2. Контейнеры и порты

| Контейнер | Роль | Внутренний порт |
|-----------|------|----------------|
| `propradar-playwright-worker-1` | FastAPI, phone enrich, Playwright | `8001` |
| `propradar-api-1` | FastAPI, myhome ingest | `8000` |
| `propradar-leads-db` | PostgreSQL 15 | `5432` |
| `propradar-n8n-1` | n8n automation | `443` (HTTP, НЕ TLS!) |
| `propradar-metabase-1` | Metabase BI | внешний `3031` → `3000` |
| `propradar-redis` | Redis | `6379` |
| `propradar-parsers-1` | Парсеры (background) | — |
| `propradar-evolution-api-1` | WhatsApp / Evolution API | `8080` |
| `propradar-reverse-proxy` | nginx TLS | `80`, `443` |

**n8n слушает HTTP:443 внутри Docker** (N8N_PORT=443, не HTTPS).
Снаружи доступен через nginx → `n8n.usluga-market.ru`.

docker-compose файлы:
- `docker/tools/docker-compose.yml` — n8n, Metabase, Evolution API
- `docker/infra/` — PostgreSQL, Redis

---

## 3. База данных

```
USER: leads   DB: leads   HOST: leads-db (внутри Docker)
DATABASE_URL=postgresql://leads:***@leads-db:5432/leads
```

```bash
docker exec propradar-leads-db psql -U leads -d leads -c "SELECT ..."
```

Основная таблица: `leads` — все лиды myhome.ge.

| Колонка | Смысл |
|---------|-------|
| `status` | Всегда `new` (других статусов сейчас нет) |
| `status_reason` | `phone_enriching` — занят потоком; `phone_enrich_failed` — retries≥3 |
| `phone_retries` | 0–3; при ≥3 лид считается exhausted |
| `source_listing_uuid` | UUID объявления для phone/show API |

---

## 4. Playwright-worker (`playwright-worker:8001`)

### Эндпоинты

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | `{"status":"ok"}` |
| GET | `/proxy/check` | Проверка прокси через api.ipify.org |
| GET | `/session/check` | Статус AccessToken: remaining_seconds, expires_at |
| GET | `/status` | Текущий job: idle/running, elapsed_seconds |
| GET | `/queue` | Количество pending лидов (phone_retries < 3) |
| GET | `/metrics` | Счётчики: total_enriched, total_failed, total_401, total_logins |
| POST | `/enrich` | Запустить обогащение (202, фоновой job) |
| POST | `/login` | Принудительный логин myhome (202, фоновой job) |
| POST | `/session/reset` | Удалить файл сессии |

### POST /enrich — параметры
```json
{"adapter": "myhome", "phase": "phone", "limit": 150}
```
`phase`: `phone` | `phone_playwright` | `detail` | `pdf`

### Параллельность
- Один job за раз: `threading.Lock(blocking=False)` — не очередь, пропускает
- `ThreadPoolExecutor(max_workers=5)` — настраивается `MYHOME_PHONE_HTTP_WORKERS`
- `enrich_batch(limit=N)` — волны по `max_workers` до `claim==0` или `processed>=min(N,500)`; каждая задача: `claim(limit=1)` → captcha → phone/show

### Токен сессии
- Файл: `/data/adapter_sessions/myhome_session.json` (Playwright storage state)
- Cookie: `AccessToken` (JWT, поле `expires_at`)
- **TTL: 660 секунд (11 минут)** — подтверждено на реальном токене
- JWT payload: `{v, iat, expires_at, data:{user_id, username, session_id, phone, ...}}`
- Перед phone-фазой (воркер): если `remaining < 40s` → re-login (`myhome_login.py`)
- В батче (`_AccessTokenProvider`): lock + proactive relogin при `remaining < 90s`; на **401** — один relogin + retry без `phone_retries++` при успехе

---

## 5. Phone enrichment — flow

```
n8n: POST /enrich {phase:"phone", limit:pending}  (cap 500 в enricher)
  └→ session_needs_login()? → да: subprocess scripts/myhome_login.py (Playwright)
  └→ sweep_stale_phone_enriching()
  └→ волны: _AccessTokenProvider.get() / refresh на 401
  └→ ThreadPoolExecutor(5 workers), claim(1) на слот, drain до пустой очереди:
       каждый поток:
         1. claim_pending(limit=1) → status_reason='phone_enriching'
         2. resolve_statement_uuid (из lead.source_listing_uuid или API)
         3. TwoCaptcha.solve_recaptcha_v3()
            - poll_interval: 3s
            - max_wait: 120s
         4. POST /v1/statements/phone/show
            - header: global-authorization: <AccessToken>
            - timeout: 60s
         5. update_enriched_fields(phone) ИЛИ release + phone_retries++
```

### phone_http vs phone_playwright

| | phone_http | phone_playwright |
|--|-----------|-----------------|
| n8n phase param | `"phone"` | `"phone_playwright"` |
| Класс | `MyHomePhoneHttpEnricher` | `MyHomePhoneEnricher` |
| Метод | HTTP + 2captcha reCAPTCHA v3 | Playwright браузер, клик кнопки |
| Требует AccessToken | **Да** | **Да** |
| Скорость | ~16s/лид | медленнее |
| Активен | **Да** | fallback, `MYHOME_PHONE_PLAYWRIGHT_FALLBACK=false` |

n8n всегда посылает `phase: "phone"` → Playwright browser **не запускается автоматически**.

---

## 6. n8n Workflow myhome

- ID: **`yG1JxQnR6kX0Vlgt`** (PropRadar — myhome v5, active)
- SDK-файл: `scripts/n8n_workflows/yG1JxQnR6kX0Vlgt_v5_proxy_gate.sdk.js`
- Расписание: `0 9 * * *` UTC = **13:00 Tbilisi** (UTC+4)
- Wait enrich: **480s**, затем poll **`GET /status`** каждые **30s** до `idle` (execution timeout **3600s** → TG)
- Лимит батча: **`limit: pending`** (воркер cap **500**)

### Пайплайн
```
Schedule/Manual
  → TG:Старт
  → GET /health (тест воркера)
  → GET /proxy/check → IF ok=false → TG:ошибка + СТОП
  → Fetch IDs (1500 max, tbilisi, apartment, private)
  → Дедупликация → Существующие IDs в БД → Фильтр новых
  → TG: fetch stats (total_api, existing, new_count)
  → IF new_count > 0:
      → POST /api/myhome/ingest
      → TG: ingest результат (parsed, new, errors)
  → SQL: COUNT pending (phone IS NULL, retries<3)
  → IF pending > 0:
      → POST /enrich {phase:"phone", limit:pending}
      → TG: обогащение запущено
      → Wait 480s → poll GET /status (30s) until idle
      → SQL enrich stats (total, with_phone, failed, pending)
      → TG: обогащение завершено
```

---

## 7. Throughput (факт 17.05.2026)

| Метрика | Значение |
|---------|---------|
| Потоков | 5 |
| Wait window | 480s |
| Обогащено за цикл | 148 лидов |
| Throughput | ~0.31 лид/сек |
| Среднее время/лид | ~16s |
| Bottleneck | 2captcha latency (poll 3s, solve ~30–45s) |
| Ошибки | 2 (1 captcha fail, 1 HTTP 400) |
| Pending после цикла | 332 из 480 |
| Циклов для 480 лидов | ~3 (≈24 мин реального времени) |

---

## 8. Ключевые env-переменные (worker)

| Переменная | Значение | Описание |
|------------|----------|---------|
| `MYHOME_PHONE_HTTP_WORKERS` | `5` | Потоков в ThreadPoolExecutor (max 10) |
| `MYHOME_ENRICH_LIMIT` | не задан → `50` | Default если нет limit в запросе |
| `MYHOME_SESSION_PATH` | `/data/adapter_sessions/myhome_session.json` | Файл сессии |
| `MYHOME_SESSION_MIN_REMAINING_SECONDS` | не задан → `40` | Порог для re-login |
| `MYHOME_PHONE_HTTP_ENABLED` | `true` | HTTP-режим включён |
| `MYHOME_PHONE_PLAYWRIGHT_FALLBACK` | не задан → `false` | Playwright fallback выключен |
| `TWOCAPTCHA_API_KEY` | `41e66b4e...` | 2captcha API |
| `PLAYWRIGHT_PROXY_SERVER` | `http://utcso6t3nr.cn.fxdx.in:15539` | Текущий прокси |
| `MYHOME_EMAIL` | `ruzzo0007@gmail.com` | Логин myhome |

---

## 9. Быстрые команды (копипаст в начале сессии)

```bash
# Все контейнеры
docker ps --format "table {{.Names}}\t{{.Status}}"

# Логи воркера (последние 30 мин)
docker logs propradar-playwright-worker-1 --since 30m --tail 200

# Логи: только ошибки/ключевые события
docker logs propradar-playwright-worker-1 --since 1h 2>&1 | \
  grep -E "enrich done|enrich start|WARNING|ERROR|login|401"

# Статус лидов в БД
docker exec propradar-leads-db psql -U leads -d leads -c "
  SELECT COUNT(*) total,
    COUNT(*) FILTER (WHERE phone IS NOT NULL AND phone!='') with_phone,
    COUNT(*) FILTER (WHERE (phone IS NULL OR phone='') AND phone_retries<3) pending,
    COUNT(*) FILTER (WHERE phone_retries>=3) exhausted
  FROM leads;"

# Последние executions n8n (без API ключа)
docker run --rm -v propradar_n8n_data:/data alpine sh -c \
  "apk add --quiet sqlite && sqlite3 /data/database.sqlite \
   'SELECT id, status, startedAt, stoppedAt FROM execution_entity \
    WHERE workflowId=\"yG1JxQnR6kX0Vlgt\" ORDER BY startedAt DESC LIMIT 5;'"

# Статус токена сессии
docker exec propradar-playwright-worker-1 python3 -c "
import json, time, base64
data = json.load(open('/data/adapter_sessions/myhome_session.json'))
tok = next(c['value'] for c in data['cookies'] if c['name']=='AccessToken')
parts = tok.split('.')
pad = '=' * (-len(parts[1]) % 4)
pl = json.loads(base64.urlsafe_b64decode(parts[1] + pad))
exp = pl['expires_at']
remaining = int(float(exp) - time.time())
print(f'remaining: {remaining}s ({remaining//60}m {remaining%60}s)')
"

# Метрики воркера
curl -s http://playwright-worker:8001/metrics  # изнутри Docker
# или:
docker exec propradar-n8n-1 wget -qO- http://playwright-worker:8001/metrics
```

---

## 10. Домены

| Домен | Сервис | Логин |
|-------|--------|-------|
| `n8n.usluga-market.ru` | n8n | — |
| `metabase.usluga-market.ru` | Metabase | `ruzzo0007@gmail.com` |
| `api.usluga-market.ru` | PropRadar API | X-API-Key header |

---

## 11. Структура исходников

```
/srv/propradar/
├── src/
│   ├── worker/main.py                         — FastAPI worker (все эндпоинты)
│   ├── parsers/adapters/myhome/
│   │   ├── phone_http.py                      — HTTP enricher (2captcha + phone/show)
│   │   ├── phone.py                           — Playwright enricher (fallback)
│   │   ├── enricher.py                        — Detail enricher (адрес, площадь и др.)
│   │   ├── pdf.py                             — PDF enricher
│   │   ├── constants.py                       — URL, заголовки, REQUEST_TIMEOUT_S=60s
│   │   └── playwright_proxy.py                — Proxy kwargs для Playwright launch
│   ├── config/settings.py                     — Все env-переменные (pydantic-settings)
│   └── repositories/postgres_lead_repository.py — claim/release/update leads
├── scripts/
│   ├── myhome_login.py                        — Playwright login (subprocess из воркера)
│   └── n8n_workflows/                         — SDK-файлы workflow
├── docker/
│   ├── tools/docker-compose.yml               — n8n, Metabase, Evolution API
│   └── infra/                                 — PostgreSQL, Redis
├── docs/
│   ├── CLAUDE_SERVER.md                       — ЭТОТ ФАЙЛ (обновлять при изменениях)
│   ├── PropRadar_STATUS.md                    — подробный лог всех изменений
│   ├── playwright_worker.md                   — документация воркера
│   ├── phone_extraction.md                    — документация phone enrichment
│   └── n8n_myhome_workflow.md                 — документация workflow
└── .env                                       — секреты (не в git, только на сервере)
```

---

## 12. Известные особенности и ловушки

- **docs/ owned root** — для записи нужен `sudo chown -R claude:claude /srv/propradar/docs`
- **n8n порт 443** — не HTTPS, HTTP внутри Docker; путает при дебаге curl
- **Токен 11 мин** — mid-batch refresh при `remaining < 90s` и 401-retry под lock (см. `phone_http._AccessTokenProvider`)
- **n8n** ждёт **`/status idle`**, не фиксированный таймер после 480s warm-up
- **phone_retries**: инкрементируется только при ошибке, не при claim
- **ValidationError на ingest**: старые короткие ID (≤8 цифр) — норма, в БД не попадают
