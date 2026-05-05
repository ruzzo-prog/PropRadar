# PropRadar — статус проекта

Единственный источник оперативного статуса по `Docs/AI_GOVERNANCE.md` §8.

## 2026-05-05 — Закрытие задачи: Smoke PASS, контрольная точка 3

- **Контекст:** финальная проверка после цикла **006** / цены / очередь detail и backfill **`price_gel`**.
- **Проверка:** контрольная точка **3** — **PASS**; **Smoke** подтверждён человеком; для **20** лидов в выборке **`price_usd`** и **`price_gel`** заполнены корректно.
- **Финальный вердикт:** `@release-check` — **PASS**; деплой и smoke подтверждены человеком.
- **Статус:** задача **закрыта**.
- **Документация:** `CHANGELOG.md`, этот файл.

| Показатель | Статус |
|------------|--------|
| КТ3 | ✅ PASS |
| Smoke (ручной) | ✅ PASS |
| Выборка цен (20 лидов) | ✅ OK |
| Документация | 📜 обновлена |

```mermaid
flowchart LR
  KT3[КТ 3 PASS] --> S[Smoke PASS\nчеловек]
  S --> P["price_usd / price_gel\n20 лидов OK"]
  P --> X[Задача закрыта]
```

## 2026-05-05 — Backfill `price_gel` и очередь detail после миграции 006

- **Контекст:** после **`migrations/006_add_price_gel_rename_price_usd.sql`** в **leads-db** часть строк остаётся с **`price_gel = NULL`**; обогащение деталями должно снова подхватывать такие записи наряду с пустым адресом.
- **Сделано:** **`list_pending_detail_enrichment`** для **`source=myhome`**, **`status=new`**: **`address IS NULL OR price_gel IS NULL`**; скрипт **`scripts/backfill_price_gel.py`** — выборка только **`new`** с **`price_gel IS NULL`**, заполнение через тот же путь, что **Statements API** в enricher (**`--limit`**, 1–500).
- **Проверка:** **Scanner** — **PASS**; **`@tester`** — **PASS**.
- **Документация:** `CHANGELOG.md`, `README.md`, этот файл.
- **Релиз вручную:** после **006** при необходимости — `python scripts/backfill_price_gel.py` (доступны **DATABASE_URL** и API; PII не логировать).

| Показатель | Статус |
|------------|--------|
| Scanner | ✅ PASS |
| Unit / регрессия | 🧪 PASS (`@tester`) |
| Документация | 📜 обновлена |

```mermaid
flowchart LR
  M006[Миграция 006\nprice_gel / price_usd] --> Q[Detail-очередь\naddress NULL ∨ price_gel NULL]
  M006 --> B[backfill_price_gel.py\nnew + price_gel NULL]
  Q --> E[Enricher API detail]
  B --> E
  E --> DB[(leads-db)]
```

## 2026-05-05 — Ретро-фикс (закрытие замечаний Diff Check, P1 hotfix)

- **Контекст:** после **Diff Check** по горячему фиксу цен/описания оставались расхождения между артефактами репозитория и фактической схемой **`price_gel`** / **`price_usd`**.
- **Сделано:** в **`metabase/propradar_dashboard.json`** во всех SQL заменено **`price_total_usd`** → **`price_usd`**; в **`.gitignore`** добавлен игнор каталога **`data/myhome_pdf/`** (выгрузки PDF enricher не попадают в git); **`myhome_api_schema.csv`** выровнен под канон имён **`price_gel`** / **`price_usd`**.
- **Проверка:** `@tester` — **PASS** (подтверждено перед документированием); дальше — **@process-guard (Diff Check)** на полный diff.
- **Документация:** `CHANGELOG.md`, `docs/METABASE_SETUP.md`, при необходимости `README.md`, этот файл.

| Показатель | Статус |
|------------|--------|
| Unit | 🧪 PASS (по отчёту тестера) |
| Документация | 📜 обновлена |

```mermaid
flowchart LR
  DC[Diff Check замечания] --> M[Metabase JSON\nprice_usd]
  DC --> G[.gitignore\ndata/myhome_pdf/]
  DC --> C[CSV schema\nprice_gel / price_usd]
  M --> OK[Согласовано с БД 006]
  G --> OK
  C --> OK
```

## 2026-05-05 — P1 hotfix: `description` без HTML, `price_gel` / `price_usd`, миграция 006

