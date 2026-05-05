# Changelog

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/).

## [Unreleased]

### Verified

- **Leads client v2 / миграция 008:** пересоздание **`leads_client`** под контракт **v2**; **Scanner** — **PASS**; **`@tester`** — **PASS**.
- **Myhome / цены (закрытие цикла):** контрольная точка **3** — **PASS**; **Smoke** подтверждён человеком; для **20** лидов **`price_usd`** и **`price_gel`** совпадают с ожиданием; задача закрыта.
- **Chain completion:** финальный `@release-check` — **PASS**; ручной smoke после деплоя подтверждён человеком.
- **Leads client / финальная проверка:** контрольная точка **3** — **PASS**; Smoke подтверждён человеком; `leads_client` создана и синхронизируется через trigger, готово к финальному деплою.

### Fixed

- **P1 / Metabase (карточка 7, колонки города и владельца):** в **`metabase/propradar_dashboard.json`** для позиции **7** колонка **«Город»** переведена на **`city_name`** (вместо **`urban_name`**); добавлен **`owner_name`** (**«Имя владельца»**) (@tester **PASS**).
- **P1 / Metabase (карточка 7 «Последние лиды»):** в **`metabase/propradar_dashboard.json`** SQL позиции **7** выводит только **клиентские** столбцы **`leads_client`**; убраны **`lead_id`** и служебные/технические поля из представления таблицы (@tester **PASS**).
- **P1 / Metabase (KeyError):** **`title_ru`** скаляра USD в **`metabase/propradar_dashboard.json`** синхронизирован со скриптом **`scripts/setup_metabase_dashboard.py`** (**`Средняя цена объекта (USD)`**); устранено падение при автосборке дашборда (@tester **PASS**).
- **Ретро после P1 hotfix (Diff Check):** в **`metabase/propradar_dashboard.json`** SQL переведены с **`price_total_usd`** на **`price_usd`**; **`data/myhome_pdf/`** в **`.gitignore`** (PDF enricher не коммитятся); **`src/parsers/adapters/myhome/myhome_api_schema.csv`** согласован с **`price_gel`** / **`price_usd`** (@tester **PASS**).
- **Myhome / `description`:** при маппинге из API удаляются HTML-теги (в т.ч. **`<br />`**), чтобы в **leads-db** сохранялся обычный текст (@tester: unit **PASS**, интеграция **SKIP**).
- **Leads / цены:** добавлена колонка **`price_gel`**, колонка **`price_total_usd`** переименована в **`price_usd`**; миграция **`migrations/006_add_price_gel_rename_price_usd.sql`** (применять после **005**). В Metabase и сохранённых SQL заменить обращения к **`price_total_usd`** на **`price_usd`**.
- **Pending enrichment / `phone`:** `list_pending_enrichment` для лидов **new** учитывает **`phone IS NULL OR phone = ''`**, чтобы пустая строка не исключала запись из очереди и enricher не завершался с **`enriched=0`** при наличии кандидатов; реализация — коммит **`8d347ce`** (@tester: `pytest`/`ruff` PASS, интеграция skipped).
- **Windows / `zoneinfo`:** добавлена зависимость **`tzdata`** в **`pyproject.toml`**, чтобы **`ZoneInfo("Asia/Tbilisi")`** и пайплайн даты публикации myhome не падали на Windows без системной IANA-базы; проверено: **`ZoneInfo`** OK и **`scripts/run_myhome_enricher.py`** без ошибки (@tester PASS).

### Changed

- **Проекция `leads_client` v2:** миграция **`migrations/008_recreate_leads_client_v2.sql`** (после **007**) — пересоздание таблицы; **PK `(source, external_id)`**; **26** столбцов; без **`lead_id`**, **`source_listing_uuid`**, языковых **`*_lang`**; триггер/функция синхронизации с **`leads`** сохранены по смыслу (см. SQL). Bundle **`metabase/propradar_dashboard.json`**: **`schema_reference`** и native-SQL выровнены под **008** (Scanner **PASS**, `@tester` **PASS**).
- **Metabase / bundle `metabase/propradar_dashboard.json`:** все native-SQL карточки переведены на таблицу **`leads_client`**; обновлены **«Последние лиды»** (столбцы и сортировка по **`COALESCE(published_at, synced_at)`**); добавлены/уточнены скаляры **средней цены USD** и **GEL** (`ROUND(AVG(...), 2)` по **`price_usd`** / **`price_gel`**); в JSON — **`schema_reference`** (эволюция **007** → актуальный контракт **008**) и **`operator_instructions_ru`** для высоты карточки и прокрутки таблицы в UI Metabase (Scanner **PASS**, `@tester` **PASS**).
- **Myhome / detail-очередь:** `list_pending_detail_enrichment` для **`source=myhome`**, **`status=new`** — условие **`address IS NULL OR price_gel IS NULL`**, чтобы после миграции **006** снова обрабатывались лиды без **`price_gel`** (Scanner **PASS**, @tester **PASS**).
- **Myhome обогащение (архитектура):** поля карточки снимаются с **Statements API** (**`GET /v1/statements/{id}`**, см. **`myhome_api_schema.csv`**); телефон (**`phone/show`**) и PDF (**`page.pdf()`**) остаются на Playwright; очереди в БД разделены на **detail** / **phone** / **pdf** (миграция **`005_myhome_api_first.sql`**).
- Enricher и репозиторий: идемпотентные обновления при повторном обогащении (не перезаписывать уже совпадающие значения).
- Разбор `published_at` с текста страницы: интерпретация в **Asia/Tbilisi**, хранение **UTC** (`parse_published_at_from_text`).
- Парсер списка myhome (`published_at` из API): нормализация к **UTC** для согласованности с enricher.
- Выравнивание конфигурации Cursor (`.cursor/rules`, `.cursor/agents`, `.cursor/skills`) под канон PropRadar (`Docs/AI_GOVERNANCE.md`): единые пути `Docs/PropRadar_STATUS.md`, `Docs/INGRESS_ARCHITECTURE.md`, `Docs/AI_GOVERNANCE.md`; удалены отсылки к чужому репозиторию `dispatch-backend`.

