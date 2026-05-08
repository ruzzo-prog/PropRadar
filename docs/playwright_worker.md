# Playwright-worker — архитектура и runbook

Документ описывает сервис **`playwright-worker`** в контуре PropRadar: зачем он нужен, как правильно поднимать профили Docker и как диагностировать проблемы **без правок кода** (скрипты в `/tmp` внутри контейнера).

## Назначение

- **HTTP API** (FastAPI, порт контейнера **8001**): обогащение лидов через Playwright (в т.ч. фаза **`phone`** для **myhome**), автологин, health.
- **Контракт с n8n:** `POST http://playwright-worker:8001/enrich` с телом вроде `{"adapter":"myhome","phase":"phone"}` — успешный ответ для оркестратора **только HTTP 202**; polling результата не выполняется (см. `docs/INGRESS_ARCHITECTURE.md`).

## Архитектура контейнера

| Компонент | Описание |
|-----------|----------|
| Образ | `docker/app/playwright-worker.Dockerfile` (базовый образ Playwright for Python). |
| Процесс | `uvicorn` на **:8001**, при необходимости Xvfb для headful/headless Chromium (см. entrypoint в репозитории). |
| Код | Монтируется/копируется в образ согласно Dockerfile; `PYTHONPATH` указывает на `src`. |
| БД | `DATABASE_URL` — PostgreSQL **`leads-db`** в сети **`propradar`** (тот же хост, что и у API). |
| Сессии Playwright | Том **`adapter_playwright_sessions`** → **`/data/adapter_sessions`**; путь к JSON сессии myhome задаётся **`MYHOME_SESSION_PATH`** (по умолчанию см. `docker/app/docker-compose.yml`). |

## Профили Compose: почему **`--profile infra --profile enricher`**, а не только **`--profile app`**

- Сервис **`leads-db`** объявлен во фрагменте **`docker/infra/docker-compose.yml`** с профилем **`infra`**. Без **`--profile infra`** контейнер БД **не поднимается**.
- **`playwright-worker`** объявлен во фрагменте **`docker/app/docker-compose.yml`** с профилями **`enricher`** и **`workers`**. Для сценария обогащения через n8n обычно достаточно **`enricher`**.
- У **`playwright-worker`** в compose указано **`depends_on: leads-db`** с условием **`service_healthy`**. Если **`leads-db`** не в проекте (не включён **`infra`**), разрешение зависимостей и старт воркера будут некорректны.

**Итог:** для воркера с БД из репозитория почти всегда нужно:

```bash
docker compose --profile infra --profile enricher up -d
```

(из **корня** репозитория, где лежит `compose.yaml`; сеть **`propradar`** должна существовать: `docker network create propradar`.)

**Зачем не ограничиваться `--profile app`:** профиль **`app`** поднимает, в частности, **`api`**, который также зависит от **`leads-db`**. Если поднять только **`app`** без **`infra`**, сервис **`leads-db`** не стартует — в корневом merge это проявляется как проблема зависимостей (см. известный баг в `docs/PropRadar_STATUS.md`).

## Runbook: деплой и smoke

1. **`git pull`** в каталоге репозитория на сервере.
2. Убедиться, что в **корневом** `.env` заданы **`MYHOME_EMAIL`**, **`MYHOME_PASSWORD`**, при необходимости **`MYHOME_SESSION_PATH`**, **`DATABASE_URL`** (см. `docs/DEPLOY_SERVER.md`).
3. Пересборка образа воркера (при изменении Dockerfile или зависимостей):

   ```bash
   docker compose --profile infra --profile enricher build playwright-worker
   ```

4. Запуск / обновление:

   ```bash
   docker compose --profile infra --profile enricher up -d playwright-worker
   ```

5. **Smoke:**
   - `curl -fsS http://127.0.0.1:8001/health` с хоста (если порт **8001** проброшен) или из контейнера в той же сети: `curl -fsS http://playwright-worker:8001/health` → ожидается **HTTP 200**.
   - При необходимости — `POST /login` или полный цикл n8n с **`phase=phone`** и проверкой **202**.

## Диагностический инструментарий (скрипты в `/tmp`)

Ниже — **типовые имена** утилит, которые оператор держит на хосте (например в **`/tmp/check_*.py`**) и при необходимости копирует в контейнер. В репозитории они **не обязаны** присутствовать; это шаблон процесса отладки.

| Скрипт | Назначение |
|--------|------------|
| **`check_form.py`** | Дамп всех **`input`** на странице (тип, name, id, видимость). |
| **`check_selector.py`** | Проверка одного CSS/XPath селектора (count, visible). |
| **`check_candidates.py`** | Перебор кандидатов из списка вроде **`EMAIL_SELECTORS`** (какой первый видимый). |
| **`check_network.py`** | Лог сетевых ответов при сабмите формы (фильтр по URL/статусу, **без** вывода телефонов/JWT в общий лог). |
| **`check_auth_response.py`** | Зафиксировать тело/статус ответа **`accounts.tnet.ge/.../user/auth`** (осторожно с секретами — не сохранять в открытые файлы). |
| **`check_redirect.py`** | Мониторинг **`page.url`** после сабмита (цепочка **auth.tnet.ge** → **auth.myauto.ge** → **myhome.ge**). |

### Копирование и запуск в контейнере

```bash
# имя контейнера подставьте из `docker ps` (часто propradar-playwright-worker-1 или см. compose)
docker cp /tmp/check_form.py <container>:/tmp/check_form.py
docker exec <container> python3 /tmp/check_form.py
```

Для скриптов, которым нужен Playwright внутри контейнера, используйте то же окружение (**`PYTHONPATH`**, переменные **`MYHOME_*`**) что и у воркера.

## См. также

- `docs/myhome_login.md` — автологин и сессия myhome.
- `docs/phone_extraction.md` — телефон и ограничения HTTP.
- `docs/DEPLOY_SERVER.md` — секреты и серверный деплой.
- `docs/INGRESS_ARCHITECTURE.md` — поток n8n → worker → БД.
