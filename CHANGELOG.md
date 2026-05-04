# Changelog

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/).

## [Unreleased]

### Added

- Стартовый скелет приложения: `src/` (parsers, domain, repositories, services, api, config), `tests/`, `migrations/001_init_leads.sql`, `scripts/setup_venv.ps1`, Docker (`docker/infra`, `docker/tools`, `docker/app`), корневые `pyproject.toml`, `.env.example`, `.gitignore`, `.python-version`.
- Metabase: **`docker/tools`** (таймзона UTC), **`metabase/propradar_dashboard.json`**, **`docs/METABASE_SETUP.md`**, переменные **`LEADS_DB_*`** в **`docker/tools/.env.example`**; скрипт **`scripts/setup_metabase_dashboard.py`** (API: дашборд «PropRadar — Лиды», идемпотентность); **`ruff`** охватывает **`scripts/`**.
- Парсер **myhome.ge**: `src/parsers/myhome.py`, `PostgresLeadRepository`, `migrations/002_add_myhome_listing_fields.sql`, `scripts/run_myhome_parser.py`, unit- и integration-тесты (`MYHOME_INTEGRATION=1` для live API); настройка `MYHOME_API_BASE_URL`.
- Обогащение **myhome.ge**: `migrations/003_add_lead_details.sql`, `src/parsers/myhome_enricher.py`, `src/parsers/exceptions.py`, расширение `Lead` и `LeadRepository`, `scripts/myhome_login.py`, `scripts/run_myhome_enricher.py`, unit-тесты `tests/unit/test_myhome_enricher.py`; сессия Playwright в `scripts/myhome_session.json` (в `.gitignore`).
- Минимальный unit-тест `tests/unit/test_api_health.py` для `GET /health`.

### Changed

- Выравнивание конфигурации Cursor (`.cursor/rules`, `.cursor/agents`, `.cursor/skills`) под канон PropRadar (`Docs/AI_GOVERNANCE.md`): единые пути `Docs/PropRadar_STATUS.md`, `Docs/INGRESS_ARCHITECTURE.md`, `Docs/AI_GOVERNANCE.md`; удалены отсылки к чужому репозиторию `dispatch-backend`.
