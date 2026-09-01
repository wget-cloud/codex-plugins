# Артефакты и gates

## ProjectSnapshot

Project identity/schema revision, selected item identity/status/priority/parent/dependencies/linked delivery и existing conflicts.

## EpicRun

Objective, selected/excluded items, delivery authority, repositories, concurrency cap, stop conditions, product decisions и target environment.

## ProductAcceptance

В phase `scope`: item-by-item accepted AC, ambiguities, explicit decisions и rejected interpretations. В phase `outcome`: наблюдаемый результат каждого selected item после QA и его соответствие business outcome.

## ImplementationDAG

Atomic slices, owners, paths, contracts, migrations, tests, docs, waves, rollback and delivery order.

## ItemEvidence

Issue/code, input revision, diff identity, protected tests/hashes, checks/coverage, reviewer/guardian/QA verdicts, blocker и resulting Project status.

## EpicRunReport

Completed/ready/blocked/deferred items, statuses before/after, repository changes, checks, полный per-item gate ledger, Git/PR/release/deployment state, risks и next ready wave. Aggregate hook verdict без списка всех selected item IDs не закрывает этот артефакт.

## Machine result

Каждый субагент завершает exact строкой:

`WGC_AGENT_RESULT: {"role":"<role>","verdict":"<allowed-verdict>","phase":"<scope|outcome для product-manager; scope|reconcile для project-manager; plan|diff для architecture-guardian; иначе пусто>","input_revision":"<exact revision>"}`