- **Контекст:** после API-first — в **`description`** попадали HTML-фрагменты (например **`<br />`**); цены нужно хранить явно в **двух валютах** с переименованием устаревшей колонки.
- **Симптомы:** «грязный» текст описания в БД; путаница в именовании **`price_total_usd`** при фактической семантике USD из API.
- **Реализация:** очистка HTML при маппинге **`description`** из ответа API; колонка **`price_gel`** (GEL из **`price.1`**), **`price_usd`** (USD из **`price.2`**, ранее **`price_total_usd`**); миграция **`migrations/006_add_price_gel_rename_price_usd.sql`** (после **005**).
- **Проверка:** `@tester` — **PASS** (unit); интеграция к live API — **SKIP** по умолчанию (**`MYHOME_INTEGRATION=1`** — вручную при необходимости).
- **Документация:** `CHANGELOG.md`, `README.md` (список миграций), `docs/METABASE_SETUP.md` (заметка про SQL), этот файл.
- **Риски:** сохранённые в Metabase и прочие SQL, где фигурирует **`price_total_usd`**, нужно перевести на **`price_usd`**; при отчётах по цене в лари добавить **`price_gel`**.
- **Релиз вручную:** применить **006** к **leads-db** сразу после **005**; при уже развёрнутом дашборде — проверить native-вопросы (см. Metabase-док).

| Показатель | Статус |
|------------|--------|
| Unit | ✅ PASS |
| Integration | ⏭️ SKIP (по умолчанию) |
| Документация | 📜 обновлена |

```mermaid
flowchart LR
  API["Statements API\nprice.1 / price.2"] --> M[Маппинг]
  M --> G["price_gel"]
  M --> U["price_usd\n(было price_total_usd)"]
  HTML["HTML в тексте"] --> C[Очистка]
  C --> D["description"]
  G --> DB[(leads-db)]
  U --> DB
  D --> DB
```

## 2026-05-05 — myhome.ge: API-first адаптер, очереди detail/phone/pdf, миграция 005

- **Контекст:** домен [1] ПАРСИНГ — список и карточка **myhome** через **api-statements.tnet.ge**; телефон и PDF остаются на Playwright.
- **Реализация:** `src/parsers/adapters/myhome/myhome_api_schema.csv` (SoT полей); `parser.py`, `schema.py`, `enricher.py` (GET `/v1/statements/{id}`), `phone.py`, `pdf.py`; фасады `src/parsers/myhome.py`, `src/parsers/myhome_enricher.py`; `migrations/005_myhome_api_first.sql`; разделение очередей в `LeadRepository`; настройки PDF в `Settings` / `.env.example`; `scripts/run_myhome_enricher.py` (три фазы). Без правок `src/parsers/base.py`, `docker/`, `.cursor/`, governance кроме этого файла.
- **Проверка:** `@tester` — **PASS** (`ruff`, `mypy src`, `pytest` unit); интеграция к live API — **SKIP** без **`MYHOME_INTEGRATION=1`**; при **`MYHOME_INTEGRATION=1`** — smoke list + detail (см. README).
- **Документация:** `README.md`, `CHANGELOG.md`, этот файл.
- **Риски:** доступность и контракт **Statements API**; для телефона нужны валидная Playwright-сессия и обход **reCAPTCHA**; PDF пишется на диск под **`MYHOME_PDF_OUTPUT_DIR`** — контроль места и прав; без миграции **005** возможны ошибки из‑за расхождения кода enricher и схемы **leads-db**.
- **Релиз вручную:** применить **005** к **leads-db** после **004**; smoke `python scripts/run_myhome_enricher.py` при доступной БД и сети (PII не логировать); при необходимости live-проверки — `MYHOME_INTEGRATION=1 pytest tests/integration/test_myhome_integration.py`.

```mermaid
flowchart LR
  API["Statements API\nGET /v1/statements/{id}"] --> D[Очередь detail]
  D --> DB[(leads-db)]
  PW[Playwright] --> P[Очередь phone]
  PW --> F[Очередь pdf]
  P --> DB
  F --> DB
```

## 2026-05-05 — P1 hotfix: pending enrichment — учёт `phone=''`

