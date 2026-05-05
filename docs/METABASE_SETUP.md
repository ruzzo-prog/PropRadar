# Metabase для PropRadar

Инструкция для оператора: поднять Metabase в `docker/tools`, подключить **leads-db**, собрать дашборд по SQL из `metabase/propradar_dashboard.json`.

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
4. Сканирование: схема **`public`**, таблица **`leads`** (см. миграции **`001_init_leads.sql`** и **`002_add_myhome_listing_fields.sql`**).

Никакие чужие базы (в т.ч. `dispatch-db-dev`) не подключать.

## Дашборд и SQL

Файл **`metabase/propradar_dashboard.json`** — валидный JSON с шестью карточками и готовым **SQL под PostgreSQL 15** и фактической схемой `leads`.

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

После **`migrations/006_add_price_gel_rename_price_usd.sql`** в таблице **`leads`**: **`price_gel`** (лари) и **`price_usd`** (доллары). Колонка **`price_total_usd`** переименована в **`price_usd`**. Файл **`metabase/propradar_dashboard.json`** в репозитории уже использует **`price_usd`** (ретро-закрытие замечаний **Diff Check** после P1 hotfix). Уже сохранённые **Native query** в Metabase и копии SQL вне репозитория, созданные до этого, всё ещё нужно обновить: заменить **`price_total_usd`** → **`price_usd`**, при необходимости выбрать **`price_gel`** для отчётов в GEL.

### Таймзона

В SQL используется **`AT TIME ZONE 'UTC'`** и **`timezone('UTC', now())`** для сопоставимости с `TIMESTAMPTZ`. При смене локали в Metabase перепроверьте карточки «сегодня» и «по дням».

### Воронка статусов

В таблице **`leads.status`** хранятся строковые литералы домена (например **`new`**, **`contacted`**, **`qualified`**, **`rejected`**, **`converted`**). Это **не** набор `contact/sent/deal/lost` из продуктовой воронки без отдельной миграции — карточка 1 показывает **фактическое распределение**.

## Автоматизация дашборда (Metabase API)

После первого входа администратора и **подключения БД «PropRadar Leads»** в UI можно собрать дашборд **«PropRadar — Лиды»** без ручной расстановки карточек:

1. Задайте в окружении (см. корневой `.env.example`): **`METABASE_URL`**, **`METABASE_USER`**, **`METABASE_PASSWORD`**; при необходимости **`LEADS_DATABASE_NAME`** (по умолчанию совпадает с именем подключения в Metabase).
2. Из корня репозитория с установленными зависимостями (`pip install -e .`):  
   `python scripts/setup_metabase_dashboard.py`
3. Повторный запуск при уже существующем дашборде с этим именем завершится с **предупреждением** и **кодом 0** (дубль не создаётся).

Карточки и SQL берутся из **`metabase/propradar_dashboard.json`**. Версия Metabase должна поддерживать используемые эндпоинты (`/api/session`, `/api/card`, `/api/dashboard`, …).

## Критерии готовности

- `docker compose -f docker/tools/docker-compose.yml up -d` завершается без ошибки.
- **http://localhost:3031** открывается.
- База **leads** подключена, тест соединения **успешен**.
- На дашборде отображаются шесть карточек; запросы выполняются без ошибки PostgreSQL.

## Остановка (опционально)

```bash
docker compose -f docker/tools/docker-compose.yml down
```

Том **`metabase_data`** сохраняет настройки Metabase; данные лидов остаются в **`docker/infra`**.
