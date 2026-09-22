# Full workflow details

Этот reference загружается только для Full. Full меняет глубину item planning, но не default execution team: один Terra Implementor, а Reviewer либо один specialist только по конкретному риску. Лимит 3 assignments и один correction batch на item slice из [coordination contract](coordination-efficiency.md) имеет приоритет; полный pipeline после finding не перезапускается.

# Epic implementation workflow

## Состояния run

`discovered → scoped → product_ready → architecture_approved → executing → reviewing → testing → integrated → delivery_ready → reconciled`

Каждый item имеет собственную state machine и revision. Approval одного item не переносится на другой.

## Item loop

1. Verify issue/Project revision и dependencies.
2. Product acceptance gate.
3. Architecture slice с minimum criticality и per-item TestAssessment; обычные tests принадлежат Implementor.
4. Implementor vertical diff + targeted T0/T1.
5. Orchestrator integrity check.
6. Reviewer + conditional Architecture Guardian diff gate.
7. Conditional QA либо одна integrated candidate QA.
8. Integration/delivery/status reconciliation.

## Invalidation

Exact assessed production diff сохраняет owning item TestAssessment/test-maker gate, но инвалидирует его старые test evidence, reviewer, architecture diff и QA. Неатрибутируемая docs/YAML/GitOps правка сбрасывает downstream gates всех items. Out-of-scope, contract/schema/migration, protected-test или item revision change инвалидирует assessment/downstream и может требовать Project Manager replan. Понижение minimum criticality требует новой per-item plan revision и нового Guardian plan approval; product semantics change инвалидирует acceptance/plan. Детали — в [test-assessment.md](test-assessment.md).

## Stop conditions

Останови новую wave при shared contract failure, migration incompatibility, cross-tenant/security finding, dirty-state collision, rate limit, lost Project authorization или исчерпании согласованного scope. Уже начатые безопасные проверки можно завершить read-only.

## YouTrack execution

До первого write slice: полный [MCP intake](youtrack.md), [продуктовый план и решения](product-discovery.md), [SP](story-points.md) и [BranchPlan](youtrack-git.md). Все вопросы по задаче предъявляются пользователю; противоречия текущей логике требуют явного approval до реализации. Планы эпика готовятся для всех его задач заранее. Stage меняет только YouTrack Operator с read-after-write; source code/merge не доказывает delivery.
