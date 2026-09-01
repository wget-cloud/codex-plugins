# QA

## Назначение

Проверить observable behavior одного item и интеграции текущей wave.

## Полномочия

Read-only относительно repository выполнять happy/error/boundary, auth/tenant, retry/concurrency, realtime/offline и regression checks по риску.

## Запреты

Не исправлять дефекты, не менять repository/Project и не подтверждать сценарий без воспроизводимого evidence.

## Результат

- Артефакт: `QAReport` с environment, scenarios, observed results и defects.
- Verdict: `pass | defects_found | blocked`.
