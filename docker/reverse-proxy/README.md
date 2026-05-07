# Reverse-proxy (Nginx) для PropRadar

TLS-терминация и внешний HTTPS для **n8n** и **Evolution API**. Контейнер подключается к внешней сети Docker `propradar` и проксирует на сервисы из `docker/tools/docker-compose.yml`: `n8n`, `evolution-api`. Порты **5678** и **8080** на хосте не публикуются — доступ только через этот прокси (80/443) по доменам **n8n.usluga-market.ru** и **evolution.usluga-market.ru**.

Порядок стеков и матрица портов на сервере — `docs/DEPLOY_SERVER.md`.

## API наружу (решение по умолчанию)

**FastAPI (`api`) через этот reverse-proxy не публикуется.** Интеграции (n8n, др.) обращаются к API по внутреннему URL в той же сети: `http://api:8000` (см. `docker/app/docker-compose.yml`). Чтобы вывести API на публичный HTTPS, понадобится отдельный `server` в Nginx, WAF, ограничение по IP/API key и согласование с `docs/API.md` — это сознательно вне текущего каркаса.

## Быстрый старт

1. Сеть (один раз): `docker network create propradar`
2. Запущены `docker/tools` (и при необходимости `docker/infra` + `docker/app` для `api`). Для n8n: `N8N_HOST=n8n.usluga-market.ru`, `N8N_PROTOCOL=https`, порт как в документации вашей версии n8n. Для Evolution: `SERVER_URL=https://evolution.usluga-market.ru`.

### Первичный выпуск TLS (certbot standalone)

Убедитесь, что **порт 80 свободен** (контейнер `propradar-reverse-proxy` / другой nginx **не запущены**). На хосте с Docker:

```bash
sudo certbot certonly --standalone --email <YOUR_EMAIL> --agree-tos --no-eff-email \
  -d n8n.usluga-market.ru
sudo certbot certonly --standalone --email <YOUR_EMAIL> --agree-tos --no-eff-email \
  -d evolution.usluga-market.ru
```

После успешной выдачи сертификатов поднимите прокси из этой папки:

```bash
docker compose up -d
```

Либо из **корня репозитория**: `docker compose --profile proxy up -d` (см. корневой `compose.yaml`).

Сухой прогон: `docker compose config` (из этой папки) или из корня с профилем `proxy`.

### Монтирование TLS (отдельные файлы, без жёстких путей в nginx)

В `conf.d/*.conf` внутри контейнера используются **фиксированные** пути:

- `/etc/nginx/certs/n8n/fullchain.pem` и `/etc/nginx/certs/n8n/privkey.pem`;
- `/etc/nginx/certs/evolution/fullchain.pem` и `/etc/nginx/certs/evolution/privkey.pem`.

На **хосте** пути к реальным `fullchain.pem` / `privkey.pem` задаются переменными окружения для **file bind-mount** (любой домен, любой каталог на хосте):

| Переменная | Назначение | Значение по умолчанию (текущие домены) |
|------------|------------|----------------------------------------|
| **`N8N_TLS_FULLCHAIN`** | fullchain для n8n | `./letsencrypt/live/n8n.usluga-market.ru/fullchain.pem` |
| **`N8N_TLS_PRIVKEY`** | приватный ключ n8n | `./letsencrypt/live/n8n.usluga-market.ru/privkey.pem` |
| **`EVOLUTION_TLS_FULLCHAIN`** | fullchain для Evolution | `./letsencrypt/live/evolution.usluga-market.ru/fullchain.pem` |
| **`EVOLUTION_TLS_PRIVKEY`** | приватный ключ Evolution | `./letsencrypt/live/evolution.usluga-market.ru/privkey.pem` |

Пути по умолчанию **относительны** к каталогу `docker/reverse-proxy`. На Linux в проде удобно задать абсолютные пути в `.env` рядом с compose, например:

```env
N8N_TLS_FULLCHAIN=/etc/letsencrypt/live/n8n.usluga-market.ru/fullchain.pem
N8N_TLS_PRIVKEY=/etc/letsencrypt/live/n8n.usluga-market.ru/privkey.pem
EVOLUTION_TLS_FULLCHAIN=/etc/letsencrypt/live/evolution.usluga-market.ru/fullchain.pem
EVOLUTION_TLS_PRIVKEY=/etc/letsencrypt/live/evolution.usluga-market.ru/privkey.pem
```

Для **другого домена** достаточно сменить только эти четыре переменные (и при необходимости `server_name` в `nginx/conf.d/*.conf`).

**Preflight:** перед стартом `nginx` compose запускает `00-tls-preflight.sh` **явно** через `sh` (не полагается на автозапуск из `/docker-entrypoint.d` и на executable bit — это важно для Windows при `core.fileMode=false`). Скрипт проверяет наличие и читаемость всех четырёх файлов в контейнере. Если чего-то нет — контейнер завершится с сообщением вида `reverse-proxy preflight: отсутствует файл: ...` и краткой подсказкой по переменным (в логах `docker logs`).

Локально можно положить структуру `letsencrypt/live/<домен>/` под `docker/reverse-proxy/letsencrypt/` или указать любые другие пути через переменные выше.

**Let’s Encrypt и symlink:** в типичной установке certbot файлы в `live/<домен>/fullchain.pem` и `privkey.pem` — **симлинки** на `archive/...`. Docker при bind-mount **одного файла** кладёт в контейнер сам symlink; целевой путь из контейнера недоступен → nginx видит «битую» цепочку. Задавайте в переменных **реальные пути к файлам** (например вывод `readlink -f /etc/letsencrypt/live/<домен>/fullchain.pem` на хосте) либо копии с раскрытыми ссылками (`cp -L`).

### Автообновление (cron)

Пример cron (ежедневно, время по желанию):

```cron
0 3 * * * certbot renew --quiet --deploy-hook "docker exec propradar-reverse-proxy nginx -s reload"
```

Если в `/etc/letsencrypt/renewal/*.conf` для сертификата указан **authenticator = standalone**, при `renew` тоже потребуется свободный порт 80: добавьте **pre-hook** / **post-hook** (остановка контейнера прокси и запуск после renew) или один раз переведите продление на **webroot**, чтобы nginx продолжал слушать 80 и отдавал `/.well-known/acme-challenge/` (блок уже есть в `conf.d`).

**Не коммитьте** ключи и PEM в репозиторий.

## Runbook / операции

- Логи контейнера: `docker logs propradar-reverse-proxy` (при ошибке preflight смотрите первые строки после `docker compose up`)
- После смены `conf.d/*.conf`: `docker compose exec reverse-proxy nginx -s reload` или перезапуск контейнера.
- Если n8n «отваливаются» websocket: убедитесь, что заголовки `Upgrade` / `Connection` на месте (см. `n8n.conf`).

## Безопасность

- PostgreSQL (`leads-db`) не должен слушать `0.0.0.0:5433` в интернете — см. `docs/DEPLOY_SERVER.md`.
- Публично остаются только 80/443 reverse-proxy и те порты, что вы явно открыли на файрволе (например, Metabase **3031**, если нужен прямой доступ).
