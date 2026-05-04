---
name: engineer-repairman-emergency-hotfix-report
description: Ведет emergency-проход для агента engineer-repairman по каноническому пути P0/P1 инцидентов и формирует формализованный доклад после hotfix. Использовать, когда нужен срочный фикс в проде, стабилизация сервиса и единый post-hotfix отчет с рисками и следующими шагами.
---

# Engineer Repairman Emergency Hotfix Report

## Когда применять

Применяй этот skill, если запрос связан с:

- P0/P1 прод-инцидентом и срочным восстановлением работоспособности;
- выполнением emergency path через `@engineer-repairman`;
- подготовкой формального доклада после hotfix для передачи дальше по цепочке.

Не применяй для плановых фич, рефакторинга или изменений без инцидента.

## Канонический Emergency Path

Используй только эту цепочку:

1. `@engineer-repairman` — диагностика, hotfix, первичная валидация.
2. `@tester` — проверка результата (PASS/FAIL).
3. `@documentor` — обновление документации и `Docs/PropRadar_STATUS.md`.
4. `@process-guard` (Diff Check) — проверка соответствия diff и governance.
5. `@release-check` — финальный pre-flight вердикт.

После стабилизации зафиксируй обязательный ретроспективный проход через `@architect` + `@process-guard (Plan Check)` не позднее 1 рабочего дня.

## Алгоритм работы engineer-repairman

1. **Подтверди аварийный режим**
   - Зафиксируй признак инцидента (симптом, влияние, приоритет P0/P1).
2. **Локализуй причину**
   - Выдели минимальный проблемный участок.
   - Исключи побочные изменения вне зоны аварии.
3. **Внеси минимальный hotfix**
   - Правь только то, что нужно для восстановления сервиса.
   - Не меняй бизнес-канон и архитектуру шире аварийного контекста.
4. **Проверь восстановление**
   - Подтверди, что критичный сценарий снова работает.
   - Зафиксируй остаточные риски и технический долг.
5. **Передай по цепочке**
   - Сразу инициируй `@tester`, затем дальнейшие обязательные шаги.

## Запреты в emergency-режиме

- Нельзя добавлять "улучшения заодно", не связанные с инцидентом.
- Нельзя пропускать `@tester`, даже если hotfix кажется очевидным.
- Нельзя завершать задачу без обновления документации и статуса.
- Нельзя считать инцидент закрытым без `@release-check PASS`.

## Формат доклада после hotfix

Всегда возвращай доклад в единой структуре:

```markdown
Emergency Hotfix Report
Incident: <ID/название>
Severity: P0 | P1
Status: Mitigated | Monitoring | Escalated
Owner: @engineer-repairman

Impact:
- <что сломалось>
- <кого/что затронуло>

Root Cause (current understanding):
- <краткая первопричина или "Under investigation">

Hotfix Applied:
- Scope: <какие компоненты затронуты>
- Change: <что изменено минимально>
- Safety: <почему изменение безопасно для канона>

Validation:
- Critical Scenario: PASS | FAIL
- Evidence: <лог/проверка/симптом после фикса>
- Residual Risk: Low | Medium | High

Next Mandatory Steps:
1. @tester -> PASS/FAIL
2. @documentor -> Docs/*.md + Docs/PropRadar_STATUS.md
3. @process-guard -> Diff Check
4. @release-check -> Release Verdict

Retro Requirement:
- Required: Yes
- Deadline: <дата/время, не позже 1 рабочего дня>
- Path: @architect -> @process-guard (Plan Check)
```

## Критерии качества доклада

- Есть однозначный статус инцидента: `Mitigated`, `Monitoring` или `Escalated`.
- Есть явная граница hotfix scope (что включено/что исключено).
- Есть доказательство валидации критического сценария.
- Есть остаточный риск и обязательные следующие шаги.
- Указан дедлайн ретроспективного прохода.
