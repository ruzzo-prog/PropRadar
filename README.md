# PropRadar

Автоматизированная система генерации лидов с рынка недвижимости Грузии.

Система парсит объявления от частных продавцов, устанавливает контакт через WhatsApp,
собирает структурированные данные и передаёт готовые лиды агентствам недвижимости.

---

## Пайплайн

```
[1] Парсинг          — мониторинг объявлений (myhome.ge, SS.ge)
        ↓
[2] Фильтрация       — скоринг, отсев агентств, дедупликация
        ↓
[3] Коммуникация     — WhatsApp-бот: согласие → сбор данных
        ↓
[4] Монетизация      — передача агентствам, трекинг сделок
```

---

## Стек

| Слой | Технология |
|---|---|
| Парсинг | Python + Playwright |
| База данных | PostgreSQL (`leads-db`, порт 5433) |
| WhatsApp | Evolution API (Docker, self-hosted) |
| Оркестрация | n8n (self-hosted) |
| Дашборд | Metabase (Docker, порт 3030) |

---

## Структура репозитория

```
PropRadar/
├── .cursor/                  # AI-агенты и правила
│   ├── agents/               # @architect, @dispatcher, @review и др.
│   ├── rules/                # Rules-for-AI.mdc
│   └── skills/               # Навыки агентов
├── docs/                     # Канонические документы
│   ├── AI_GOVERNANCE.md      # Процесс работы агентов и канон v1.0
│   ├── INGRESS_ARCHITECTURE.md  # Архитектурные инварианты
│   └── PropRadar_STATUS.md   # Актуальный статус проекта
├── CHANGELOG.md              # История изменений
└── README.md                 # Этот файл
```

> Код (src/, tests/, docker/) появится по мере реализации этапов.

---

## Источники данных

- **myhome.ge** — REST API (`api-statements.tnet.ge`), заголовок `X-Website-Key: myhome`
- **SS.ge** — Playwright (JavaScript-рендеринг, телефон за reCAPTCHA v3)

---

## Процесс разработки

Все изменения — только через цепочку AI-агентов по `docs/AI_GOVERNANCE.md`.

Три точки контроля человека:
1. Одобрение Fix Plan
2. Деплой
3. Smoke-тест

Подробнее: [`docs/AI_GOVERNANCE.md`](docs/AI_GOVERNANCE.md)

---

## Статус

Актуальный статус проекта: [`docs/PropRadar_STATUS.md`](docs/PropRadar_STATUS.md)
