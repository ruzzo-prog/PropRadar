---
name: documentor-doc-style
description: Enforces documentation formatting standards for project docs, release notes, and status files. Use when the user asks to write, edit, or review documents, changelogs, runbooks, governance docs, or PropRadar_STATUS updates.
---

# Documentor Doc Style

## Purpose

Apply consistent formatting and structure for project documentation created by the `@documentor` workflow.

## When To Use

Use this skill when working on:
- `Docs/PropRadar_STATUS.md`
- `CHANGELOG.md` (repository root)
- `README.md`
- `Docs/*.md`
- governance and release documentation

## Core Formatting Rules

1. Write in Russian unless the target file is explicitly English.
2. Keep technical tone: concise, factual, no marketing wording.
3. Preserve existing project terminology and canonical names.
4. Use consistent Markdown hierarchy: `#` -> `##` -> `###` without skipping levels.
5. Keep lists flat (no nested bullets unless absolutely required).
6. Use backticks for paths, commands, endpoints, env vars, and code identifiers.

## Section Design Rules

For status or release documents:
1. Start with current state or verdict.
2. Then list validated changes (what was done and scope boundaries).
3. Then test evidence and checks.
4. End with conditions, risks, or next manual actions.

For technical docs:
1. Problem/context.
2. Decision or behavior.
3. Constraints and non-goals.
4. Verification method.

## Writing Style Rules

- Prefer short paragraphs (1-3 lines).
- One bullet = one fact.
- Avoid ambiguous wording like "примерно", "наверное", "возможно", unless uncertainty is required.
- Do not duplicate the same statement in multiple sections.
- Do not add historical noise unrelated to the current change.

## Mandatory Quality Checklist

Before finalizing, verify:
- [ ] Terminology matches project canon.
- [ ] Scope boundaries are explicitly stated ("без ...", "only ...").
- [ ] Test evidence is present when documenting completed changes.
- [ ] Manual steps are marked as manual and assigned to human.
- [ ] Dates, states, and identifiers are consistent across the file.
- [ ] Markdown renders cleanly (headers, lists, code formatting).

## Output Template

Use this base template when adding a new status entry:

```markdown
## YYYY-MM-DD (scope)

- Контекст: кратко что менялось.
- Реализация: ключевые изменения и явные границы scope.
- Проверка: какие тесты/проверки выполнены и результат.
- Документация: какие файлы обновлены.
- Условия релиза: что проверяет человек вручную (если применимо).
```

## Safety Rules

- Never invent test results.
- Never mark automation PASS if it was not executed.
- Keep `PASS WITH CONDITIONS` wording when manual smoke/deploy is required.
- Do not change business logic in docs; only document confirmed behavior.
