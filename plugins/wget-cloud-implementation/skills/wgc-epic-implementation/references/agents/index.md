# Реестр агентов epic-implementation

## Общий assignment envelope

```text
WORK_ITEM: <item URL/code и цель>
EPIC_RUN: <selected scope, exclusions и authority>
PROJECT_SNAPSHOT_REVISION: <exact snapshot revision>
ROLE: <role>
TASK_NAME: <role prefix>_<snake slice>[_ordinal]
TASK_SLICE: <один atomic item slice>
DEPENDENCY_EVIDENCE: <delivered prerequisites и blockers>
REPOSITORIES: <разрешённые repositories>
ALLOW_PATHS: <разрешённые paths>
DENY_PATHS: <запрещённые paths>
PROTECTED_TESTS: <paths и hashes>
INPUT_ARTIFACTS: <upstream plans/reports/findings>
LOCAL_INSTRUCTIONS: <AGENTS.md и обязательные docs>
EXPECTED_COMMANDS: <targeted checks>
OUTPUT_CONTRACT: <артефакт и verdict enum>
MODEL_ROUTE: <economy|balanced|frontier|main-only>
MODEL: <selected advertised model или inherit>
REASONING_EFFORT: <selected effort или inherit>
ROUTING_BASIS: <role lane, risk signals и fallback>
FORK_TURNS: <none|smallest justified positive N|all>
TIME_BUDGET_MIN: <positive supervision budget in minutes>
CHECKPOINT_INTERVAL_MIN: <positive checkpoint interval in minutes>
MAX_EXTENSIONS: <non-negative extension limit>
PROGRESS_CRITERIA: <objective evidence required at checkpoints and completion>
INPUT_REVISION: <exact current workflow revision>
```

`TASK_NAME` строится из prefix и snake_case item slice. Каждый субагент работает только в slice, сохраняет чужие изменения, не commit/push/PR/merge/release/deploy без приложенного разрешения и не меняет GitHub Project, кроме Operator с exact sync plan.

## Model routing policy

`economy` — deterministic discovery на `gpt-5.6-luna/low` (не Codex Fast mode); `balanced` — bounded work на `gpt-5.6-terra/medium`; `frontier` — judgement на `gpt-5.6-sol/high`; `main-only` — главный агент. Используй только advertised model, `FORK_TURNS: none` и не более трёх активных субагентов. Critical capability нельзя молча downgrade.

## Роли

| Роль | Task prefix | Когда применять | Write scope | Model lane | Контракт |
|---|---|---|---|---|---|
| Orchestrator | n/a | всегда | coordination | main-only | [orchestrator.md](orchestrator.md) |
| Product Manager | product_manager | intent и acceptance | нет | frontier | [product-manager.md](product-manager.md) |
| Project Manager | project_manager | scope/reconcile | нет | balanced | [project-manager.md](project-manager.md) |
| Explorer | explorer | repository mapping | нет | economy | [explorer.md](explorer.md) |
| Architect | architect | ImplementationDAG | нет | frontier | [architect.md](architect.md) |
| Architecture Guardian | architecture_guardian | plan/diff gate | нет | frontier | [architecture-guardian.md](architecture-guardian.md) |
| Test-maker | test_maker | per-item adaptive TestAssessment | tests allowlist при add/update | balanced | [test-maker.md](test-maker.md) |
| Implementor | implementor | one atomic slice | production/docs allowlist | balanced | [implementor.md](implementor.md) |
| Reviewer | reviewer | independent review | нет | balanced | [reviewer.md](reviewer.md) |
| QA | qa | behavior verification | нет в repository | balanced | [qa.md](qa.md) |
| GitHub Project Operator | github_project_operator | exact status sync | selected item/status allowlist | balanced | [github-project-operator.md](github-project-operator.md) |
| DevOps | devops | GitOps desired state | k8s allowlist | frontier | [devops.md](devops.md) |
| Infrastructure Reviewer | infrastructure_reviewer | GitOps gate | нет | frontier | [infrastructure-reviewer.md](infrastructure-reviewer.md) |
| Deployment Agent | deployment_agent | approved rollout | exact approved action | frontier | [deployment-agent.md](deployment-agent.md) |

## Машинный результат

```text
WGC_AGENT_RESULT: {"role":"<role>","verdict":"<role verdict>","phase":"<scope|outcome для product-manager; scope|reconcile для project-manager; plan|diff для architecture-guardian; иначе пусто>","input_revision":"<exact-input-revision>"}
```

Project Manager scope marker передаёт bounded максимум 100 entries `selected_items[{item_id,item_revision=sha256,plan_revision,acceptance_revision,minimum_test_criticality}]`. Item-facing Architect добавляет exact `item_id`, `item_revision`, `plan_revision`, `minimum_test_criticality`; Product scope marker добавляет per-item `acceptance_revision`, если ledger ещё не содержал его. Item-facing Test-maker, Implementor, Reviewer, Guardian diff, QA и Product outcome добавляют exact `item_id`/`item_revision`; Test-maker использует полный flat marker из [test-assessment.md](../test-assessment.md). Global revision/floor не подменяет per-item поля. Текст не заменяет артефакт.

Architecture Guardian `phase=plan` также всегда item-facing: marker содержит exact frozen `item_id`, SHA-256 `item_revision` и текущий per-item `plan_revision`. Global, missing или stale marker запрещён; пример находится в [architecture-guardian.md](architecture-guardian.md).

## Независимость

- Implementor не совмещается с Test-maker, Reviewer, QA или Architecture Guardian.
- Architect не утверждает свой plan; DevOps не является Infrastructure Reviewer.
- Product/Project Manager и Operator не объявляют delivery результата без repository evidence.
- Два write-агента не работают одновременно в одном repository или contract boundary.
