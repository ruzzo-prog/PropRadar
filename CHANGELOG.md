# Changelog

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/).

## [Unreleased]

### Added

- Стартовый скелет приложения: `src/` (parsers, domain, repositories, services, api, config), `tests/`, `migrations/001_init_leads.sql`, `scripts/setup_venv.ps1`, Docker (`docker/infra`, `docker/tools`, `docker/app`), корневые `pyproject.toml`, `.env.example`, `.gitignore`, `.python-version`.
- Минимальный unit-тест `tests/unit/test_api_health.py` для `GET /health`.

### Changed

- Выравнивание конфигурации Cursor (`.cursor/rules`, `.cursor/agents`, `.cursor/skills`) под канон PropRadar (`Docs/AI_GOVERNANCE.md`): единые пути `Docs/PropRadar_STATUS.md`, `Docs/INGRESS_ARCHITECTURE.md`, `Docs/AI_GOVERNANCE.md`; удалены отсылки к чужому репозиторию `dispatch-backend`.
