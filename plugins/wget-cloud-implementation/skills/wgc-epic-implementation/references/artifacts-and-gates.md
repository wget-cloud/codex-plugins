# Артефакты и gates

## ProjectSnapshot

Project identity/schema revision, selected item identity/status/priority/parent/dependencies/linked delivery и existing conflicts.

## EpicRun

Objective, selected/excluded items, delivery authority, repositories, concurrency cap, stop conditions, product decisions и target environment.

## ProductAcceptance

В phase `scope`: item-by-item accepted AC, ambiguities, explicit decisions и rejected interpretations. В phase `outcome`: наблюдаемый результат каждого selected item после QA и его соответствие business outcome.

## ImplementationDAG

Atomic slices, owners, paths, contracts, migrations, minimum test criticality, docs, waves, rollback and delivery order.

## FrozenSelectedItems и TestAssessment

Project Manager scope marker фиксирует максимум 100 `selected_items[{item_id,item_revision=sha256,plan_revision,acceptance_revision,minimum_test_criticality}]`. Отсутствующие revision/floor поля должны быть добавлены matching per-item Architect/Product markers до TestAssessment; global plan, acceptance или floor не закрывают item contract. Каждый item получает отдельный TestAssessment по [test-assessment.md](test-assessment.md); при `add/update` `TestPlan` обязательно содержит exact runnable commands, expected/actual baseline и реально совпавшие protected hashes для exact test keyset.

## ItemEvidence

Issue/code, item revision, diff identity, TestAssessment/disposition evidence, protected tests/hashes, repository checks, reviewer/guardian/QA/product-outcome verdicts, blocker и resulting Project status.

## EpicRunReport

Completed/ready/blocked/deferred items, statuses before/after, repository changes, checks, полный per-item gate ledger, Git/PR/release/deployment state, risks и next ready wave. Aggregate hook verdict без списка всех selected item IDs не закрывает этот артефакт.

## Machine result

Каждый субагент завершает exact строкой:

`WGC_AGENT_RESULT: {"role":"<role>","verdict":"<allowed-verdict>","phase":"<scope|outcome для product-manager; scope|reconcile для project-manager; plan|diff для architecture-guardian; иначе пусто>","input_revision":"<exact revision>","item_id":"<для item-facing role>","item_revision":"<sha256 для item-facing role>"}`

Project Manager scope и Test-maker используют расширенные exact markers из [test-assessment.md](test-assessment.md).
