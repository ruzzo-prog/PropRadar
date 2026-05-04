# PropRadar

Автоматизированная система генерации лидов с рынка недвижимости Грузии.

Система парсит объявления от частных продавцов, устанавливает контакт через WhatsApp,
собирает структурированные данные и передаёт готовые лиды агентствам недвижимости.

---

## Пайплайн

```
[1] Парсинг          — мониторинг объявлений (myhome.ge, SS.ge)
        ↓
[2] Фильтрация       — скоринг, отсев агентств, дедупликация
        ↓
[3] Коммуникация     — WhatsApp-бот: согласие → сбор данных
        ↓
[4] Монетизация      — передача агентствам, трекинг сделок
```

---

## Стек


| Слой        | Технология                                                     |
| ----------- | -------------------------------------------------------------- |
| Парсинг     | Python + Playwright                                            |
| База данных | PostgreSQL (`leads-db`, порт 5433)                             |
| WhatsApp    | Evolution API (Docker, self-hosted)                            |
| Оркестрация | n8n (self-hosted)                                              |
| Дашборд     | Metabase (Docker, порт **3031** локально — см. `docker/tools`) |


---

## Структура репозитория

```
PropRadar/
├── .cursor/                  # AI-агенты и правила
├── docs/                     # Канонические документы
├── src/                      # Python-пакеты: api, config, domain, parsers, repositories, services
├── tests/                    # unit / integration / e2e (каркас)
├── migrations/               # SQL-миграции (leads-db)
├── scripts/                  # setup_venv.ps1 и др.
├── docker/
│   ├── infra/                # PostgreSQL 15 (leads-db, хост-порт 5433)
│   ├── tools/                # n8n, Metabase:3031, Evolution API:8080
│   └── app/                  # Каркас parsers + FastAPI API:8000
├── pyproject.toml
├── CHANGELOG.md
└── README.md
```

### Локальная среда (кратко)

1. Сеть Docker (один раз): `docker network create propradar`
2. БД: из `docker/infra` поднять `leads-db`, затем применить `migrations/001_init_leads.sql` и `migrations/002_add_myhome_listing_fields.sql` к БД на `localhost:5433`.
3. Python: `powershell -ExecutionPolicy Bypass -File .\scripts\setup_venv.ps1`, затем из корня с активированным venv: `uvicorn api.main:app --reload --host 127.0.0.1 --port 8000`.
4. Инструменты (опционально): `docker/tools` — n8n **5678**, Metabase **3031**, Evolution **8080**. Не смешивать с чужими проектами; БД проекта только **leads-db**, не `dispatch-db-dev`.
5. Парсер myhome (точка входа n8n): `python scripts/run_myhome_parser.py` — JSON-отчёт в stdout; интеграционный smoke к API: `MYHOME_INTEGRATION=1 pytest tests/integration/test_myhome_integration.py`.

Проверка compose: `docker compose -f docker/infra/docker-compose.yml config` (аналогично для `docker/tools` и `docker/app`).

---

## Источники данных

- **myhome.ge** — REST API (`api-statements.tnet.ge`), заголовок `X-Website-Key: myhome`
- **SS.ge** — Playwright (JavaScript-рендеринг, телефон за reCAPTCHA v3)

---

## Процесс разработки

Все изменения — только через цепочку AI-агентов по `docs/AI_GOVERNANCE.md`.

Три точки контроля человека:

1. Одобрение Fix Plan
2. Деплой
3. Smoke-тест

Подробнее: `[docs/AI_GOVERNANCE.md](docs/AI_GOVERNANCE.md)`

---

## Статус

Актуальный статус проекта: `[docs/PropRadar_STATUS.md](docs/PropRadar_STATUS.md)`