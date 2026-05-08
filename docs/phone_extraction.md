# Телефон объявления myhome.ge — контур и ограничения

Актуальное правило PropRadar: **номер продавца для myhome.ge получается только через Playwright** (карточка объявления, **reCAPTCHA v3**, ответ **`phone/show`**), в связке с **валидной сессией** TNET (см. `docs/myhome_login.md` и `docs/playwright_worker.md`). Прямой HTTP к публичной HTML-странице карточки **не используется** в проде.

---

## Почему HTTP не работает

- Сайт **`www.myhome.ge`** защищён **Cloudflare Managed Challenge**.
- Простые HTTP-клиенты (**`httpx`**, **`curl`**, **`requests`**) с типичными заголовками получают **403** или страницу challenge **с любого IP** (проверено **2026-05-09**: локально и с сервера).
- Обход challenge для автоматического скачивания HTML **вне** полноценного браузера в этот контур **не входит** и противоречит устойчивости и ToS.
- **Итог:** извлечение телефона из HTML (**`__NEXT_DATA__`**, JSON-LD) по HTTP **не применяется**; рабочий путь — **Playwright + авторизованная сессия** (storage state).

---

## Историческая диагностика (`__NEXT_DATA__`)

В ходе исследования **2026-05-09** проверялась гипотеза: номер доступен во встроенном JSON страницы листинга (**`__NEXT_DATA__`** → ветка **`statement.comment`**, regex **`+995`…**), с fallback на **JSON-LD**. Диагностика в контролируемой среде (без Cloudflare или с браузером агента) могла **не** воспроизвести блокировку.

Этот раздел оставлен как **архив рассуждений**. Код **`phone_extractor.py`** и юнит-тесты к нему **удалены** после отката; канон **`docs/AI_GOVERNANCE.md`** (§9) и **`docs/INGRESS_ARCHITECTURE.md`** снова описывают **Playwright-only** путь для телефона.

---

## Оркестрация

- n8n вызывает **`POST http://playwright-worker:8001/enrich`** с **`{"adapter":"myhome","phase":"phone"}`** — ожидается **HTTP 202**, без polling (см. `docs/INGRESS_ARCHITECTURE.md`).
- Паузы и порядок шагов в браузере **не сокращать** без отдельного решения (rate / reCAPTCHA).

## См. также

- `src/parsers/adapters/myhome/phone.py` — текущий **`MyHomePhoneEnricher`** (только Playwright).
- `docs/myhome_login.md` — сохранение сессии.
- `docs/playwright_worker.md` — деплой воркера.
