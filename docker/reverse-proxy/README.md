# Reverse-proxy (Nginx) для PropRadar

TLS-терминация и внешний HTTPS для **n8n**, **Evolution API**, **Metabase** и **Snapotter**. Контейнер подключается к внешней сети Docker `propradar` и проксирует на сервисы **`n8n`**, **`evolution-api`**, **`metabase:3000`** из `docker/tools/docker-compose.yml` и **`snapotter:1349`** из `docker/app/docker-compose.yml`. Порты **5678** и **8080** на хосте не публикуются — доступ только через этот прокси (80/443) по доменам **n8n.usluga-market.ru**, **evolution.usluga-market.ru**, **metabase.usluga-market.ru** и **snapotter.usluga-market.ru** (Metabase по-прежнему может быть доступен напрямую с хоста на **3031** → 3000, если порт опубликован во фрагменте `tools`).

Порядок стеков и матрица портов на сервере — `docs/DEPLOY_SERVER.md`.

## API наружу (решение по умолчанию)

**FastAPI (`api`) через этот reverse-proxy не публикуется.** Интеграции (n8n, др.) обращаются к API по внутреннему URL в той же сети: `http://api:8000` (см. `docker/app/docker-compose.yml`). Чтобы вывести API на публичный HTTPS, понадобится отдельный `server` в Nginx, WAF, ограничение по IP/API key и согласование с `docs/API.md` — это сознательно вне текущего каркаса.

## Быстрый старт

1. Сеть (один раз): `docker network create propradar`
2. Запущены `docker/tools` и при необходимости `docker/infra` + `docker/app` (для `api` и/или сервиса **`snapotter`** с профилем **`app`**). Для n8n: `N8N_HOST=n8n.usluga-market.ru`, `N8N_PROTOCOL=https`, порт как в документации вашей версии n8n. Для Evolution: `SERVER_URL=https://evolution.usluga-market.ru`. Для Metabase за прокси задайте публичный URL с тем же хостом, что в `server_name` (например `MB_SITE_URL=https://metabase.usluga-market.ru` — см. документацию Metabase по переменным окружения для вашей версии).

### Первичный выпуск TLS (certbot standalone)

Убедитесь, что **порт 80 свободен** (контейнер `propradar-reverse-proxy` / другой nginx **не запущены**). На хосте с Docker:

