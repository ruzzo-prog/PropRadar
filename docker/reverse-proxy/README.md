# Reverse-proxy (Nginx) для PropRadar

TLS-терминация и внешний HTTPS для **n8n** и **Evolution API**. Контейнер подключается к внешней сети Docker `propradar` и проксирует на сервисы из `docker/tools/docker-compose.yml`: `n8n`, `evolution-api`. Порты **5678** и **8080** на хосте не публикуются — доступ только через этот прокси (80/443) по доменам **n8n.usluga-market.ru** и **evolution.usluga-market.ru**.

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

Сухой прогон: `docker compose config`.

### Монтирование сертификатов в nginx

В `docker-compose.yml` каталоги хоста смонтированы **read-only**: `/etc/letsencrypt/live` и **`/etc/letsencrypt/archive`**. Файлы в `live/<домен>/` — симлинки на `archive/`; без монтирования `archive` nginx в контейнере не сможет прочитать цепочку.

### Автообновление (cron)

Пример cron (ежедневно, время по желанию):

```cron
0 3 * * * certbot renew --quiet --deploy-hook "docker exec propradar-reverse-proxy nginx -s reload"
```

Если в `/etc/letsencrypt/renewal/*.conf` для сертификата указан **authenticator = standalone**, при `renew` тоже потребуется свободный порт 80: добавьте **pre-hook** / **post-hook** (остановка контейнера прокси и запуск после renew) или один раз переведите продление на **webroot**, чтобы nginx продолжал слушать 80 и отдавал `/.well-known/acme-challenge/` (блок уже есть в `conf.d`).

**Не коммитьте** ключи и PEM в репозиторий.

## Runbook / операции

- Логи контейнера: `docker logs propradar-reverse-proxy`
- После смены `conf.d/*.conf`: `docker compose exec reverse-proxy nginx -s reload` или перезапуск контейнера.
- Если n8n «отваливаются» websocket: убедитесь, что заголовки `Upgrade` / `Connection` на месте (см. `n8n.conf`).

## Безопасность

- PostgreSQL (`leads-db`) не должен слушать `0.0.0.0:5433` в интернете — см. `docs/DEPLOY_SERVER.md`.
- Публично остаются только 80/443 reverse-proxy и те порты, что вы явно открыли на файрволе (например, Metabase **3031**, если нужен прямой доступ).
