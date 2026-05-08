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
| Redis (`propradar-redis`) | `docker/infra` | не публикован на хост, только **`propradar`** |
| Metabase UI | `docker/tools` | **3031** → 3000 |
| n8n (слушает в контейнере; **на хост не проброшен**) | `docker/tools` | **5678** (только внутри `propradar`) |
| Evolution API (аналогично) | `docker/tools` | **8080** (только внутри `propradar`) |
| Reverse-proxy HTTP/HTTPS | `docker/reverse-proxy` | 80, 443 |

Публичный доступ к n8n и Evolution на сервере — через **HTTPS** на **`docker/reverse-proxy`** (домены и TLS — см. `docker/reverse-proxy/README.md`, переменные **`N8N_TLS_*`** / **`EVOLUTION_TLS_*`** и preflight перед стартом nginx).

## Redis и Evolution API

- Сервис **Redis** — во фрагменте **`docker/infra`** (**`propradar-redis`**, образ **`redis:7.4.9-alpine`**), только внутренний доступ по Docker-сети; наружу порт не открывается.
- По умолчанию в **`docker/tools/.env.example`** для Evolution задано **`CACHE_REDIS_ENABLED=false`**: можно поднимать только **`--profile tools`** без Redis — контейнер **не ждёт** недоступный Redis.
- Чтобы использовать Redis-кэш Evolution (**`CACHE_REDIS_ENABLED=true`**), поднимайте **одновременно** **`--profile infra`** и **`--profile tools`** из корня (**один** `compose.yaml`, сеть **`propradar`**), параметры см. **`docker/tools/.env.example`** (**`CACHE_REDIS_URI`** обычно **`redis://propradar-redis:6379`**).
- Compose **не** связывает **`depends_on`** между **`tools`** и **`infra`** для этого сценария; готовность Redis обеспечивается скриптом ожидания в **`command`** сервиса **`evolution-api`** при включённом кэше.

## Корневой `.env` и шаблоны

- От корня репозитория: **`cp .env.example .env`**, затем подставьте секреты и URL (**не коммитить** боевые значения). Сервер может дополняться шаблоном **`.env.example.server`** (см. комментарии в репозитории).
- В одном **`./.env`** собраны переменные для всех включаемых профилей (`infra`, `app`, **`tools`** с n8n/Metabase/Evolution, при необходимости `proxy` и др.); Compose читает этот файл из каталога проекта (**корень** репозитория).
- Переменные Evolution продублированы во **`docker/tools/.env.example`** для ориентира при profile **`tools`**; набор ключей блока Evolution **должен совпадать** с корневым **`.env.example`**.

После изменения переменных пересоздайте затронутые сервисы (`docker compose … up -d … --force-recreate` точечно).

## Переменные окружения: local vs server

- **Локально (хост подключается к БД):** `DATABASE_URL=postgresql://USER:PASS@localhost:5433/DB` — шаблон в `.env.example.local` и корневом `.env.example`.
- **На сервере (контейнеры приложения):** `DATABASE_URL=postgresql://USER:PASS@leads-db:5432/DB` — шаблон в `.env.example.server`, `docker/app/.env.example`, `docker/infra/.env.example`.

Синхронизируйте `POSTGRES_*` и учётные данные в URL между `docker/infra` и приложениями.

## Секреты playwright-worker

Сервис **`playwright-worker`** (профили **`enricher`** / **`workers`**, см. `docker/app/docker-compose.yml`) читает **тот же корневой** `.env`, что и **`api`**: путь **`env_file`** — **`../../.env`** относительно фрагмента приложения, на сервере это обычно каталог репозитория, например **`/srv/propradar/.env`**.

**Обязательно для автологина myhome и последующего парсинга телефонов:**

- **`MYHOME_EMAIL`** — учётная запись на сайте (плейсхолдеры см. `.env.example` и `docker/app/.env.example`).
- **`MYHOME_PASSWORD`** — пароль (реальные значения только на сервере; в репозиторий не коммитить).

Без них контейнер обычно остаётся **healthy**, но **`POST /login`** не сможет создать storage state, и цепочка обогащения телефонов не заработает. После добавления переменных в корневой `.env` пересоздайте контейнер **`playwright-worker`** (например `docker compose … up -d playwright-worker --force-recreate`), чтобы процесс увидел новое окружение.

## Безопасность PostgreSQL (без «5433 в мир»)

- **Не открывайте** порт leads-db на `0.0.0.0` в проде. Предпочтительно: привязка только к loopback, например в override или правке `ports` у `leads-db`: `127.0.0.1:5433:5432`, либо убрать публикацию порта и работать только из контейнеров сети `propradar`.
- **Временное подключение локального Playwright enricher к серверной БД** — только через один из вариантов:
  - **SSH-туннель** (типично): с рабочей машины `ssh -L 5433:127.0.0.1:5433 user@server` при условии, что на сервере Postgres слушает `127.0.0.1:5433` или 5432 через проброс только на loopback. Локально в `.env`: `DATABASE_URL=...@localhost:5433/...`.
  - **Корпоративный VPN** + доступ к внутреннему хосту/порту по политике сети.
  - **Allowlist на файрволе** для вашего статического IP — узкое правило, не полная публикация порта.

После отладки туннель закрыть, учётки/пароли при необходимости сменить.

## Типовой порядок compose на сервере

**Рекомендуемый способ (единый project directory и `./.env` в корне репозитория):** файл **`compose.yaml`** в корне включает фрагменты `docker/infra`, `docker/app`, `docker/tools`, `docker/reverse-proxy`. Сервисы отнесены к **профилям** (`infra`, `app`, `tools`, `proxy`), чтобы поднимать только нужное.

Из корня репозитория (перед первым запуском: **`cp .env.example .env`**, объедините при необходимости с `.env.example.server`, заполните секреты; контейнер **`api`** читает **`../../.env`** относительно `docker/app/docker-compose.yml`, то есть **тот же корневой файл**).

Образ Evolution API собирается из **`docker/tools/evolution-api.Dockerfile`** (Chromium для Puppeteer). Во фрагменте **`docker/tools/docker-compose.yml`** у сервиса **`evolution-api`** поле **`build.context`** должно быть **`.`** (корень репозитория при использовании корневого **`compose.yaml`**); иначе команда сборки из корня может завершиться ошибкой (исторический hotfix: ранее встречалось значение вроде **`docker/tools`**, несогласованное с merge из корня).

Перед первым запуском **tools**, при необходимости, выполните:

```bash
docker compose config --quiet
docker compose --profile tools build evolution-api
```

```bash
docker network create propradar 2>/dev/null || true

# Минимум для API + PostgreSQL (типичный сервер приложения):
docker compose --profile infra --profile app up -d

# Дополнительно инструменты (n8n, Metabase, Evolution; образ см. build выше):
docker compose --profile tools up -d

# Evolution с Redis-кэшем (CACHE_REDIS_ENABLED=true): Redis во фрагменте infra — поднимите
# хотя бы один раз вместе, например: docker compose --profile infra --profile tools up -d

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