```bash
sudo certbot certonly --standalone --email <YOUR_EMAIL> --agree-tos --no-eff-email \
  -d n8n.usluga-market.ru
sudo certbot certonly --standalone --email <YOUR_EMAIL> --agree-tos --no-eff-email \
  -d evolution.usluga-market.ru
sudo certbot certonly --standalone --email <YOUR_EMAIL> --agree-tos --no-eff-email \
  -d metabase.usluga-market.ru
sudo certbot certonly --standalone --email <YOUR_EMAIL> --agree-tos --no-eff-email \
  -d snapotter.usluga-market.ru
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
- `/etc/nginx/certs/evolution/fullchain.pem` и `/etc/nginx/certs/evolution/privkey.pem`;
- `/etc/nginx/certs/metabase/fullchain.pem` и `/etc/nginx/certs/metabase/privkey.pem`;
- `/etc/nginx/certs/snapotter/fullchain.pem` и `/etc/nginx/certs/snapotter/privkey.pem`.

На **хосте** пути к реальным `fullchain.pem` / `privkey.pem` задаются переменными окружения для **file bind-mount** (любой домен, любой каталог на хосте):

| Переменная | Назначение | Значение по умолчанию (текущие домены) |
|------------|------------|----------------------------------------|
| **`N8N_TLS_FULLCHAIN`** | fullchain для n8n | `./letsencrypt/live/n8n.usluga-market.ru/fullchain.pem` |
| **`N8N_TLS_PRIVKEY`** | приватный ключ n8n | `./letsencrypt/live/n8n.usluga-market.ru/privkey.pem` |
| **`EVOLUTION_TLS_FULLCHAIN`** | fullchain для Evolution | `./letsencrypt/live/evolution.usluga-market.ru/fullchain.pem` |
| **`EVOLUTION_TLS_PRIVKEY`** | приватный ключ Evolution | `./letsencrypt/live/evolution.usluga-market.ru/privkey.pem` |
| **`METABASE_TLS_FULLCHAIN`** | fullchain для Metabase | `./letsencrypt/live/metabase.usluga-market.ru/fullchain.pem` |
| **`METABASE_TLS_PRIVKEY`** | приватный ключ Metabase | `./letsencrypt/live/metabase.usluga-market.ru/privkey.pem` |
| **`SNAPOTTER_TLS_FULLCHAIN`** | fullchain для Snapotter | `./letsencrypt/live/snapotter.usluga-market.ru/fullchain.pem` |
| **`SNAPOTTER_TLS_PRIVKEY`** | приватный ключ Snapotter | `./letsencrypt/live/snapotter.usluga-market.ru/privkey.pem` |

Пути по умолчанию **относительны** к каталогу `docker/reverse-proxy`. На Linux в проде удобно задать абсолютные пути в `.env` рядом с compose, например:

```env
N8N_TLS_FULLCHAIN=/etc/letsencrypt/live/n8n.usluga-market.ru/fullchain.pem
N8N_TLS_PRIVKEY=/etc/letsencrypt/live/n8n.usluga-market.ru/privkey.pem
EVOLUTION_TLS_FULLCHAIN=/etc/letsencrypt/live/evolution.usluga-market.ru/fullchain.pem
EVOLUTION_TLS_PRIVKEY=/etc/letsencrypt/live/evolution.usluga-market.ru/privkey.pem
METABASE_TLS_FULLCHAIN=/etc/letsencrypt/live/metabase.usluga-market.ru/fullchain.pem
METABASE_TLS_PRIVKEY=/etc/letsencrypt/live/metabase.usluga-market.ru/privkey.pem
SNAPOTTER_TLS_FULLCHAIN=/etc/letsencrypt/live/snapotter.usluga-market.ru/fullchain.pem
SNAPOTTER_TLS_PRIVKEY=/etc/letsencrypt/live/snapotter.usluga-market.ru/privkey.pem
```

Для **другого домена** достаточно сменить соответствующие переменные (и при необходимости `server_name` в `nginx/conf.d/*.conf`).

**Preflight:** перед стартом `nginx` compose запускает `00-tls-preflight.sh` **явно** через `sh` (не полагается на автозапуск из `/docker-entrypoint.d` и на executable bit — это важно для Windows при `core.fileMode=false`). Скрипт проверяет наличие и читаемость **восьми** TLS-файлов (четыре домена × `fullchain` + `privkey`: n8n, Evolution, Metabase, Snapotter). Если чего-то нет — контейнер завершится с сообщением вида `reverse-proxy preflight: отсутствует файл: ...` и краткой подсказкой по переменным (в логах `docker logs`). Полный конспект контура — **`docs/TLS_LETSENCRYPT.md`**.

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
- После смены `conf.d/*.conf` или переменных `*_TLS_*`: из корня репозитория `docker compose --profile proxy up -d --force-recreate reverse-proxy` или `docker compose exec reverse-proxy nginx -s reload` (если меняли только `*.conf` и конфиг уже смонтирован).
- Smoke для Metabase: `curl -sI http://metabase.usluga-market.ru/` — ожидаются `301` и заголовок `Location` на `https://metabase.usluga-market.ru/`; затем в браузере `https://metabase.usluga-market.ru/` — должен открываться UI Metabase.
- Если n8n «отваливаются» websocket: убедитесь, что заголовки `Upgrade` / `Connection` на месте (см. `n8n.conf`).

## Безопасность

- PostgreSQL (`leads-db`) не должен слушать `0.0.0.0:5433` в интернете — см. `docs/DEPLOY_SERVER.md`.
- Публично остаются только 80/443 reverse-proxy и те порты, что вы явно открыли на файрволе (например, Metabase **3031**, если нужен прямой доступ к контейнеру минуя HTTPS **metabase.usluga-market.ru**).
