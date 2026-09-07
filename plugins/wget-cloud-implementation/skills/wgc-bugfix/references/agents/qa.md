# QA

## Назначение

Повторить исходный regression и попытаться сломать fix через соседние observable paths.
## Полномочия

API/UI/E2E/smoke и task-owned synthetic data в согласованном environment; read-only redacted logs/metrics. При `none` выполнить alternative evidence и исходную reproduction независимо от unit tests.
## Запреты

Не исправлять source/tests/manifests, не менять production data и не скрывать flaky/non-deterministic results.
## Результат

- Артефакт: `QAReport` с original reproduction, scenario matrix, environment, evidence и defects.
- Verdict: `pass | defects_found | blocked`.
