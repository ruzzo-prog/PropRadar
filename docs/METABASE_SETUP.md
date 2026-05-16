# Metabase для PropRadar

Инструкция для оператора: поднять Metabase в `docker/tools`, подключить **leads-db**, собрать дашборд по SQL из `metabase/propradar_dashboard.json`.

## Оглавление

- [Предусловия](#предусловия)
- [Порты и хосты](#порты-и-хосты)
- [Запуск tools](#запуск-tools)
- [Первый вход в Metabase](#первый-вход-в-metabase)
- [Подключение базы leads](#подключение-базы-leads)
- [Дашборд и SQL](#дашборд-и-sql)
- [Автоматизация дашборда (Metabase API)](#автоматизация-дашборда-metabase-api)
- [Критерии готовности](#критерии-готовности)

## Предусловия

- Сеть Docker **`propradar`** создана: `docker network create propradar` (один раз).
- Контейнер БД запущен из **`docker/infra`** (сервис **`leads-db`**, `container_name`: **`propradar-leads-db`**), данные не потеряны.
- Пользователь БД: **`leads`**, база: **`leads`**, пароль — как в **`docker/infra/.env`** (локально), **не хранить в репозитории**.

## Порты и хосты

| Откуда | Куда | Host | Port |
|--------|------|------|------|
| Браузер на Windows | Metabase | `localhost` | **3031** |
| Контейнер Metabase | PostgreSQL leads-db | **`propradar-leads-db`** или **`leads-db`** | **5432** |

С хоста Windows к Postgres: `localhost` **5433** (только для отладки с вашей машины; Metabase в Docker должен ходить на **5432** внутри сети).

## Проверка DNS из контейнера Metabase

После шага «Запуск tools»:

```bash
docker compose -f docker/tools/docker-compose.yml exec metabase ping -c1 propradar-leads-db
```

Если имя не резолвится, попробуйте **`leads-db`** (имя сервиса из `docker/infra/docker-compose.yml`).

## Запуск tools

Из корня репозитория (рядом с `docker/tools`):

```bash
docker compose -f docker/tools/docker-compose.yml up -d
```

Альтернатива (тот же стек через корневой `compose.yaml` и профиль **`tools`**):

```bash
docker compose --profile tools up -d metabase
```

Ожидаем **`exit 0`**. UI: **http://localhost:3031**

Переменные окружения для справки — **`docker/tools/.env.example`** (скопируйте в `.env` при необходимости; секреты не коммитить). Поля **`LEADS_DB_*`** нужны **в форме Metabase** при добавлении базы, а не обязательно в compose.

## Первый вход в Metabase

1. Откройте **http://localhost:3031**.
2. Пройдите мастер: задайте учётную запись администратора (локально, значения не коммитить).
3. Пропустите демо-данные, если предложит.

## Подключение базы leads

1. **Admin → Databases → Add database → PostgreSQL**.
2. Поля (свериться с **`docker/tools/.env.example`**):
   - **Host**: `propradar-leads-db` (или `leads-db`, если так резолвится).
   - **Port**: `5432`
   - **Database name**: `leads`
   - **Username**: `leads`
   - **Password**: как в **`docker/infra`** для `POSTGRES_PASSWORD`.
3. Сохраните. Нажмите **Test connection**. Должно быть успешно.
4. Сканирование: схема **`public`**, таблица **`leads`** (см. миграции **`001_init_leads.sql`** и **`002_add_myhome_listing_fields.sql`**). После миграций **007** и **008** в той же БД доступна **`leads_client`** (проекция **v2**) — её использует bundle дашборда в репозитории.

Никакие чужие базы (в т.ч. `dispatch-db-dev`) не подключать.

## Дашборд и SQL

Файл **`metabase/propradar_dashboard.json`** — валидный JSON с **одиннадцатью** карточками и готовым **SQL под PostgreSQL 15**. Запросы в репозитории ориентированы на проекцию **`leads_client`**: сначала **`007_create_leads_client_table.sql`**, затем **`008_recreate_leads_client_v2.sql`**, затем **`009_add_city_name_to_leads_client.sql`** (контракт после 009: **PK `(source, external_id)`**, **28** столбцов, включая **`city_name`** и **`owner_name`**, без **`lead_id`** и служебных полей старой проекции). Поле **`schema_reference`** в JSON фиксирует актуальный контракт и правило дат **`COALESCE(published_at, synced_at)`**.

В Community/OSS обычно **нет** одного пункта меню «Импорт этого JSON целиком». Рекомендуемый порядок:

1. **New → Dashboard**, название как в поле **`dashboard_title_ru`** в JSON (или своё на русском).
2. Для каждого элемента массива **`cards`**:
   - **New → Question → Native query**.
   - Выберите подключённую БД **leads**.
   - Вставьте текст из поля **`sql`**.
   - Сохраните вопрос, тип визуализации: **`display`** из JSON (`bar`, `line`, `scalar`, `table`).
   - Добавьте вопрос на дашборд (**Add questions**).

Подписи карточек на русском — поля **`title_ru`** / **`description_ru`** в JSON (и заголовки вопросов в Metabase).

### Схема `leads` и цены (миграция 006)

После **`migrations/006_add_price_gel_rename_price_usd.sql`** в таблице **`leads`**: **`price_gel`** (лари) и **`price_usd`** (доллары). Колонка **`price_total_usd`** переименована в **`price_usd`**. Уже сохранённые **Native query** в Metabase и копии SQL вне репозитория, созданные до этого, всё ещё нужно обновить: заменить **`price_total_usd`** → **`price_usd`**, при необходимости выбрать **`price_gel`** для отчётов в GEL.

### Проекция `leads_client` (миграции 007 → 008 v2 → 009) и bundle дашборда

Таблица **`leads_client`** — денормализованная проекция **`leads`** (синхронизация триггером после **008/009**). **007** создаёт первую версию; **008** пересоздаёт таблицу под **v2**; **009** добавляет **`city_name`** и **`owner_name`** из **`myhome_statement_json`**. Итоговый контракт: **PK `(source, external_id)`**, **28** клиентских столбцов, без **`lead_id`** / **`source_listing_uuid`** / языковых **`*_lang`** (см. **`migrations/008_recreate_leads_client_v2.sql`**, **`migrations/009_add_city_name_to_leads_client.sql`** и **`schema_reference`** в JSON). Текущий **`metabase/propradar_dashboard.json`**: все карточки читают **`FROM leads_client`**; средние цены — **`AVG(price_usd)`** / **`AVG(price_gel)`**; временные срезы — по **`COALESCE(published_at, synced_at)`** (в проекции нет **`created_at`**). Карточка **«Последние лиды»** (**`position` 7** в массиве **`cards`**) — таблица с **`LIMIT 20`**; **«Город»** — **`city_name`** (не **`urban_name`**), **«Имя владельца»** — **`owner_name`**. Полный SELECT — поле **`sql`** у этой карточки.

**Высота карточки и прокрутка таблицы:** задаются в UI Metabase (растянуть плитку на дашборде; опции визуализации зависят от версии; OSS может не давать «внутренний» scroll). Подробнее — поле **`operator_instructions_ru`** у соответствующей карточки в JSON.

### Таймзона

В SQL используется **`AT TIME ZONE 'UTC'`** и **`timezone('UTC', now())`** для сопоставимости с `TIMESTAMPTZ`. При смене локали в Metabase перепроверьте карточки «сегодня» и «по дням».

### Воронка статусов

В таблице **`leads.status`** хранятся строковые литералы домена (например **`new`**, **`contacted`**, **`qualified`**, **`rejected`**, **`converted`**). Это **не** набор `contact/sent/deal/lost` из продуктовой воронки без отдельной миграции — карточка 1 показывает **фактическое распределение**.

## Автоматизация дашборда (Metabase API)

После первого входа администратора и **подключения БД «PropRadar Leads»** в UI можно собрать дашборд **«PropRadar — Лиды»** без ручной расстановки карточек:

1. Задайте в окружении (см. корневой `.env.example`): **`METABASE_URL`**, **`METABASE_USER`**, **`METABASE_PASSWORD`**; при необходимости **`LEADS_DATABASE_NAME`** (по умолчанию совпадает с именем подключения в Metabase).
2. Из корня репозитория с установленными зависимостями (`pip install -e .`):  
   `python scripts/setup_metabase_dashboard.py`
3. Повторный запуск при уже существующем дашборде **«PropRadar — Лиды»** **обновляет** через API только карточки **position 7** («Последние лиды», PUT SQL) и **position 11** («Карта лидов», создать при отсутствии). Карточки **1–6** и **8–10** не меняются.
4. Если дашборда ещё нет — создаются все карточки из bundle (**1–11**) и дашборд с раскладкой.

Карточки и SQL берутся из **`metabase/propradar_dashboard.json`**. Версия Metabase должна поддерживать используемые эндпоинты (`/api/session`, `/api/card`, `/api/dashboard`, …).

**Карта (position 11):** native SQL к таблице **`leads`**, поля **`latitude`** / **`longitude`**, подписи район / комнаты / цена GEL; визуализация **`map`** (pin).

### Соответствие `title_ru` скрипту автосборки

Скрипт **`scripts/setup_metabase_dashboard.py`** находит элементы массива **`cards`** по **строгому совпадению** **`title_ru`** с литералами в коде. Если переименовать подпись в JSON без синхронного изменения скрипта, при запуске возможен **KeyError**. Канон для скаляра средней цены в USD: **`Средняя цена объекта (USD)`**.

## Админ-дашборды (мониторинг и карта)

Отдельно от **«PropRadar — Лиды»** — два дашборда для операторов/админов, только через API:

| Дашборд | JSON bundle | Назначение |
| -------- | ----------- | ---------- |
| **PropRadar — Мониторинг** | `metabase/monitoring_admin_dashboard.json` | Скаляры (synced/published), график 30 дней (две линии), воронка статусов, таблица 20 лидов |
| **PropRadar — Карта объектов** | `metabase/map_objects_dashboard.json` | Карта до 500 точек по `geo_lat`/`geo_lng` |

**Таймзона в SQL:** `Asia/Tbilisi` для срезов «сегодня» и дневных графиков.

**Запуск** (после подключения БД **PropRadar Leads** в Metabase):

1. В `.env`: **`METABASE_URL`** (prod: `https://metabase.usluga-market.ru`), **`METABASE_USER`**, **`METABASE_PASSWORD`**, при необходимости **`LEADS_DATABASE_NAME`**.
2. Из корня репозитория:  
   `python scripts/create_metabase_dashboards.py`
3. Скрипт выводит `id` и `url` обоих дашбордов. **Идемпотентность:** при повторном запуске дашборд с тем же именем удаляется (вместе с карточками) и создаётся заново.
4. **Не затрагивает** дашборд **«PropRadar — Лиды»** и **`setup_metabase_dashboard.py`**.

Общие HTTP-хелперы: **`scripts/metabase_api_common.py`**.

**Smoke (человек):** 10 плиток на мониторинге, график с двумя сериями, карта с точками в Грузии, запросы без ошибки PostgreSQL (миграции **007–009** для `owner_name` / `urban_name`).

## Критерии готовности

- `docker compose -f docker/tools/docker-compose.yml up -d` завершается без ошибки.
- **http://localhost:3031** открывается.
- База **leads** подключена, тест соединения **успешен**.
- На дашборде отображаются **одиннадцать** карточек (по bundle); запросы выполняются без ошибки PostgreSQL (ожидаются миграции **007**, **008** и **009** для актуального контракта **`leads_client`**).
- **«Последние лиды»:** колонки ID, адрес, район, микрорайон, телефон, цены, площадь, **комнаты**.
- **«Карта лидов»:** точки myhome с координатами на карте.

## Остановка (опционально)

```bash
docker compose -f docker/tools/docker-compose.yml down
```

Том **`metabase_data`** сохраняет настройки Metabase; данные лидов остаются в **`docker/infra`**.
