# Телефон объявления myhome.ge — контур и реализация

Адаптер: **myhome.ge**  
Обновлено: 2026-05-15

Основной путь получения телефона — **HTTP + 2captcha** (без браузера, ~16 с/лид).  
Playwright остаётся как **fallback** и для обновления JWT-сессии.

## Оглавление

1. [Операционный статус](#1-операционный-статус)
2. [Архитектура авторизации](#2-архитектура-авторизации)
3. [Основной путь: HTTP + 2captcha](#3-основной-путь-http--2captcha)
4. [Fallback путь: Playwright](#4-fallback-путь-playwright)
5. [Очередь и retry-стратегия](#5-очередь-и-retry-стратегия)
6. [Конфигурация](#6-конфигурация)
7. [Запуск и диагностика](#7-запуск-и-диагностика)
8. [Результаты тестов](#8-результаты-тестов)
9. [Бэклог](#9-бэклог)
10. [Оркестрация n8n](#10-оркестрация-n8n)
11. [См. также](#11-см-также)

---

## 1. Операционный статус

**Статус (2026-05-15): HTTP+2captcha — подтверждено на сервере, в продакшн-релизе.**


| Путь            | Скорость   | Success rate   | Статус                 |
| --------------- | ---------- | -------------- | ---------------------- |
| HTTP + 2captcha | ~16 с/лид  | ожидается >98% | **Основной (primary)** |
| Playwright      | ~60+ с/лид | 98% (49/50)    | **Fallback**           |


Прокси с residential IP (`fxdx.in`) используется для обоих путей.

---

## 2. Архитектура авторизации

Три независимых контура защиты myhome.ge:


| Контур                         | Механизм                             | Как решается                                                                      |
| ------------------------------ | ------------------------------------ | --------------------------------------------------------------------------------- |
| **Cloudflare**                 | CDN fingerprinting + IP-репутация    | residential прокси + playwright-stealth (только для логина и Playwright-fallback) |
| **reCAPTCHA v3**               | Невидимая капча при запросе телефона | **2captcha API** (~14 с, $2/1000 токенов)                                         |
| **AccessToken / RefreshToken** | JWT в cookie `.tnet.ge`, TTL ~11 мин | `myhome_login.py` через Playwright + **`PLAYWRIGHT_PROXY_*`** (login-if-needed в воркере) |


**Важно:**

- `api-statements.tnet.ge` — **не защищён CF**. UUID объявления и детали берутся напрямую без браузера.
- `api3.myhome.ge` — за CF, недоступен без браузера. Обновление токена только через Playwright login.
- reCAPTCHA v3 site key myhome.ge: `6LeziPEpAAAAAHuR9vWBVCrfklSbWt8zixM4jAbM`

---

## 3. Основной путь: HTTP + 2captcha

Реализация: `src/parsers/adapters/myhome/phone_http.py` — `MyHomePhoneHttpEnricher`

### 3.1 Поток для каждого лида

```
1. Прочитать AccessToken из myhome_session.json
   └─ Если `expires_at - now < MYHOME_SESSION_MIN_REMAINING_SECONDS` (default 40 с) → `myhome_login.py` в том же job воркера (**Playwright через тот же proxy**, что HTTP/phone enrich)

2. Получить statement_uuid
   └─ GET https://api-statements.tnet.ge/v1/statements/{ext_id}
      Header: X-Website-Key: myhome
      Ответ: HTTP 200, JSON без CF, без авторизации
      Поле: data.statement.uuid

3. Запросить reCAPTCHA токен у 2captcha
   └─ POST https://2captcha.com/in.php
      method=userrecaptcha, version=v3, action=verify
      googlekey=6LeziPEp…, pageurl=https://www.myhome.ge/
      Ждать результат: GET /res.php polling каждые 3 сек (~14 сек)

4. Запросить телефон
   └─ POST https://api-statements.tnet.ge/v1/statements/phone/show
         ?statement_uuid={uuid}
      Headers:
        global-authorization: {AccessToken}
        x-website-key: myhome
        Content-Type: application/json
      Body: {"response_token": "{2captcha_token}"}
      Прокси: PLAYWRIGHT_PROXY_*

5. Разобрать ответ
   └─ HTTP 200 + JSON → phone_number из data.phone_number
   └─ HTTP 400 / bad token → increment phone_retries → следующий батч
   └─ HTTP 401 → под lock один relogin (`relogin_fn` из воркера) → один retry `phone/show`; при успехе **`phone_retries` не растёт**; повторный 401 / fail login → `release` как раньше

6. Сохранить в БД
   └─ repository.update_enriched_fields(lead_id, phone=…)

```

### 3.2 Тайминги


| Шаг              | Время         |
| ---------------- | ------------- |
| Чтение JWT       | ~0 с          |
| Запрос UUID      | ~1 с          |
| 2captcha решение | ~14 с         |
| POST phone/show  | ~1 с          |
| **Итого**        | **~16 с/лид** |


### 3.3 Параллелизм и JWT

5 потоков (`ThreadPoolExecutor`, `MYHOME_PHONE_HTTP_WORKERS=5`).  
На **каждый лид в потоке** — **два** отдельных `httpx.Client` (myhome API + 2captcha); общий клиент между потоками **не используется**.  
**JWT в батче:** `_AccessTokenProvider` + `threading.Lock` — проактивный relogin при `remaining < 90` с (`TOKEN_PROACTIVE_REFRESH_MIN_REMAINING_S`); перед стартом job воркер по-прежнему проверяет **`MYHOME_SESSION_MIN_REMAINING_SECONDS`** (default **40** с). Relogin только через `relogin_fn` из `main.py`, не subprocess из enricher.

**Волны drain:** `enrich_batch(limit=N)` — до **N** лидов волнами по `max_workers`: каждая волна — `claim(1)` на слот; следующая волна, пока очередь не пуста и `processed < min(limit, 500)`.

Выборка лидов из БД — атомарная, `SELECT … FOR UPDATE SKIP LOCKED` — гонки исключены.

**Резерв при claim (in-flight):** в той же транзакции claim — `status_reason = phone_enriching`, `updated_at = now()` (**`phone_retries` не меняется**). Лид снова eligible, если `status_reason` пустой, не `phone_enriching`, или enriching **старше** `PHONE_ENRICH_STALE_MINUTES` (default **15**, env). В начале батча — `sweep_stale_phone_enriching` (только `status_reason`, retries не трогаем). После успеха — `status_reason = NULL`; после ошибки — `release_phone_enrich_after_failure` (`phone_retries += 1`).

---

## 4. Fallback путь: Playwright

Реализация: `src/parsers/adapters/myhome/phone.py` — `MyHomePhoneEnricher`  
**Файл не изменяется.** Очередь — **`claim_pending_phone_enrichment`** (как у HTTP), не `list_*`.  
Используется при `phase=phone_playwright` или если HTTP отключён. **Не запускать параллельно** с активным `phase=phone`.

### 4.1 Когда используется

- `MYHOME_PHONE_HTTP_ENABLED=False` — откат без деплоя
- `phase=phone_playwright` в POST /enrich — явный вызов Playwright
- Лиды с `phone_retries >= 1` которые не прошли HTTP (опционально через n8n)

### 4.2 Поток (кратко)

```
load_storage() → pkill chromium → sync_playwright()
  → chromium.launch(headless, stealth, proxy)
  → page.goto(url, domcontentloaded) → networkidle
  → проверка CF → dismiss_popup()
  → locator("text=ნომრის ნახვა") → JS evaluate (unhide) → click()
  → expect_response("phone/show", status in (200, 204))
    200 → parse_phone_response() → JSON phone_number
    204 → body.inner_text() + regex +995…
  → context.storage_state() → save to disk
→ browser.close() → pkill chromium → waitpid → sleep(2–4с)

```

Подробности: `docs/playwright_worker.md`, `docs/myhome_login.md`.

---

## 5. Очередь и retry-стратегия

### 5.1 Условие выборки лидов

```sql
SELECT … FROM leads
WHERE source = 'myhome'
  AND status = 'new'
  AND (phone IS NULL OR phone = '')
  AND phone_retries < 3
ORDER BY created_at
LIMIT :limit
FOR UPDATE SKIP LOCKED

```

### 5.2 Счётчик phone_retries


| Событие                    | Действие                                                                                   |
| -------------------------- | ------------------------------------------------------------------------------------------ |
| Успех (phone получен)      | phone записан, phone_retries не меняется                                                   |
| 2captcha error / timeout   | `phone_retries += 1`                                                                       |
| phone/show 400 / bad token | `phone_retries += 1`                                                                       |
| phone/show 401 (JWT истёк) | relogin под lock + один retry; при успехе retries **не** растут; иначе `release` / retries как при других ошибках |
| `phone_retries >= 3`       | `status_reason = 'phone_enrich_failed'`, статус остаётся `new`, лид исключается из очереди |


### 5.3 Добивка через n8n

После основного батча (`phase=phone`) n8n ждёт 5–15 мин и запускает повторный батч (`phase=phone`).  
Лиды с `phone_retries=1,2` автоматически попадают в следующую выборку.  
После 3 неудачных попыток лид исключается (`phone_enrich_failed`).

---

## 6. Конфигурация


| Переменная                  | Описание                                     | Обязательна    |
| --------------------------- | -------------------------------------------- | -------------- |
| `TWOCAPTCHA_API_KEY`        | API ключ 2captcha                            | Да (HTTP путь) |
| `MYHOME_RECAPTCHA_SITE_KEY` | site key reCAPTCHA v3 (default: `6LeziPEp…`) | Нет            |
| `MYHOME_PHONE_HTTP_WORKERS` | Число параллельных потоков (default: 5)      | Нет            |
| `MYHOME_PHONE_HTTP_ENABLED` | Включить HTTP enricher (default: True)       | Нет            |
| `MYHOME_SESSION_PATH`       | Путь к файлу сессии (`myhome_session.json`)  | Да             |
| `PLAYWRIGHT_PROXY_SERVER`   | Адрес прокси, напр. `http://host:port`       | Для CF         |
| `PLAYWRIGHT_PROXY_USER`     | Логин прокси                                 | При auth       |
| `PLAYWRIGHT_PROXY_PASS`     | Пароль прокси                                | При auth       |


На сервере сессия: `/data/adapter_sessions/myhome_session.json` (volume `playwright_sessions`).

---

## 7. Запуск и диагностика

**Обновить JWT-сессию (логин через Playwright):**

```bash
curl -X POST http://localhost:8001/login \
  -H 'Content-Type: application/json' \
  -d '{"adapter": "myhome"}'

```

**Запустить HTTP обогащение (основной путь):**

```bash
curl -X POST http://localhost:8001/enrich \
  -H 'Content-Type: application/json' \
  -d '{"phase": "phone", "adapter": "myhome", "limit": 50}'

```

**Запустить Playwright обогащение (fallback):**

```bash
curl -X POST http://localhost:8001/enrich \
  -H 'Content-Type: application/json' \
  -d '{"phase": "phone_playwright", "adapter": "myhome", "limit": 10}'

```

**Проверить токен сессии:**

```bash
docker exec propradar-playwright-worker-1 python3 -c "
import json, base64, time
data = json.load(open('/data/adapter_sessions/myhome_session.json'))
tok = next((c for c in data['cookies'] if c['name']=='AccessToken'), None)
if tok:
    payload = json.loads(base64.b64decode(tok['value'].split('.')[1] + '=='))
    remaining = payload['expires_at'] - time.time()
    print('remaining:', round(remaining), 'sec =', round(remaining/60, 1), 'min')
"

```

**Лиды без телефона в БД:**

```bash
docker exec propradar-leads-db psql -U leads -d leads -c \
  "SELECT COUNT(*), phone_retries FROM leads WHERE source='myhome' AND (phone IS NULL OR phone='') GROUP BY phone_retries ORDER BY phone_retries;"

```

**Логи воркера:**

```bash
docker logs propradar-playwright-worker-1 --tail 100 -f

```

**Коды ошибок:**


| Код                      | Путь    | Причина                                    |
| ------------------------ | ------- | ------------------------------------------ |
| `captcha_timeout`        | HTTP    | 2captcha не ответил за 120 с               |
| `captcha_error`          | HTTP    | 2captcha вернул ошибку                     |
| `phone_api_bad_token`    | HTTP    | phone/show 400 — токен не прошёл валидацию |
| `phone_api_unauthorized` | HTTP/PW | phone/show 401 — JWT истёк                 |
| `phone_api_http_NNN`     | HTTP/PW | phone/show 4xx/5xx                         |
| `phone_api_denied`       | HTTP/PW | `result != true` в JSON ответа             |
| `phone_api_empty`        | HTTP/PW | Номер в ответе пустой                      |
| `CloudflareBlock`        | PW      | CF challenge не прошёл                     |
| `TimeoutError`           | PW      | Страница/кнопка не загрузилась за 30 с     |


---

## 8. Результаты тестов

### HTTP + 2captcha (2026-05-15, сервер)


| Шаг                            | Результат                            |
| ------------------------------ | ------------------------------------ |
| UUID из api-statements.tnet.ge | HTTP 200, без CF ✅                   |
| 2captcha reCAPTCHA v3          | токен получен за ~14 с ✅             |
| POST phone/show с токеном      | HTTP 200, phone_number = 591100282 ✅ |
| Итого                          | ~16 с/лид ✅                          |


### Playwright fallback (2026-05-12)


| Тест                | Лидов  | Результат       | Причина потерь                          |
| ------------------- | ------ | --------------- | --------------------------------------- |
| Тест 1              | 3      | 2/3             | TimeoutError — просроченное объявление  |
| Тест 2              | 10     | 9/10            | RuntimeError — снятое объявление        |
| Тест 3 (старый код) | 50     | 19/50 (38%)     | Токен истёк + CF-блокировки             |
| Тест 4 (новый код)  | 50     | 42/50 (84%)     | CF rate-limit на 8 лидов                |
| Тест 5 (retry 8)    | 8      | 7/8             | 1 лид стабильно блокируется CF          |
| **ИТОГО**           | **50** | **49/50 (98%)** | ext=23971326 — стабильная CF-блокировка |


---

## 9. Бэклог


| Приоритет   | Задача                                                                                                   |
| ----------- | -------------------------------------------------------------------------------------------------------- |
| **ВЫСОКИЙ** | `init: true` в `docker-compose.yml` для playwright-worker → tini как PID 1, автоматический reaping зомби |
| ~~**ВЫСОКИЙ**~~ | ~~n8n: login cron + enrich~~ — **2026-05-16:** login-if-needed в `phase=phone` воркера; cron `MvaHceZGVlUxDIHM` inactive; v4 только `POST /enrich` |
| **СРЕДНИЙ** | Мониторинг success rate: метрика после каждого батча, алерт если `enriched/total < 80%`                  |
| **СРЕДНИЙ** | Ротация прокси при росте объёма (500+ лидов/день)                                                        |
| **НИЗКИЙ**  | Ограничение памяти контейнера playwright-worker                                                          |
| **НИЗКИЙ**  | Проверить и задокументировать `phase=detail` и `phase=pdf`                                               |


---

## 10. Оркестрация n8n

n8n вызывает `POST http://playwright-worker:8001/enrich` — ожидается **HTTP 202** (задача принята, не результат).

**Основной батч:**

```json
{"adapter": "myhome", "phase": "phone", "limit": 50}

```

**Добивка (через 5–15 мин после основного батча):**

```json
{"adapter": "myhome", "phase": "phone", "limit": 50}

```

Лиды с `phone_retries=1,2` автоматически попадают в выборку.

**Fallback (опционально, медленно):**

```json
{"adapter": "myhome", "phase": "phone_playwright", "limit": 10}

```

Подробности: `docs/n8n_myhome_workflow.md`.

---

## 11. См. также

- `src/parsers/adapters/myhome/phone_http.py` — `MyHomePhoneHttpEnricher` (HTTP + 2captcha, основной)
- `src/parsers/adapters/myhome/phone.py` — `MyHomePhoneEnricher` (Playwright, fallback)
- `src/parsers/adapters/myhome/constants.py` — BTN_SELECTORS, TW_MS
- `src/parsers/adapters/myhome/browser.py` — `dismiss_popup`, `save_timeout_shot`
- `docs/myhome_login.md` — обновление JWT-сессии, SSO TNET
- `docs/playwright_worker.md` — деплой воркера, профили Docker
- `docs/INGRESS_ARCHITECTURE.md` — общая схема потока данных

