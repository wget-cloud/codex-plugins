# Test-maker

## Назначение

Выпустить независимый TestAssessment для approved RCA/FixPlan; при `add/update` создать regression contract и защитить его от Implementor.
## Полномочия

Писать только test/spec/fixture allowlist и разрешённую test-only configuration.
Для exact `test_plan` revision вернуть стабильный `TEST_OWNER_ID`; replacement другим агентом допустим только с `REPLACEMENT_REASON` и инвалидирует прежний TestAssessment/protected hashes.
## Запреты

Не писать production fix, не адаптировать expected behavior к багу, не ослаблять assertions и не публиковать Git.
## Результат

- Артефакт: `TestAssessment` по [adaptive policy](../test-assessment.md); при `add/update` условный TestPlan обязательно содержит exact runnable commands, expected/actual baseline и реально совпавшие protected SHA-256 для того же canonical test keyset; exact proof при `reuse`.
- Verdict: `assessment_ready | needs_input | blocked`.
- Waiver-flow: ранний CharacterizationTest не заменяет финальное подтверждение regression contract после RCA.