### Added

- **`leads_client` / миграция 009:** колонки **`city_name`** и **`owner_name`** в проекции; backfill и синхронизация из **`leads.myhome_statement_json`** по ключам **`city_name`** / **`owner_name`** (соединение **`(source, external_id)`**); **`sync_leads_client_from_lead`** — маппинг в **INSERT** и **ON CONFLICT DO UPDATE**; источник — только JSON statement (**не** **`leads.city_name`**). Файл: **`migrations/009_add_city_name_to_leads_client.sql`** (после **008**).

- **Проекция `leads_client`:** таблица денормализованного представления **`leads`** для клиентских выборок; миграция **`migrations/007_create_leads_client_table.sql`** (после **006**): функция **`sync_leads_client_from_lead`**, триггер **`trg_leads_sync_client`** на **`leads`** (**INSERT**/**UPDATE**), индексы на **`external_id`** и **`district_name`**, начальное заполнение из **`leads`** (Scanner **PASS**, @tester **PASS**).
- **`scripts/backfill_price_gel.py`** — backfill **`price_gel`** для myhome: только **`status=new`** и **`price_gel IS NULL`**, тот же HTTP-путь, что у enricher (**`GET /v1/statements/{id}`**), параметр **`--limit`** (Scanner **PASS**, @tester **PASS**).
- Myhome **API-first** и enricher: канон полей **`src/parsers/adapters/myhome/myhome_api_schema.csv`**; пакет **`src/parsers/adapters/myhome/`** (`parser.py`, `schema.py`, `enricher.py` с HTTP-деталями, `phone.py`, `pdf.py`, извлечение полей, локаль страницы, разбор даты публикации); фасады **`src/parsers/myhome.py`**, **`src/parsers/myhome_enricher.py`** (реэкспорт публичного API); миграция **`005_myhome_api_first.sql`**; очереди **`list_pending_detail_enrichment`** / **`list_pending_phone_enrichment`** / **`list_pending_pdf_enrichment`**; колонки **`geo_lat`**, **`geo_lng`**, **`listing_views`**, **`myhome_statement_json`**, **`pdf_url`**.
- Миграция `migrations/004_add_text_lang_columns.sql`: колонки `address_lang`, `district_lang`, `description_lang` в `leads`.
- Стартовый скелет приложения: `src/` (parsers, domain, repositories, services, api, config), `tests/`, `migrations/001_init_leads.sql`, `scripts/setup_venv.ps1`, Docker (`docker/infra`, `docker/tools`, `docker/app`), корневые `pyproject.toml`, `.env.example`, `.gitignore`, `.python-version`.
- Metabase: **`docker/tools`** (таймзона UTC), **`metabase/propradar_dashboard.json`**, **`docs/METABASE_SETUP.md`**, переменные **`LEADS_DB_*`** в **`docker/tools/.env.example`**; скрипт **`scripts/setup_metabase_dashboard.py`** (API: дашборд «PropRadar — Лиды», идемпотентность); **`ruff`** охватывает **`scripts/`**.
- Парсер **myhome.ge**: `src/parsers/myhome.py`, `PostgresLeadRepository`, `migrations/002_add_myhome_listing_fields.sql`, `scripts/run_myhome_parser.py`, unit- и integration-тесты (`MYHOME_INTEGRATION=1` для live API); настройка `MYHOME_API_BASE_URL`.
- Обогащение **myhome.ge**: `migrations/003_add_lead_details.sql`, `src/parsers/myhome_enricher.py`, `src/parsers/exceptions.py`, расширение `Lead` и `LeadRepository`, `scripts/myhome_login.py`, `scripts/run_myhome_enricher.py`, unit-тесты `tests/unit/test_myhome_enricher.py`; сессия Playwright в `scripts/myhome_session.json` (в `.gitignore`).
- Минимальный unit-тест `tests/unit/test_api_health.py` для `GET /health`.
