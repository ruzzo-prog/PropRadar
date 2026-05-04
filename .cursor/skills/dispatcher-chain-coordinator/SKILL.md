---
name: dispatcher-chain-coordinator
description: Управляет канонической цепочкой агентов: онбординг, auto-advance при PASS, stop-on-fail, формирование промтов для каждого шага. Использовать когда нужно запустить или продолжить цепочку изменений через @dispatcher.
---

# Dispatcher Chain Coordinator

## Когда применять

Применяй этот skill, если запрос связан с:

- запуском канонической цепочки изменений;
- координацией шагов между агентами;
- формированием промтов для конкретного шага цепочки;
- обработкой PASS/FAIL артефактов от агентов.

Не применяй для реализации кода или архитектурного аудита.

## Онбординг (обязательно перед запуском)

Перед запуском цепочки прочитать:
- `Docs/PropRadar_STATUS.md` — единственный источник статуса (`Docs/AI_GOVERNANCE.md` §8)
- `Docs/AI_GOVERNANCE.md` — §5 цепочка, §4 роли

Опционально: корневой `CHANGELOG.md`, если файл существует.

Если недоступны обязательные документы (`Docs/PropRadar_STATUS.md`, `Docs/AI_GOVERNANCE.md`) — STOP: `Missing: [Onboarding Docs]`.

## Каноническая последовательность

@architect -> Fix Plan (остановка для одобрения человеком)  
@process-guard -> Plan Check  
@review -> реализация  
3.5 Scanner Check -> опционально по решению человека  
@tester -> QA  
@documentor -> Docs/*.md + Docs/PropRadar_STATUS.md  
@process-guard -> Diff Check  
@release-check -> финальный вердикт

## Правила auto-advance

При PASS на любом шаге — В ТОМ ЖЕ ОТВЕТЕ:
1. Зафиксировать: «Шаг N — PASS».
2. Сформулировать промт для следующего шага.
3. Вызвать следующего агента.

Запрещено: выдавать PASS и ждать реакции человека.  
Запрещено: спрашивать «продолжить?» после PASS.

## Точки остановки (ждать человека)

- FAIL на любом шаге.
- NEEDS CONFIRMATION от любого агента.
- После шага 0 (@architect Verdict: PASS) — показать Fix Plan полностью, запросить `одобряю` / `approve`.
- Перед @tester — если diff не docs-only, уведомить о необходимости Scanner Check.

## Stop-on-fail

При FAIL:
- Остановить цепочку немедленно.
- Зафиксировать шаг и артефакт FAIL.
- Запросить решение человека.

Исключение — @architect Verdict: FAIL:
- Не эскалировать к человеку сразу.
- Извлечь причины FAIL, вернуть @architect на доработку с точным списком требований.
- Повторять до 2 последовательных FAIL, только потом эскалация.

## Правила формирования промтов

Промт содержит ЧТО сделать (цель, контекст, артефакты предыдущих шагов).  
Промт НЕ содержит КАК сделать (алгоритмы, строки кода, реализацию).

Для шага 0 (@architect):
- Описание задачи + список затронутых файлов/областей + контекст.
- Секции Fix Plan (Диагноз, План изменений, Зона влияния, Verdict) — это ВЫХОД @architect, не вход.
- Нестандартные секции (Risks, Test Plan и т.д.) в промте к @architect запрещены.

## Авто-FAIL триггеры

- Попытка перейти к @review без PASS от @process-guard (Plan Check).
- Попытка перейти к @release-check без PASS от @process-guard (Diff Check).
- Деплой без финального вердикта @release-check.
- Чтение/запись memory-bank (`.cursor/memory-bank/*`) — запрещено.

## Формат итогового пакета

```markdown
Status by step:
0) @architect — PASS/FAIL/SKIP
1) @process-guard Plan Check — PASS/FAIL/SKIP
2) @review — PASS/FAIL/SKIP
3.5) Scanner Check — PASS/SKIP
4) @tester — PASS/FAIL/SKIP
5) @documentor — PASS/FAIL/SKIP
6) @process-guard Diff Check — PASS/FAIL/SKIP
7) @release-check — PASS/FAIL/SKIP

Summary:
- 1-5 пунктов что сделано

Final Verdict: PASS | FAIL

Rollback note:
- Что откатить при проблеме

Deploy command (recommendation only):
- <команда деплоя — только рекомендация для человека>
```
