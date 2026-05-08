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
| Metabase UI (прямой проброс с хоста) | `docker/tools` | **3031** → 3000 |
| Metabase по HTTPS (через reverse-proxy) | `docker/reverse-proxy` | **443** (`https://metabase.usluga-market.ru/`), внутри сети `metabase:3000` |
| n8n (слушает в контейнере; **на хост не проброшен**) | `docker/tools` | **5678** (только внутри `propradar`) |
| Evolution API (аналогично) | `docker/tools` | **8080** (только внутри `propradar`) |
| Reverse-proxy HTTP/HTTPS | `docker/reverse-proxy` | 80, 443 |

Публичный доступ к n8n, Evolution и Metabase на сервере — через **HTTPS** на **`docker/reverse-proxy`** (домены и TLS — см. `docker/reverse-proxy/README.md`, переменные **`N8N_TLS_*`**, **`EVOLUTION_TLS_*`**, **`METABASE_TLS_*`** и preflight перед стартом nginx).

## Redis и Evolution API

- Сервис **Redis** — во фрагменте **`docker/infra`** (**`propradar-redis`**, образ **`redis:7.4.9-alpine`**), только внутренний доступ по Docker-сети; наружу порт не открывается.
- По умолчанию в **`docker/tools/.env.example`** для Evolution задано **`CACHE_REDIS_ENABLED=false`**: можно поднимать только **`--profile tools`** без Redis — контейнер **не ждёт** недоступный Redis.
- Чтобы использовать Redis-кэш Evolution (**`CACHE_REDIS_ENABLED=true`**), поднимайте **одновременно** **`--profile infra`** и **`--profile tools`** из корня (**один** `compose.yaml`, сеть **`propradar`**), параметры см. **`docker/tools/.env.example`** (**`CACHE_REDIS_URI`** обычно **`redis://propradar-redis:6379`**).
- Compose **не** связывает **`depends_on`** между **`tools`** и **`infra`** для этого сценария; при **`CACHE_REDIS_ENABLED=true`** контейнер **`evolution-api`** перед стартом приложения выполняет ожидание TCP-доступности Redis по **`CACHE_REDIS_URI`** (см. **`command`** во фрагменте **`docker/tools/docker-compose.yml`**).
- **Старт Evolution (Prisma):** миграции и генерация выполняются командами **`npm run db:deploy`** и **`npm run db:generate`**, затем поднимается прод-сервер через **`exec npm run start:prod`** (те же шаги в **`docker/tools/docker-compose.yml`**). Устаревший вызов **`deploy_database.sh`** не используется — при ошибке в этой цепочке контейнер завершится на шаге оболочки (**`set -euo pipefail`**).

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

**Evolution API (Docker):** используется публичный образ **`evoapicloud/evolution-api`** (официальная цепочка публикаций Evolution API v2). Локальная сборка Dockerfile в репозитории не требуется. Персистентность данных инстансов — именованный volume **`evolution_instances`** → **`/evolution/instances`** (контейнерный процесс в образе работает под **`root`**, что устраняет типичный **`EACCES`** при записи в named volume без открытых **`777`** прав на файловую систему хоста).

**Pairing Code / привязка WhatsApp:** это сценарий **connect-flow** в Evolution Manager либо HTTP-методы инстанса, описанные в официальной документации Evolution API (Manager «подключить инстанс» / pairing). В шаблонах **`.env.example`** отдельные переменные «включить pairing» не задаём — параметры берите из канала документации продукта, а ключ API — **`AUTHENTICATION_API_KEY`**.

Перед первым запуском **tools**, при необходимости, выполните:

```bash
docker compose config --quiet
```

```bash
docker network create propradar 2>/dev/null || true

# Минимум для API + PostgreSQL (типичный сервер приложения):
docker compose --profile infra --profile app up -d

# Дополнительно инструменты (n8n, Metabase, Evolution; образ evoapicloud/evolution-api):
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

Каноничные детали — `docker/reverse-proxy/README.md`: параметризованные file-mount сертификатов, preflight для **шести** PEM-файлов (**n8n**, **Evolution**, **Metabase**: по `fullchain` и `privkey` внутри контейнера — переменные **`N8N_TLS_*`**, **`EVOLUTION_TLS_*`**, **`METABASE_TLS_*`**), явный запуск скрипта через `sh`. API за прокси по умолчанию не выводится; n8n вызывает `http://api:8000` внутри Docker.

### Единый процесс Let's Encrypt (n8n, Evolution, Metabase)

Один тип доверия для всех трёх публичных доменов: **Let's Encrypt** на хосте, **шесть** переменных в корневом **`.env`**, монтирование в контейнер nginx по `docker/reverse-proxy/docker-compose.yml`, проверка **preflight** до старта nginx.

