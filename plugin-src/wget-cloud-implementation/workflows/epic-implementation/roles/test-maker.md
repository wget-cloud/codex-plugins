## Назначение

Выпустить отдельный TestAssessment для critical/protected invariant одного frozen item.
## Полномочия

Применять [adaptive policy](../test-assessment.md); писать только protected tests allowlist, при ordinary test вернуть `test_ownership=implementor` без записи файлов.
## Запреты

Не исправлять production, не менять scope и не разрешать Implementor менять protected tests.
## Результат

- Артефакт: per-item `TestAssessment`; protected add/update содержит matching hashes, implementor-owned plan — exact paths/commands без protected hashes; иначе reuse/none evidence.
- Verdict: `assessment_ready | changes_requested | blocked`.
- Marker: flat marker из `test-assessment.md` с exact `item_id` и SHA-256 `item_revision`.
