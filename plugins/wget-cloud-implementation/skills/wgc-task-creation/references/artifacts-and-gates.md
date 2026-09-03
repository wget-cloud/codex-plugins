# Артефакты и gates

## TaskRequest

Содержит revision, objective, actors, business workflow, exclusions, target Project, repositories, labels, known decisions, unknowns и creation authorization.

## AuditReport

Для каждой capability: `working | partial | placeholder | absent | defective`, evidence handles, business impact, blockers и confidence. Проценты всегда обозначаются как оценка продуктовой готовности, не coverage.

## ProductSpec

Описывает lifecycle, state transitions, ownership, money/inventory rules, permissions, exceptions и explicit user decisions.

## BacklogPlan

Для каждого item: code, title, type, owner repo, label, parent, goal, business logic, cases, requirements, acceptance, dependencies, priority, initial status, evidence и provisional `test_policy` из [test-assessment.md](test-assessment.md). Политика живёт в managed body/AC, не в новом Project field; окончательное решение принимает Test-maker при implementation.

## BacklogReview

Verdict `approved | changes_requested | needs_input`, blocking findings с item codes и проверка duplicate/scope/dependency/acceptance/Project schema.

## MutationPlan

Для каждой write содержит exact Project/repository/operation/fields, managed marker/hash, duplicate fingerprint и expected current state для compare-and-swap.

## BacklogReport

Project/roadmap URLs, created/reused/updated counts, hierarchy, priority distribution, ordering verification, labels, unresolved decisions и skipped mutations.

## Machine result

Каждый субагент завершает одной строкой:

`WGC_AGENT_RESULT: {"role":"<role>","verdict":"<allowed-verdict>","phase":"","input_revision":"<exact revision>"}`