- **Контекст:** emergency-path — enricher отдавал **`enriched=0`**, хотя в БД были лиды **new** без телефона.
- **Симптом:** очередь обогащения пустая при непустом наборе «новых» лидов.
- **Root cause:** отбор **pending enrichment** не учитывал **`phone`** как **пустую строку** (`''`), только **`NULL`**.
- **Фикс:** `list_pending_enrichment` для **new** выбирает **`phone IS NULL OR phone = ''`** (см. коммит **`8d347ce`**).
- **Scope:** код — коммит **`8d347ce`** (репозиторий/тесты); документация этой записи — **3** файла `.md`: **`docs/PropRadar_STATUS.md`**, **`CHANGELOG.md`**, **`README.md`**.
- **Проверка:** `@tester` — **PASS** (`pytest`, **`ruff`**); интеграция — **SKIP**; **`mypy`**: известный baseline в **`settings.py`** — **вне scope**.
- **Риски:** расширение выборки (лиды с намеренно пустым `phone` попадут в очередь чаще); семантика совпадает с «телефон ещё не получен».

```mermaid
flowchart LR
  N[Lead status=new] --> P{phone NULL или ''?}
  P -->|да| Q[pending enrichment]
  Q --> E[Enricher]
```

## 2026-05-05 — P1 hotfix: `tzdata` для `ZoneInfo` на Windows (Asia/Tbilisi)

- **Контекст:** emergency-path — при локальном запуске на **Windows** падала работа с часовыми поясами для обогащения myhome (**Asia/Tbilisi → UTC**).
- **Симптом:** ошибка при создании **`ZoneInfo("Asia/Tbilisi")`** / связанная трассировка из цепочки **`published_at`** (нет данных зоны в окружении).
- **Root cause:** в сборках Python под Windows полная IANA-база для **`zoneinfo`** не гарантирована «из коробки»; для переносимости нужен пакет **`tzdata`** (PEP 615).
- **Реализация (минимальный scope):** только **`pyproject.toml`** — добавлена зависимость **`tzdata`** в `[project].dependencies`. Код и миграции не менялись.
- **Проверка:** `@tester` — **PASS**. Валидация сценария: **`ZoneInfo("Asia/Tbilisi")`** успешно; **`python scripts/run_myhome_enricher.py`** завершается без ошибки (при прочих выполненных условиях среды).
- **Документация:** этот файл, **`CHANGELOG.md`**, **`README.md`** (кратко про Windows).
- **Релиз вручную:** после `git pull` — переустановить зависимости окружения (`pip install -e .` / эквивалент), чтобы подтянулся **`tzdata`**.

```mermaid
flowchart LR
  W[Windows Python] --> Z[zoneinfo.ZoneInfo]
  Z --> T["tzdata (IANA)"]
  T --> L["Asia/Tbilisi → UTC"]
```

## 2026-05-05 — myhome enricher: адаптеры, `*_lang`, `published_at` (Asia/Tbilisi → UTC), миграция 004

- **Контекст:** домен [1] ПАРСИНГ — уточнение обогащения myhome: вынесен адаптерный пакет, языковые метки текстовых полей, единые правила даты публикации с грузинской локалью, идемпотентные обновления в репозитории.
- **Реализация:** пакет `src/parsers/adapters/myhome/` (`enricher`, `extract`, `locale`, `published` и др.); фасад `src/parsers/myhome_enricher.py` сохранён для совместимости импортов. Миграция `migrations/004_add_text_lang_columns.sql`: колонки `address_lang`, `district_lang`, `description_lang` (VARCHAR(8)). Модель `Lead` и `PostgresLeadRepository`: поля `*_lang`, разбор `published_at` со страницы как локаль **Asia/Tbilisi** с сохранением в **UTC** (`parse_published_at_from_text`). Повторный прогон enricher не затирает уже заполненные значения теми же данными (идемпотентные апдейты на уровне репозитория).
- **Проверка:** `@tester` — PASS (по цепочке: Scanner PASS/SKIP, затем unit/регрессия согласно отчёту тестера). Ручной smoke: применить **004** к **leads-db**, сессия Playwright, `scripts/run_myhome_enricher.py`, сверка колонок `*_lang` и `published_at` (телефон и PII не логировать).
- **Документация:** `CHANGELOG.md`, `README.md`, этот файл.
- **Релиз вручную:** применить `migrations/004_add_text_lang_columns.sql` к **leads-db** после **003** (см. README, шаг локальной БД).

```mermaid
flowchart LR
  A[Страница объявления] --> B[adapters/myhome]
  B --> C["published_at (Tbilisi→UTC)"]
  B --> D["address/district/description + *_lang"]
  C --> E[(leads-db)]
  D --> E
```

## 2026-05-04 — myhome.ge: обогащение лидов (Playwright, телефон, детали)

