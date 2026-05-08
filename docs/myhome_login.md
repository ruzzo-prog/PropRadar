# Автологин myhome (TNET) — `scripts/myhome_login.py`

## Назначение

Скрипт **`scripts/myhome_login.py`** выполняет вход в экосистему **TNET / myhome.ge** через браузер **Playwright**, сохраняет **`storage_state`** в JSON. Этот файл сессии нужен **playwright-worker** (и локальным прогонам enricher) для обхода **reCAPTCHA v3** и вызова **`phone/show`** — без живой сессии на **`.tnet.ge`** обогащение телефона ненадёжно.

Секреты (**`MYHOME_EMAIL`**, **`MYHOME_PASSWORD`**) не логируются; в лог не должны попадать значения **`AccessToken`** из URL.

## Переменные окружения

| Переменная | Назначение |
|------------|------------|
| **`MYHOME_EMAIL`** | Учётная запись для формы логина. |
| **`MYHOME_PASSWORD`** | Пароль. |
| **`MYHOME_SESSION_PATH`** | Путь к файлу **`storage_state`** (JSON). Если не задан — значение из настроек приложения / дефолт в compose. |
| **`MYHOME_LOGIN_URL`** | (Опционально) переопределение URL страницы входа. |

## Путь к сессии и volume в Docker

- В **`docker/app/docker-compose.yml`** для **`playwright-worker`** по умолчанию:  
  **`MYHOME_SESSION_PATH`** = **`/data/adapter_sessions/myhome_session.json`**.
- Том **`adapter_playwright_sessions`** смонтирован в контейнер как **`/data/adapter_sessions`** — сессия **переживает** пересоздание контейнера, если том не удалять.

Проверка наличия файла (без вывода содержимого):

```bash
docker exec <container> test -f /data/adapter_sessions/myhome_session.json && echo OK
```

## Архитектура входа: **auth.tnet.ge** и SSO TNET

1. **Форма логина** на **auth.tnet.ge** (React SPA):
   - поле email часто **`input[name="Email"]`** (регистр **E**), не обязательно **`type="email"`**;
   - пароль: **`input[type="password"]`** (и другие кандидаты в скрипте).
2. После сабмита вызывается API вида **`accounts.tnet.ge/.../user/auth`** → в ответе **JWT** (**AccessToken**, **RefreshToken**).
3. Браузер перенаправляется на **`auth.myauto.ge`** — промежуточный шаг SSO TNET.
4. В **headless** финальный клиентский редирект на **myhome.ge** иногда **не выполняется**, хотя авторизация уже успешна. В скрипте признаком успеха считается:
   - URL на **myhome.ge** вне страниц логина, **или**
   - **`auth.myauto.ge`** с параметром **`AccessToken`** в query (без логирования значения).
5. **Куки** сессии (в т.ч. **AccessToken** / **RefreshToken** для домена **`.tnet.ge`**) попадают в сохранённый **`storage_state`** при успешном завершении сценария.

## TTL сессии

- У **RefreshToken** в типичной конфигурации TNET срок жизни порядка **~120 суток** (точное значение смотрите в **`exp`** полей JWT в payload — **не** публикуйте токены в тикеты/логи).
- До истечения срока переиздавать **`myhome_login.py`** нужно только при смене пароля или отзыве сессии.

## Признак валидной сессии (концептуально)

- В сохранённом **`storage_state`** есть **cookies** для домена **`.tnet.ge`**, в т.ч. признаки сессии, достаточные для запросов к защищённым эндпоинтам myhome (детальная структура зависит от выдачи TNET).
- Практическая проверка: успешный прогон фазы **`phone`** воркером для тестового лида или непустой файл сессии после **`POST /login`** / ручного **`python -m scripts.myhome_login`**.

Пример **без** печати секретов — только факт наличия ключей (идея для одноразовой диагностики):

```bash
docker exec <container> python3 -c "import json, pathlib; p=pathlib.Path('/data/adapter_sessions/myhome_session.json'); d=json.loads(p.read_text()); c=d.get('cookies',[]); print('cookies', len(c))"
```

## Headless и загрузка SPA

- На сервере без дисплея скрипт использует **`headless=True`** для Chromium (см. реализацию в **`scripts/myhome_login.py`**).
- Страница логина — **React SPA**: после **`page.goto`** используется **`wait_until="networkidle"`** и короткая пауза перед поиском полей, иначе поля могут отсутствовать в DOM.

## См. также

- `docs/playwright_worker.md` — запуск воркера и профили Compose.
- `docs/phone_extraction.md` — телефон и Cloudflare.
- `docs/DEPLOY_SERVER.md` — секреты **`MYHOME_*`** на сервере.
