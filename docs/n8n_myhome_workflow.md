# n8n: расписание myhome (список ID → парсер → discover ↔ WhatsApp → mark-rejected)

Цель — оркестрация без секретов Evolution API в Python; креды только в n8n / переменных окружения инстанса n8n.

## Параметры расписания

- **Hourly:** Cron `0 * * * `* или интервал 1 час.
- **Каждые 6 ч:** `0 */6 * * `* или интервал 6 часов.
- **Daily:** например `0 8 * * `* (08:00) или интервал 24 часа.

Выбор — параметр workflow (переменная `SCHEDULE_MODE` или отдельные workflow-копии).

## Переменные (пример)


| Имя              | Назначение                                                        |
| ---------------- | ----------------------------------------------------------------- |
| `PROPRADAR_ROOT` | Корень репозитория на хосте n8n (для Execute Command).            |
| `PYTHON`         | Интерпретатор с установленным пакетом (`python` или путь к venv). |
| Evolution        | URL, instance, API key — только в узлах HTTP/WhatsApp.            |


Команды ниже предполагают `cd $PROPRADAR_ROOT` и `PYTHONPATH=src` (как в `pyproject.toml` для тестов). Для Windows задайте эквивалент в Execute Command.

## Цепочка шагов

### 1) Список ID (для сверки «исчезнувших»)

Полная выгрузка ID с API (обязательно **без** ограничения 7 дней, иначе старые объявления ошибочно попадут в «исчезнувшие»):

```bash
PYTHONPATH=src python scripts/fetch_myhome_ids.py --full --output json
```

Результат: JSON-массив строк `["123", "456", ...]`. Сохраните в файл или передайте следующим узлам.

Опционально для лёгкого «окна» по дате публикации (не для discover исчезнувших):

```bash
PYTHONPATH=src python scripts/fetch_myhome_ids.py --since-days 7 --output json
```

По умолчанию (без `--full` и без `--since-days`): окно **7 суток** — удобно для отладки, **не** использовать для шага discover.

### 2) Новые лиды по явному списку ID

В n8n: получить множество `existing` из БД (SQL / отчёт) и вычислить `new_ids = api_ids - existing`. Записать `new_ids` в временный файл и вызвать:

```bash
PYTHONPATH=src python scripts/run_myhome_parser.py --ingest-ids-json /tmp/myhome_new_ids.json
```

JSON — массив чисел или строк. Каждый ID тянется через `GET /v1/statements/{id}` (уже существующая логика обогащения совместима с обогащением/enricher).

Если `new_ids` пустой, шаг можно пропустить.

Legacy-режим (только первая страница списка API без входного списка):

```bash
PYTHONPATH=src python scripts/run_myhome_parser.py
```

### 3) Исчезнувшие объявления (только JSON, без записи в БД)

Вариант A — передать файл из шага 1:

```bash
PYTHONPATH=src python scripts/sync_myhome_status.py discover --api-ids-json /tmp/myhome_api_ids.json
```

Вариант B — скрипт сам запросит API (тот же полный список, что и `--full`):

```bash
PYTHONPATH=src python scripts/sync_myhome_status.py discover --fetch-api
```

Ответ: `{"disappeared": [{"external_id","phone","address","owner_name","lead_id"}, ...], "counts": {...}}`.

### 4) WhatsApp (Evolution API)

Для каждого элемента `disappeared`:

- Номер: `phone` из JSON (формат и валидация — в n8n; при необходимости нормализация под вашу ноду).
- Текст (шаблон):

```text
Объявление [address] больше не найдено на myhome.ge. Если оно было продано, пожалуйста, подтвердите.
```

Подставьте фактический `address`; при пустом адресе используйте запасной текст (например, «по объявлению [external_id]»).

Отправку выполняет только n8n (узел Evolution), не Python.

### 5) Фиксация в БД после успешной отправки

Сохраните список `external_id`, по которым сообщение реально ушло, в файл и вызовите:

```bash
PYTHONPATH=src python scripts/sync_myhome_status.py mark-rejected --ids-json /tmp/notified_ids.json --reason disappeared_from_api
```

Команда обновляет только лиды `source=myhome`, `status=new` → `rejected`, выставляет `status_reason` (по умолчанию `disappeared_from_api`).

## Логирование и счётчики

- Выход `run_myhome_parser.py`: `parsed`, `new`, `errors`.
- Выход `sync_myhome_status.py discover`: `counts`.
- Выход `mark-rejected`: `updated`.
- Агрегируйте в ноде «Set» / «Merge» или пишите в syslog/файл через Execute Command.

## Миграция БД

Перед использованием `status_reason` примените `migrations/010_add_status_reason_to_leads.sql` к `leads-db`.

## Экспорт workflow

При необходимости добавьте в репозиторий экспорт n8n в `scripts/n8n_myhome_sync.json` вручную из UI (опционально; узлы с секретами вычищайте перед коммитом).