1. **Предварительные условия**
   - **UFW:** открыть **`80/tcp`** и **`443/tcp`** (`sudo ufw allow 80/tcp`, `sudo ufw allow 443/tcp`; при необходимости `sudo ufw reload`). Для **`certbot certonly --standalone`** порт **80** на хосте должен быть **свободен** на время выпуска (временно остановите сервис, который слушает 80, либо используйте webroot — см. `docker/reverse-proxy/README.md`).
   - **DNS:** для каждого FQDN одна **A**-запись на **один** публичный IP сервера (без дублирующих A на другие адреса для того же имени — иначе ACME и браузер могут расходоваться с фактическим сервером).
   - **Docker:** сеть **`propradar`**, из корня репозитория профили **`tools`** и **`proxy`** так, чтобы **`reverse-proxy`**, **`n8n`**, **`evolution-api`**, **`metabase`** были в одной сети (см. раздел «Типовой порядок compose» выше).

2. **Выпуск сертификатов (certbot, standalone)**

   На каждый домен — отдельная команда (после освобождения 80, п. 1):

   ```bash
   sudo certbot certonly --standalone --email <YOUR_EMAIL> --agree-tos --no-eff-email -d n8n.usluga-market.ru
   sudo certbot certonly --standalone --email <YOUR_EMAIL> --agree-tos --no-eff-email -d evolution.usluga-market.ru
   sudo certbot certonly --standalone --email <YOUR_EMAIL> --agree-tos --no-eff-email -d metabase.usluga-market.ru
   ```

   Продление и политика renew — на хосте (cron, `certbot renew`, перезагрузка nginx в контейнере); symlink в `live/` и bind-mount — см. `docker/reverse-proxy/README.md` (`readlink -f` при необходимости).

3. **Переменные в корневом `.env`**

   Задайте **все шесть** путей к материалу LE (типичный путь на Ubuntu после certbot):

   ```
   N8N_TLS_FULLCHAIN=/etc/letsencrypt/live/n8n.usluga-market.ru/fullchain.pem
   N8N_TLS_PRIVKEY=/etc/letsencrypt/live/n8n.usluga-market.ru/privkey.pem
   EVOLUTION_TLS_FULLCHAIN=/etc/letsencrypt/live/evolution.usluga-market.ru/fullchain.pem
   EVOLUTION_TLS_PRIVKEY=/etc/letsencrypt/live/evolution.usluga-market.ru/privkey.pem
   METABASE_TLS_FULLCHAIN=/etc/letsencrypt/live/metabase.usluga-market.ru/fullchain.pem
   METABASE_TLS_PRIVKEY=/etc/letsencrypt/live/metabase.usluga-market.ru/privkey.pem
   ```

   В переменных **`_*_TLS_*`** указывайте **файлы на хосте**, которые реально существуют и читаются процессом docker (обычно пути под **`/etc/letsencrypt/live/<домен>/`**). Не подменяйте их путями вида **`/etc/nginx/certs/...` на хосте** для «обхода» LE: внутри контейнера nginx уже монтирует в **`/etc/nginx/certs/{n8n,evolution,metabase}/`**; если на хост положить только самоподписанный материал, браузер покажет **недоверенный** сертификат при том же preflight.

4. **Применение конфигурации reverse-proxy**

   Из **корня** репозитория:

   ```bash
   docker compose --profile proxy up -d --force-recreate reverse-proxy
   ```

   Если менялись только **`nginx/conf.d/*.conf`**, допустим `docker compose exec reverse-proxy nginx -s reload` (см. README).

5. **Проверка**

   ```bash
   curl -vI https://n8n.usluga-market.ru/ 2>&1 | grep -E 'SSL|HTTP'
   curl -vI https://evolution.usluga-market.ru/ 2>&1 | grep -E 'SSL|HTTP'
   curl -vI https://metabase.usluga-market.ru/ 2>&1 | grep -E 'SSL|HTTP'
   ```

   Ожидание: **`SSL certificate verify ok`**, ответ приложения (**`HTTP/2 200`** или согласованный редирект). Редирект с HTTP: `curl -sI http://<домен>/` — **`301`** и **`Location: https://...`**.

### Metabase (`metabase.usluga-market.ru`)

- **TLS и выпуск:** следуйте разделу **«Единый процесс Let's Encrypt»** выше (отдельный **`certbot`** для **`metabase.usluga-market.ru`**, пара **`METABASE_TLS_*`** в **`.env`**, пересоздание **`reverse-proxy`**).
- **Профиль `tools` и `proxy`:** контейнер **`metabase`** и **`reverse-proxy`** в сети **`propradar`** (из корня: `docker compose --profile infra --profile app --profile tools --profile proxy up -d`).
- **Metabase и публичный URL:** задайте в окружении сервиса `metabase` базовый URL под HTTPS за прокси (см. официальную документацию вашей версии Metabase), чтобы ссылки и редиректы не указывали на `http://...:3031`.

## Healthchecks

`leads-db` и `api` используют healthcheck в compose; `api` ждёт `service_healthy` для `leads-db` при совместном запуске с `docker/infra`.