- **Контекст:** домен [1] ПАРСИНГ — после списка API нужны телефон (reCAPTCHA v3 + сессия) и поля со страницы объявления в **leads-db**.
- **Реализация:** `migrations/003_add_lead_details.sql`; расширение `Lead`, порта `LeadRepository` (`list_pending_enrichment`, `update_enriched_fields`) и `PostgresLeadRepository`; `src/parsers/exceptions.py` (`SessionExpiredError`), `src/parsers/myhome_enricher.py`; `scripts/myhome_login.py`, `scripts/run_myhome_enricher.py`; `Settings` (`MYHOME_EMAIL`, `MYHOME_PASSWORD`, `MYHOME_SESSION_PATH`, `MYHOME_ENRICH_LIMIT`); `.gitignore` для `scripts/myhome_session.json`; unit-тесты `tests/unit/test_myhome_enricher.py`. Без правок `src/parsers/base.py`, `src/parsers/myhome.py`, `docker/`, `.cursor/`, governance-файлов.
- **Проверка:** `@tester`: `ruff check src tests scripts`, `mypy src`, `pytest tests/unit/` — PASS. Ручной smoke: применить `003_*`, `myhome_login.py`, `run_myhome_enricher.py` при доступной БД и сети; `playwright install chromium` при необходимости.
- **Документация:** `README.md`, `CHANGELOG.md`, этот файл.
- **Релиз вручную:** миграция **003** на существующую **leads-db**; сохранение сессии; прогон enricher и сверка колонок в БД (телефон и детали не логировать).

## 2026-05-04 — Metabase: скрипт API для дашборда «PropRadar — Лиды»

- **Контекст:** автоматическая настройка дашборда через **Metabase HTTP API** без ручной расстановки шести карточек; идемпотентность при уже созданном дашборде.
- **Реализация:** **`scripts/setup_metabase_dashboard.py`** (сессия, поиск БД **`LEADS_DATABASE_NAME`** / «PropRadar Leads», **`POST /api/card`**, **`POST /api/dashboard`**, раскладка **`POST .../cards`**), **`pyproject.toml`** (**`ruff`** включает **`scripts/`**), корневой **`.env.example`** (закомментированные **`METABASE_*`**). **`docs/METABASE_SETUP.md`** — раздел про автоматизацию. Остальные запреты scope (без правок **`src/`**, **`migrations/`**, **`docker/infra`**) соблюдены.
- **Проверка:** Scanner PASS (подтверждено человеком). `@tester`: **`ruff check src tests scripts`**, **`mypy src`**, **`pytest -m "not integration"`** — OK; **`docker compose config`** (infra/tools/app) — OK. Smoke против живого Metabase — вручную (**`METABASE_*`**).
- **Документация:** **`docs/METABASE_SETUP.md`**, **`CHANGELOG.md`**, **`README.md`**, этот файл.
- **Релиз вручную:** один прогон скрипта после настройки админа и подключения БД в UI.

## 2026-05-04 — Metabase: дашборд и подключение leads-db

- **Контекст:** наблюдаемость/монетизация — дашборд для агентств и внутреннего мониторинга; Metabase в **`docker/tools`**, порт хоста **3031**, сеть **`propradar`**.
- **Реализация:** правки **`docker/tools/docker-compose.yml`** (Metabase: `JAVA_TIMEZONE`/`TZ`), **`docker/tools/.env.example`** (блок **`LEADS_DB_*`** для формы в UI), **`metabase/propradar_dashboard.json`** (6 карточек, SQL под PG15 и миграции `001`+`002`), **`docs/METABASE_SETUP.md`** (шаги, DNS, ручная сборка дашборда из JSON). **`docker/infra`**, **`src/`**, **`migrations/`**, **`docs/AI_GOVERNANCE.md`** не менялись.
- **Проверка:** Scanner PASS (подтверждено человеком). `@tester`: валидность JSON, `docker compose config` для **infra/tools/app** — OK; `ruff`/`mypy`/`pytest` ( регрессия кода) — OK. Ручной smoke: `up tools` и UI **http://localhost:3031** — по **`METABASE_SETUP.md`**.
- **Документация:** `docs/METABASE_SETUP.md`, `CHANGELOG.md`, этот файл.
- **Релиз вручную:** поднять infra + tools, подключить БД **leads** в Metabase, собрать дашборд по SQL из JSON.

## 2026-05-04 — Парсер myhome.ge (HTTP API, leads-db)

