# Reverse-proxy (Nginx) для PropRadar

TLS-терминация и внешний HTTPS для **n8n** и **Evolution API**. Контейнер подключается к внешней сети Docker `propradar` и проксирует на сервисы из `docker/tools/docker-compose.yml`: `n8n`, `evolution-api`.

## API наружу (решение по умолчанию)

**FastAPI (`api`) через этот reverse-proxy не публикуется.** Интеграции (n8n, др.) обращаются к API по внутреннему URL в той же сети: `http://api:8000` (см. `docker/app/docker-compose.yml`). Чтобы вывести API на публичный HTTPS, понадобится отдельный `server` в Nginx, WAF, ограничение по IP/API key и согласование с `docs/API.md` — это сознательно вне текущего каркаса.

## Быстрый старт

1. Сеть (один раз): `docker network create propradar`
2. Запущены `docker/tools` (и при необходимости `docker/infra` + `docker/app` для `api`).
3. TLS: каталог `nginx/ssl/` должен содержать `fullchain.pem` и `privkey.pem` **до** `docker compose up` (иначе Nginx не поднимется). Для теста:

   ```bash
   openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
     -keyout nginx/ssl/privkey.pem -out nginx/ssl/fullchain.pem \
     -subj "/CN=n8n.example.com"
   ```

4. В `nginx/conf.d/n8n.conf` и `evolution.conf` замените `n8n.example.com` / `evolution.example.com` на реальные FQDN.
5. В env n8n выставьте `N8N_HOST`, `N8N_PROTOCOL=https`, порт `443` (или пустой, см. доки n8n для вашей версии). Для Evolution — `SERVER_URL=https://<ваш-evolution-FQDN>`.
6. Запуск из этой папки:

   ```bash
   docker compose up -d
   ```

Сухой прогон: `docker compose config`.

## Certbot (Let's Encrypt)

Том `reverse_proxy_certbot_www` смонтирован в `/var/www/certbot`. Настройте выпуск сертификатов на хосте или отдельным контейнером certbot с тем же томом; путь challenge: `/.well-known/acme-challenge/` (уже прописан в server для порта 80). **Не коммитьте** ключи и PEM в репозиторий.

## Runbook / операции

- Логи контейнера: `docker logs propradar-reverse-proxy`
- После смены `conf.d/*.conf`: `docker compose exec reverse-proxy nginx -s reload` или перезапуск контейнера.
- Если n8n «отваливаются» websocket: убедитесь, что заголовки `Upgrade` / `Connection` на месте (см. `n8n.conf`).

## Безопасность

- PostgreSQL (`leads-db`) не должен слушать `0.0.0.0:5433` в интернете — см. `docs/DEPLOY_SERVER.md`.
- Публично остаются только 80/443 reverse-proxy и те порты, что вы явно открыли на файрволе.
