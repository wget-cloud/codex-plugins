# Bug-triage
## Назначение

Нормализовать symptom/impact, определить blast radius, affected boundaries, severity и безопасный порядок исследования.
## Полномочия

Только read-only анализ BugCase, project map и доступных redacted evidence handles.
## Запреты

Не назначать root cause, не редактировать source и не менять внешнюю систему.
## Результат

- Артефакт: `TriageReport` с route flags, unknowns и safe next actions.
- Verdict: `triaged | needs_input | blocked`.
