# Let's Encrypt и TLS на прод-сервере (Hetzner / PropRadar)

Единый конспект: как устроена терминация TLS, как выпускать сертификаты и добавлять новый FQDN без поломки существующих доменов. Короткая шпаргалка по командам дополнительно в `docker/reverse-proxy/README.md`; матрица портов и порядок профилей compose — в `docs/DEPLOY_SERVER.md`.

---

## 1. Роли компонентов

| Компонент | Где работает | Задача |
|-----------|----------------|--------|
| **DNS** | У регистратора | **A**-запись FQDN на публичный IP сервера (для текущего контура — один IP на несколько поддоменов). |
| **UFW / firewall** | Хост Ubuntu | Открыты **80/tcp** и **443/tcp** снаружи; остальное — по минимуму. |
| **Certbot** | **Хост**, не в контейнере | Выпуск и продление сертификатов LE; материал в `/etc/letsencrypt/`. |
| **docker `propradar-reverse-proxy`** | Контейнер **nginx** | Слушает **80/443**, отдаёт **`/.well-known/acme-challenge/`** (webroot volume), редирект **HTTP→HTTPS**, проксирует на сервисы в сети **`propradar`**. |
| **Корневой `.env` репозитория** | Хост (рядом с `compose.yaml`) | Абсолютные пути к **файлам** `fullchain.pem` / `privkey.pem` на хосте для **bind-mount** в контейнер (по одной паре на публичный домен). |

---

## 2. Цепочка доверия и каталоги Let's Encrypt

После успешного `certbot certonly` для домена `example.usluga-market.ru`:

- Канонический путь lineage: **`/etc/letsencrypt/live/example.usluga-market.ru/`**.
- В каталоге **`live/<домен>/`** лежат **`fullchain.pem`** и **`privkey.pem`**. В типичной установке это **симлинки** на файлы в **`/etc/letsencrypt/archive/...`**.

**Критично для Docker bind-mount одного файла:** при монтировании в контейнер самого symlink из `live/` целевой файл из `archive/` **недоступен** внутри контейнера — nginx получает «битую» цепочку. Поэтому в переменных **`*_TLS_*`** на проде указывают:

- либо **реальный путь после раскрытия**: `readlink -f /etc/letsencrypt/live/<домен>/fullchain.pem` (и то же для `privkey.pem`);
- либо **копию** с разыменованием ссылок (`cp -L` и т.п.).

Это относится ко **всем** доменам в контуре: **n8n**, **Evolution**, **Metabase** (и любым будущим FQDN по тому же паттерну).

---

## 3. Порты и два сценария certbot

### 3.1. Первичный выпуск: `certbot certonly --standalone`

- Требуется: **порт 80 на хосте свободен** на время запуска certbot (ничто не слушает **0.0.0.0:80**).
- Пока certbot слушает **80**, контейнер **`propradar-reverse-proxy`** (и любой другой nginx на **80**) должен быть **остановлен**.
- Пример для **нового** FQDN (замените email и домен):

```bash
sudo certbot certonly --standalone --email <YOUR_EMAIL> --agree-tos --no-eff-email -d <новый.fqdn>
```

### 3.2. Продление: `certbot renew`

- Если в **`/etc/letsencrypt/renewal/<домен>.conf`** указан **`authenticator = standalone`**, при **`renew`** снова понадобится **свободный 80** — обычно делают **pre-hook** / **post-hook**: остановить прокси, выполнить renew, поднять прокси.
- Альтернатива: перевести выпуск/продление на **webroot** при уже работающем nginx, чтобы **80** оставался за прокси, а **`/.well-known/acme-challenge/`** отдавался из **`/var/www/certbot`** (том **`reverse_proxy_certbot_www`** в compose reverse-proxy). Это отдельная миграция и не обязательна, если hooks для standalone устраивают операционно.

Пример cron с перезагрузкой nginx в контейнере после renew (когда renew не требует остановки прокси или hooks уже обеспечили файлы на диске):

```cron
0 3 * * * certbot renew --quiet --deploy-hook "docker exec propradar-reverse-proxy nginx -s reload"
```

---

## 4. Переменные `.env` на хосте (три домена в репозитории)

Compose (фрагмент `docker/reverse-proxy/docker-compose.yml`) монтирует **отдельные файлы** PEM в **фиксированные** пути внутри контейнера. На хосте задаются **шесть** переменных:

| Переменная | Файл в контейнере |
|------------|-------------------|
| **`N8N_TLS_FULLCHAIN`** | `/etc/nginx/certs/n8n/fullchain.pem` |
| **`N8N_TLS_PRIVKEY`** | `/etc/nginx/certs/n8n/privkey.pem` |
| **`EVOLUTION_TLS_FULLCHAIN`** | `/etc/nginx/certs/evolution/fullchain.pem` |
| **`EVOLUTION_TLS_PRIVKEY`** | `/etc/nginx/certs/evolution/privkey.pem` |
| **`METABASE_TLS_FULLCHAIN`** | `/etc/nginx/certs/metabase/fullchain.pem` |
| **`METABASE_TLS_PRIVKEY`** | `/etc/nginx/certs/metabase/privkey.pem` |

