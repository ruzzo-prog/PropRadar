# Телефон объявления myhome.ge — контур и реализация

Актуальное правило PropRadar: **номер продавца для myhome.ge получается только через Playwright** (карточка объявления, **reCAPTCHA v3**, ответ **`phone/show`**), в связке с **валидной сессией** TNET (см. `docs/myhome_login.md` и `docs/playwright_worker.md`). Прямой HTTP к публичной HTML-странице карточки **не используется** в проде.

## Оглавление

1. [Операционный статус](#1-операционный-статус)
2. [Архитектура авторизации](#2-архитектура-авторизации)
3. [Технический поток](#3-технический-поток)
4. [Ключевые решения и баги](#4-ключевые-решения-и-баги)
5. [Конфигурация](#5-конфигурация)
6. [Запуск и диагностика](#6-запуск-и-диагностика)
7. [Результаты тестов](#7-результаты-тестов)
8. [Бэклог](#8-бэклог)
9. [Почему HTTP не работает](#9-почему-http-не-работает)
10. [Историческая диагностика `__NEXT_DATA__`](#10-историческая-диагностика-__next_data__)
11. [Оркестрация n8n](#11-оркестрация-n8n)
12. [См. также](#12-см-также)

---

## 1. Операционный статус

**Статус (2026-05-12): РАБОТАЕТ — 98% (49/50 лидов).**

Прокси с residential IP (`fxdx.in`) обходит Cloudflare. Один лид (`ext=23971326`) стабильно блокируется CF по неизвестной причине независимо от сессии и прокси — ожидаемая потеря.

**Переменные прокси:** `PLAYWRIGHT_PROXY_SERVER`, `PLAYWRIGHT_PROXY_USER`, `PLAYWRIGHT_PROXY_PASS` — см. [раздел 5](#5-конфигурация).

---

## 2. Архитектура авторизации

Сайт работает на трёх независимых контурах:

| Контур | Механизм | Как обходится |
|---|---|---|
| **Cloudflare** | CDN fingerprinting + IP-репутация | playwright-stealth + пауза 2–4с между лидами + residential прокси |
| **reCAPTCHA v3** | Невидимая капча при клике кнопки телефона | Проходит браузерным fingerprint; ожидание `grecaptcha` в `window` |
| **AccessToken / RefreshToken** | JWT в cookie `.tnet.ge`, TTL ~11 мин | Автоперелогин если остаток < 60с; cookie копируется на `www.myhome.ge` |

**Важно про AccessToken:** сессия сохраняется от `auth.myauto.ge`, cookie с доменом `.tnet.ge`. Для запросов к `www.myhome.ge/phone/show` нужна копия этого cookie с доменом `www.myhome.ge` — делается в `load_storage()` перед каждым лидом.

---

## 3. Технический поток

Для каждого лида выполняется изолированный цикл:

```
load_storage()          ← чтение сессии с диска, автоперелогин если токен < 60с
pkill -9 chromium       ← очистка zombie-процессов
sync_playwright()
  chromium.launch()     ← headless=True, stealth, proxy, --disable-blink-features
  new_context()         ← storage_state, Windows UA, locale
  new_page()
  Stealth().apply()
  page.goto(url, wait_until="domcontentloaded")
  wait_for_load_state("networkidle", timeout=10s)   ← ждём CF-JS
  проверка Cloudflare   ← "Just a moment" в title или "cf-challenge" в HTML
  dismiss_popup()       ← Escape + поиск крестика модала
  wait 3s
  _wait_for_phone_btn_and_recaptcha()   ← polling "text=ნომრის ნახვა" + grecaptcha ready
  click_show_phone()
    expect_response("phone/show", status in (200, 204))
    JS evaluate → раскрыть display:none у предков → el.click()
    200 → parse_phone_response()   ← JSON result/data/phone_number
    204 → body.inner_text() + regex +995…   ← номер в DOM после React
  repository.update_enriched_fields()
  context.storage_state() → save to disk   ← фиксируем обновлённый токен
browser.close()
pkill -9 chromium       ← очистка
os.waitpid(-1, WNOHANG) ← reaping зомби
time.sleep(2.0–4.0)     ← защита от CF rate-limit
```

---

## 4. Ключевые решения и баги

### 4.1 Per-lead browser isolation

**Проблема:** один browser на батч 50 лидов → накопление zombie chromium → OOM / exit 137.  
**Решение:** каждый лид — отдельный `sync_playwright()` + `browser`. ~60с/лид, зато стабильно.

### 4.2 Локатор кнопки

**Проблема:** `button:has(span:text("ნომრის ნახვა"))` — Playwright-специфичный синтаксис, падает в `querySelectorAll`. Кнопка — SPAN внутри DIV, не `<button>`.  
**Решение:** `page.locator("text=ნომრის ნახვა").first` — нативный text-локатор.

### 4.3 React hydration delay (4–9 сек)

**Проблема:** кнопка есть в DOM, но скрыта до завершения гидратации Next.js. `locator.click()` падал с "element is not visible".  
**Решение:** `wait_for(state="attached", timeout=30000)` — ждём появления в DOM, не видимости.

### 4.4 display:none у предков

**Проблема:** даже после гидратации `click()` падал — `display:none` у родительских элементов.  
**Решение:** JS evaluate раскрывает всю цепочку предков перед `el.click()`:

```js
let e = el;
while (e && e !== document.body) {
    if (getComputedStyle(e).display === 'none') e.style.display = 'block';
    if (getComputedStyle(e).visibility === 'hidden') e.style.visibility = 'visible';
    e = e.parentElement;
}
el.click();
```

### 4.5 HTTP 204 — No Content, номер в DOM

**Проблема:** API **`phone/show`** (tnet) отвечает **204** без тела; номер появляется в UI после React update. Фильтр **`status == 200`** не ловил ответ → таймаут **30 s** на лид.  
**Решение:** `"phone/show" in r.url and r.status in (200, 204)`; при **204** — **`page.locator("body").inner_text()`** и regex **`\+?995[\s\d]{9,14}`** → формат **`+995XXXXXXXXX`**; при **200** — **`parse_phone_response`**.

### 4.6 AccessToken TTL ~11 мин

**Проблема:** батч 50 лидов занимает ~50 мин. Токен истекал → 401/403 от phone/show.  
**Решение:**
1. `load_storage()` читает сессию с диска **перед каждым лидом**.
2. Декодирует JWT, проверяет `expires_at` — если остаток < 60с → `subprocess.run(myhome_login.py)`.
3. После лида `context.storage_state()` сохраняется на диск (JS страницы продлевает токен).

### 4.7 Cloudflare rate-limiting

**Проблема:** быстрая серия запросов → CF challenge. Проверка по `title` срабатывала, но CF иногда включался **после** `domcontentloaded`.  
**Решение:** `wait_for_load_state("networkidle", timeout=10s)` — CF-JS успевает выполниться. Плюс `random.uniform(2.0, 4.0)` пауза между лидами.

---

## 5. Конфигурация

| Переменная | Описание | Обязательна |
|---|---|---|
| `MYHOME_SESSION_PATH` | Путь к файлу сессии (`myhome_session.json`) | Да |
| `PLAYWRIGHT_PROXY_SERVER` | Адрес прокси, напр. `http://host:port` | Для обхода CF |
| `PLAYWRIGHT_PROXY_USER` | Логин прокси | При наличии auth |
| `PLAYWRIGHT_PROXY_PASS` | Пароль прокси | При наличии auth |

**Важно про Google bypass:** домены `*.google.com`, `*.gstatic.com`, `recaptcha.google.com` идут напрямую, минуя прокси (`--proxy-bypass-list`). Иначе reCAPTCHA v3 не загружается.

На сервере сессия лежит в `/data/adapter_sessions/myhome_session.json` (volume `playwright_sessions`).

---

## 6. Запуск и диагностика

**Обновить сессию (логин):**
```bash
curl -X POST http://localhost:8001/login \
  -H 'Content-Type: application/json' \
  -d '{"adapter": "myhome"}'
```

**Запустить обогащение:**
```bash
curl -X POST http://localhost:8001/enrich \
  -H 'Content-Type: application/json' \
  -d '{"phase": "phone", "adapter": "myhome", "limit": 50}'
```

**Прямой тест из контейнера (10 лидов):**
```bash
docker exec propradar-playwright-worker-1 timeout 300 python3 -c "
import sys, logging; sys.path.insert(0, '/app/src')
logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s %(message)s')
from config.settings import Settings
from parsers.adapters.myhome.phone import MyHomePhoneEnricher
from repositories.postgres_lead_repository import PostgresLeadRepository, PostgresSessionFactory
settings = Settings()
sessions = PostgresSessionFactory.from_database_url(str(settings.database_url))
repo = PostgresLeadRepository(sessions)
leads = repo.list_pending_phone_enrichment('myhome', limit=10)
e = MyHomePhoneEnricher(repo, headless=True, storage_state_path=settings.myhome_session_path)
r = e.enrich_leads(leads)
print('enriched=%d failed=%d' % (r.enriched, r.failed))
" 2>&1
```

**Логи воркера:**
```bash
docker logs propradar-playwright-worker-1 --tail 100 -f
```

**Скриншоты при ошибках:** `scripts/debug_screenshots/{lead_id}.png` внутри контейнера.

**Коды ошибок в `report.errors`:**

| Код | Причина |
|---|---|
| `CloudflareBlock` | CF challenge не прошёл (IP / fingerprint) |
| `TimeoutError` | Страница/кнопка не загрузилась за 30с |
| `phone_api_unauthorized` | HTTP 401 от phone/show — сессия истекла |
| `phone_api_http_NNN` | HTTP 4xx/5xx от phone/show |
| `phone_api_denied` | `result != true` в JSON ответа |
| `phone_api_empty` | Номер в ответе пустой |
| `phone_btn_digits_missing` | HTTP 204 и номер не найден в тексте страницы |

---

## 7. Результаты тестов

| Тест | Лидов | Результат | Причина потерь |
|---|---|---|---|
| Тест 1 | 3 | 2/3 | TimeoutError — просроченное объявление |
| Тест 2 | 10 | 9/10 | RuntimeError — снятое объявление |
| Тест 3 (старый код) | 50 | 19/50 (38%) | Токен истёк + CF-блокировки |
| Тест 4 (новый код) | 50 | 42/50 (84%) | CF rate-limit на 8 лидов |
| Тест 5 (retry 8) | 8 | 7/8 | 1 лид стабильно блокируется CF |
| **ИТОГО** | **50** | **49/50 (98%)** | ext=23971326 — стабильная CF-блокировка |

---

## 8. Бэклог

| Приоритет | Задача |
|---|---|
| **ВЫСОКИЙ** | `init: true` в `docker-compose.yml` для playwright-worker → tini/init как PID 1 автоматически reap-ает зомби. Текущий `pkill + waitpid` работает, но ненадёжен при краше Python. |
| **ВЫСОКИЙ** | n8n workflow/cron для автозапуска: `POST /login` → sleep 5с → `POST /enrich` (батч 50, раз в час с учётом TTL токена). |
| **СРЕДНИЙ** | Retry с экспоненциальным backoff для CF-заблокированных лидов (5 мин → 1 час → 1 день). |
| **СРЕДНИЙ** | Мониторинг success rate: метрика после каждого батча, алерт если `enriched/total < 80%`. |
| **СРЕДНИЙ** | Ротация прокси при росте объёма (500+ лидов/день). |
| **НИЗКИЙ** | Параллельная обработка: 2–3 worker с разными прокси + row-level locking в БД. |
| **НИЗКИЙ** | Проверить и задокументировать `phase=detail` и `phase=pdf`. |
| **НИЗКИЙ** | Ограничение памяти контейнера + рестарт после длинного батча. |

---

## 9. Почему HTTP не работает

- `www.myhome.ge` защищён **Cloudflare Managed Challenge**.
- Простые HTTP-клиенты (`httpx`, `curl`, `requests`) получают **403** или challenge-страницу с любого IP (проверено 2026-05-09: локально и с сервера).
- **Итог:** HTTP-путь не применяется; рабочий путь — **Playwright + авторизованная сессия**.

---

## 10. Историческая диагностика `__NEXT_DATA__`

Исследование 2026-05-09: проверялась гипотеза о доступности номера во встроенном JSON страницы (`__NEXT_DATA__` → `statement.comment`, regex `+995…`). Cloudflare в контролируемой среде воспроизвести не удалось.

Код `phone_extractor.py` и тесты **удалены** после отката. Канон — `docs/AI_GOVERNANCE.md` (§9) и `docs/INGRESS_ARCHITECTURE.md` — Playwright-only.

---

## 11. Оркестрация n8n

n8n вызывает `POST http://playwright-worker:8001/enrich` с `{"adapter":"myhome","phase":"phone","limit":50}` — ожидается **HTTP 202** (принятие задачи, не результат). Итог — в БД и логах контейнера. Автоматический workflow пока не настроен — см. бэклог.

---

## 12. См. также

- `src/parsers/adapters/myhome/phone.py` — `MyHomePhoneEnricher` (только Playwright).
- `src/parsers/adapters/myhome/constants.py` — BTN_SELECTORS, TW_MS, POPUP_CLOSE_SELECTORS.
- `src/parsers/adapters/myhome/browser.py` — `dismiss_popup`, `save_timeout_shot`.
- `docs/myhome_login.md` — сохранение сессии, SSO TNET.
- `docs/playwright_worker.md` — деплой воркера, профили Docker.
- `docs/INGRESS_ARCHITECTURE.md` — общая схема потока данных.
