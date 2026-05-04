---
name: release-check
description: Выполняет pre-flight проверку перед релизом с фокусом на P0-блокеры и выдает формализованный Release Verdict. Использовать, когда нужно принять решение о готовности к деплою после Diff Check и QA.
---

# Release Check P0 Verdict

## Когда применять

Применяй этот skill, если запрос связан с:

- финальным go/no-go решением перед деплоем;
- проверкой P0-блокеров после `@process-guard` Diff Check;
- выпуском формального заключения `Release Verdict`.

Не применяй для реализации кода или изменения Fix Plan.

## Входные артефакты

Перед вердиктом собери и проверь:

1. Итог `@process-guard` (Diff Check).
2. Итог `@tester` (PASS/FAIL + evidence).
3. Обновления `@documentor` (`CHANGELOG.md` в корне репозитория, `Docs/PropRadar_STATUS.md`, релизные заметки в `Docs/`).
4. Краткий список изменений релиза (scope и риски).

Если артефактов недостаточно, вердикт не может быть `PASS`.

## Чеклист P0-блокеров

Проверь каждый пункт явно:

1. **Governance chain complete**
   - Нет пропущенных обязательных шагов канонической цепочки.
2. **Security blockers**
   - Нет секретов в diff, отключенной валидации, опасных bypass/fallback.
3. **Critical tests**
   - Обязательные тесты завершены успешно; нет незакрытых `FAIL` по целевому scope.
4. **Contract and data safety**
   - Нет невалидированных breaking changes API/схемы/миграций.
5. **Deploy safety**
   - Есть понятный путь отката или безопасный rollback-сценарий.
6. **Observability**
   - Достаточно логов/метрик для обнаружения регрессий после релиза.
7. **Docs and operator readiness**
   - Документация и статус актуальны; ручной smoke-план указан.

## Авто-FAIL триггеры

Любой пункт ниже дает немедленный `Release Verdict: FAIL`:

- отсутствует `@process-guard` Diff Check PASS;
- отсутствует `@tester` PASS по обязательному scope;
- обнаружены P0 security риски (секреты, ослабление auth/validation, небезопасный обход);
- не завершены обязательные обновления документации/статуса;
- нет безопасного rollback для рискованных изменений;
- есть критичные открытые дефекты без принятого mitigation-плана.

## Формат Release Verdict

Всегда возвращай результат строго в этом формате:

```markdown
Release Check: <краткое название релиза>
Release Verdict: PASS | PASS WITH CONDITIONS | FAIL
Confidence: High | Medium | Low

P0 Checklist:
- [PASS/FAIL] Governance chain complete: <краткое обоснование>
- [PASS/FAIL] Security blockers: <краткое обоснование>
- [PASS/FAIL] Critical tests: <краткое обоснование>
- [PASS/FAIL] Contract and data safety: <краткое обоснование>
- [PASS/FAIL] Deploy safety: <краткое обоснование>
- [PASS/FAIL] Observability: <краткое обоснование>
- [PASS/FAIL] Docs and operator readiness: <краткое обоснование>

Blocking Findings:
1. <блокер или "None">

Conditions Before Deploy:
1. <обязательное условие или "None">

Manual Smoke Plan:
1. <ключевой smoke-шаг 1>
2. <ключевой smoke-шаг 2>

Decision:
- Deploy Allowed: Yes/No
- Next Step: <например "@release-check PASS -> человек деплоит" или "вернуть в @review">
```

## Политика строгости

- Тон: технический, проверяемый, без размытых формулировок.
- При `FAIL` всегда указывай конкретные блокеры и маршрут возврата.
- `PASS WITH CONDITIONS` разрешен только если нет P0-блокеров и условия не меняют код.
- Не подменяй verdict общими фразами: решение должно быть однозначным.

## Быстрая самопроверка

- [ ] Все P0-пункты чеклиста оценены явно.
- [ ] Авто-FAIL триггеры проверены.
- [ ] Вердикт согласован с фактами и подтвержден evidence.
- [ ] Указаны условия перед деплоем и следующий шаг.