- **Контекст:** первый рабочий адаптер домена «Парсинг»; запуск по расписанию n8n, запись только новых объявлений в **leads-db** через **LeadRepository**; телефон/reCAPTCHA вне scope.
- **Реализация:** `src/parsers/myhome.py` (`MyHomeParser`), `PostgresLeadRepository` и `PostgresSessionFactory`, расширение `Lead` + `migrations/002_add_myhome_listing_fields.sql`, `scripts/run_myhome_parser.py` (JSON `parsed` / `new` / `errors`, коды выхода 0/1, `SELECT 1` до HTTP), `Settings.myhome_api_base_url`, unit-тесты парсера, интеграционный тест с маркером `@pytest.mark.integration`. Файлы в `docs/`, `docker/`, `.cursor/` и контракт `BaseParser` не менялись.
- **Проверка:** Scanner PASS (подтверждено человеком). `@tester`: `ruff check src tests`, `mypy src`, `pytest -m "not integration"` — PASS; интеграция к API при `MYHOME_INTEGRATION=1` — вручную/offline по умолчанию **SKIP**; `docker compose config` (infra/tools/app) — exit 0.
- **Документация:** `README.md` (миграции 002 и скрипт), `CHANGELOG.md`, этот файл.
- **Релиз вручную:** применить `002_*` к существующей БД; smoke `python scripts/run_myhome_parser.py` при доступном `DATABASE_URL` и сети.

## 2026-05-04 — Скелет приложения (src, Docker, миграции)

- **Контекст:** после Plan Check и реализации `@review` добавлен стартовый каркас репозитория без бизнес-логики парсеров; цель — подготовка к разработке парсера myhome.ge.
- **Реализация:** дерево `src/` (parsers `BaseParser`, domain `Lead`/`LeadStatus`/`Score`, repositories, services, FastAPI `/health`, `Settings`), `tests/`, `migrations/001_init_leads.sql`, `scripts/setup_venv.ps1`, `docker/{infra,tools,app}` с сетью `propradar`, порты хоста: leads-db **5433**, n8n **5678**, Metabase **3031**, Evolution **8080**, API **8000**; корневые `pyproject.toml`, `.env.example`, `.gitignore`, `.python-version`. Канон в `docs/` и `.cursor/` не менялись.
- **Проверка:** Scanner PASS (подтверждено человеком). `@tester`: `pytest tests/unit` (в т.ч. `test_api_health`), `ruff check src tests`, `mypy src`, `docker compose config` для трёх compose — успешно. Integration/E2E с поднятой БД и полным стеком в этой итерации не автоматизировались.
- **Документация:** `README.md`, `CHANGELOG.md` (в т.ч. строка про unit-тест `/health`), этот файл.
- **Релиз вручную:** при первом деплоне — создать сеть `docker network create propradar`, поднять `docker/infra`, применить SQL к `leads-db`, smoke `GET /health` на API.

## 2026-05-04 — Выравнивание `.cursor/` под PropRadar

- **Контекст:** после Plan Check выполнена реализация Fix Plan: агенты и skills в `.cursor/` синхронизированы с `Docs/AI_GOVERNANCE.md` v1.0; убрано наследие `dispatch-backend` / `DISPATCH_STATUS` / чужих продуктовых шаблонов.
- **Реализация:** обновлены `Rules-for-AI.mdc`, все `agents/*.mdc` по scope плана, skills (`dispatcher-chain-coordinator`, `documentor-doc-style`, `release-check`, `engineer-repairman-emergency-hotfix-report`, `architect-fix-plan-audit`).
- **Проверка:** grep по `.cursor/` — нет `dispatch-backend`, `DISPATCH_STATUS`, `usluga-market`, «Диспетчерская»; целевые пути доков — `Docs/…`. Сканер кода для чисто конфигурационного diff не требовался (docs-only / `.cursor`).
- **Документация:** этот файл; добавлен корневой `CHANGELOG.md` (первая запись).
- **Релиз вручную:** не применимо (нет деплоя кода).

## Бэклог

- Унифицировать в тексте `Docs/AI_GOVERNANCE.md` обозначение папки `docs/` vs фактическая `Docs/` на диске (отдельная задача вне последнего Fix Plan).

## Технический долг

- `Docs/INGRESS_ARCHITECTURE.md` — заготовка пустая; заполнить перед первым ingress-изменением в коде.

## ENV

_(раздел заполняется при появлении деплой-канона и секретов; не хранить значения в репозитории.)_