Типичный прод (пути в `live/`; при symlink — см. раздел 2):

```env
N8N_TLS_FULLCHAIN=/etc/letsencrypt/live/n8n.usluga-market.ru/fullchain.pem
N8N_TLS_PRIVKEY=/etc/letsencrypt/live/n8n.usluga-market.ru/privkey.pem
EVOLUTION_TLS_FULLCHAIN=/etc/letsencrypt/live/evolution.usluga-market.ru/fullchain.pem
EVOLUTION_TLS_PRIVKEY=/etc/letsencrypt/live/evolution.usluga-market.ru/privkey.pem
METABASE_TLS_FULLCHAIN=/etc/letsencrypt/live/metabase.usluga-market.ru/fullchain.pem
METABASE_TLS_PRIVKEY=/etc/letsencrypt/live/metabase.usluga-market.ru/privkey.pem
```

**Не подменять** эти переменными путём к самоподписанным файлам «для вида»: браузеры покажут недоверенный сертификат; preflight всё равно ожидает обычные **файлы** по mount.

---

## 5. Nginx и preflight в контейнере

- Конфиги vhost — **`docker/reverse-proxy/nginx/conf.d/*.conf`** (монтируются с хоста). Для каждого FQDN: блок **80** (challenge + редирект), блок **443** с `ssl_certificate` / `ssl_certificate_key` на пути **`/etc/nginx/certs/<имя>/...`** внутри контейнера.
- Перед **`nginx`** в **`command`** выполняется **`00-tls-preflight.sh`**: проверка **`-e`**, **`-f`**, **`-r`** для каждого из **шести** путей (три домена × `fullchain` + `privkey`). Любая ошибка → **exit 1**, контейнер не стартует, в логах текст с перечнем переменных.

### Типовые сообщения preflight

- **`отсутствует файл` / `ожидался обычный файл` при смонтированном каталоге-заглушке Docker** — на хосте путь из **`*_TLS_*`** неверен или не файл; Docker мог создать **пустой каталог** вместо mount файла.
- **`нет прав на чтение`** — UID в контейнере не может читать файл на хосте (проверить права и владельца PEM).
- **Nginx сообщает ошибку цепочки при валидном preflight** — чаще всего проблема **symlink через mount** (раздел 2).

---

## 6. Порядок добавления N-го нового домена (чек-лист)

1. **DNS:** одна **A** на нужный IP.
2. **UFW:** открыть **80/443**.
3. **Освободить 80** и выполнить **`certbot certonly --standalone -d <новый.fqdn>`** (или webroot-сценарий, если уже настроен).
4. **Репозиторий (git):**
   - добавить **`docker/reverse-proxy/nginx/conf.d/<сервис>.conf`** по образцу существующих (`server_name`, `upstream` на **`имя-сервиса:порт`**, пути PEM под **`/etc/nginx/certs/<каталог>/`**);
   - в **`docker/reverse-proxy/docker-compose.yml`** — **две** новые строки **`volumes`** с **`${PREFIX_TLS_FULLCHAIN}`** и **`${PREFIX_TLS_PRIVKEY}`**, не изменяя уже смонтированные домены;
   - в **`00-tls-preflight.sh`** — два новых **`check_one`** и обновить текст подсказки в **`stderr`**.
5. **`/.env` на сервере** — добавить пару переменных с путями PEM (раздел 4).
6. **Перезапуск прокси** из корня репозитория:

```bash
docker compose --profile proxy up -d --force-recreate reverse-proxy
```

7. **Smoke:** `curl -sI http://<fqdn>/` → **301**, `curl -vI https://<fqdn>/` → успешная проверка цепочки и ожидаемый код ответа приложения.

Если нужен новый **backend** в Docker: объявите сервис во фрагменте compose (например `docker/app/docker-compose.yml`), сеть **`propradar`** **external: true**, **без публикации порта на хост** (или осознанно с публикацией), имя контейнера для **upstream** должно совпадать с **именем сервиса**.

---

## 7. Ограничения и несоответствия по умолчанию

- **Корневой `compose.yaml`** только **включает** фрагменты; новые прикладные сервисы добавляют в соответствующий фрагмент (**`docker/app/docker-compose.yml`**, `docker/tools`, …), а не в корень без `include`.
- **Профили:** для API+БД обычно нужны **`--profile infra --profile app`** (см. известные ограничения в `docs/PropRadar_STATUS.md`).

---

## 8. Верификация после изменений

- `docker compose config` из корня репозитория с нужными профилями.
- Логи: `docker logs propradar-reverse-proxy` при ошибке preflight или nginx.
- Повторная проверка symlink: `readlink -f` на хосте для каждого смонтированного PEM.
