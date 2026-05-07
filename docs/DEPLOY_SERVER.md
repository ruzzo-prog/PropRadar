# Деплой на сервер (PropRadar)

Канон по маршрутизации и границам ответственности — `docs/INGRESS_ARCHITECTURE.md` (если расходится с этим runbook, приоритет у канона). Здесь — практические шаги для хоста с Docker.

## Локальный workflow (обязательный)

1. **Windows / локальная разработка и тесты:** клон репозитория, `scripts/setup_venv.ps1`, копируете в корень `.env` содержимое `.env.example.local` (или `.env.example` как базу для хоста), поднимаете `docker/infra` (PostgreSQL на `localhost:5433`), при необходимости `docker/tools` (n8n, Metabase **3031**, Evolution). API для разработки на хосте: `uvicorn api.main:app --reload --host 127.0.0.1 --port 9000` (порт **9000** — локальный профиль; в Docker контейнер `api` слушает **8000**, с хоста доступен как **8000**).
2. **Фиксация изменений:** `git push` в основную ветку (или ветку деплоя по вашему процессу).
3. **Сервер:** `git pull` в каталоге проекта.
4. **Запуск стеков:** создать сеть при необходимости `docker network create propradar`, затем из **корня репозитория** `docker compose --profile … up -d` (см. `compose.yaml` и раздел ниже); либо по отдельности фрагменты в `docker/infra`, `docker/tools`, `docker/app`, при публичных n8n/Evolution — `docker/reverse-proxy` (TLS). Точные команды см. ниже.

## Порты (согласованная матрица)

| Назначение | Где | Порт |
|------------|-----|------|
| API через Docker (хост → контейнер) | `docker/app` | **8000** |
| API внутри сети `propradar` | hostname `api` | **8000** (`http://api:8000`) |
| Локальный uvicorn на Windows/хосте | вручную | **9000** |
| PostgreSQL leads-db (хост, локальная разработка) | `docker/infra` | **5433** → 5432 |
| Metabase UI | `docker/tools` | **3031** → 3000 |
| n8n (слушает в контейнере; **на хост не проброшен**) | `docker/tools` | **5678** (только внутри `propradar`) |
| Evolution API (аналогично) | `docker/tools` | **8080** (только внутри `propradar`) |
| Reverse-proxy HTTP/HTTPS | `docker/reverse-proxy` | 80, 443 |

Публичный доступ к n8n и Evolution на сервере — через **HTTPS** на **`docker/reverse-proxy`** (домены и TLS — см. `docker/reverse-proxy/README.md`, переменные **`N8N_TLS_*`** / **`EVOLUTION_TLS_*`** и preflight перед стартом nginx).

## Переменные окружения: local vs server

- **Локально (хост подключается к БД):** `DATABASE_URL=postgresql://USER:PASS@localhost:5433/DB` — шаблон в `.env.example.local` и корневом `.env.example`.
- **На сервере (контейнеры приложения):** `DATABASE_URL=postgresql://USER:PASS@leads-db:5432/DB` — шаблон в `.env.example.server`, `docker/app/.env.example`, `docker/infra/.env.example`.

Синхронизируйте `POSTGRES_*` и учётные данные в URL между `docker/infra` и приложениями.

## Безопасность PostgreSQL (без «5433 в мир»)

- **Не открывайте** порт leads-db на `0.0.0.0` в проде. Предпочтительно: привязка только к loopback, например в override или правке `ports` у `leads-db`: `127.0.0.1:5433:5432`, либо убрать публикацию порта и работать только из контейнеров сети `propradar`.
- **Временное подключение локального Playwright enricher к серверной БД** — только через один из вариантов:
  - **SSH-туннель** (типично): с рабочей машины `ssh -L 5433:127.0.0.1:5433 user@server` при условии, что на сервере Postgres слушает `127.0.0.1:5433` или 5432 через проброс только на loopback. Локально в `.env`: `DATABASE_URL=...@localhost:5433/...`.
  - **Корпоративный VPN** + доступ к внутреннему хосту/порту по политике сети.
  - **Allowlist на файрволе** для вашего статического IP — узкое правило, не полная публикация порта.

После отладки туннель закрыть, учётки/пароли при необходимости сменить.

## Типовой порядок compose на сервере

**Рекомендуемый способ (единый project directory и `./.env` в корне репозитория):** файл **`compose.yaml`** в корне включает фрагменты `docker/infra`, `docker/app`, `docker/tools`, `docker/reverse-proxy`. Сервисы отнесены к **профилям** (`infra`, `app`, `tools`, `proxy`), чтобы поднимать только нужное.

Из корня репозитория (перед первым запуском скопируйте или объедините переменные в **корневой** `.env` по шаблону `.env.example` / `.env.example.server`; контейнер **`api`** читает **`../../.env`** относительно `docker/app/docker-compose.yml`, то есть **тот же корневой файл**):

```bash
docker network create propradar 2>/dev/null || true

# Минимум для API + PostgreSQL (типичный сервер приложения):
docker compose --profile infra --profile app up -d

# Дополнительно инструменты (n8n, Metabase, Evolution):
docker compose --profile tools up -d

# TLS / nginx для публичных n8n и Evolution (после сертификатов):
docker compose --profile proxy up -d
```

Миграция с прежней схемы (`docker/app/.env` только в подкаталоге): положите секреты в **корневой** `.env` (например `cp docker/app/.env .env` или симлинк), затем пересоздайте контейнеры.

**Устаревший вариант** (отдельные `cd` по каталогам и merge `-f`) оставлен для совместимости в комментариях к фрагментам; для предсказуемого `DATABASE_URL` предпочтительнее команды выше из корня.

Проверка: `docker compose --profile infra --profile app ps`, логи сервиса `api`, `docker exec <container-api> env | grep DATABASE_URL`, `curl -s http://127.0.0.1:8000/health` на сервере (если проброшен 8000 только на localhost — так и задумано для внешнего доступа; снаружи API по умолчанию не публикуется). Имя проекта Compose по умолчанию — **`propradar`** (префикс контейнеров может отличаться от старых запусков из `docker/infra`).

## Reverse-proxy и TLS

См. `docker/reverse-proxy/README.md`: параметризованные file-mount сертификатов, preflight (`-f` / читаемость PEM), явный запуск скрипта через `sh`. API за прокси по умолчанию не выводится; n8n вызывает `http://api:8000` внутри Docker.

## Healthchecks

`leads-db` и `api` используют healthcheck в compose; `api` ждёт `service_healthy` для `leads-db` при совместном запуске с `docker/infra`.
