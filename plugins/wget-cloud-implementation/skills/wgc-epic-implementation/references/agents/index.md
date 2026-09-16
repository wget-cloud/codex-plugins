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
ASSESSMENT_REVISION: <current TaskAssessment revision; n/a only during assessment/intake>
DOMAIN_PROFILES: <selected domain reference paths>
OUTPUT_CONTRACT: <артефакт и verdict enum>
MODEL_ROUTE: <economy|balanced|frontier>
MODEL: <selected advertised model>
REASONING_EFFORT: <selected effort>
ROUTING_BASIS: <role lane, risk и fallback evidence>
FORK_TURNS: <none|smallest justified positive N|all>
TIME_BUDGET_MIN: <positive supervision budget in minutes>
CHECKPOINT_INTERVAL_MIN: <positive checkpoint interval in minutes>
MAX_EXTENSIONS: <non-negative extension limit>
PROGRESS_CRITERIA: <objective evidence required at checkpoints and completion>
INPUT_REVISION: <exact current workflow revision>
```

`TASK_NAME` строится из prefix и snake_case item slice. Orchestrator использует `n/a`, не spawn и требует запуска основной задачи на своей `frontier` lane. Каждый субагент работает только в slice, сохраняет чужие изменения, не commit/push/PR/merge/release/deploy без приложенного разрешения и не меняет YouTrack, кроме Operator с exact sync plan.

## Model routing policy

Используй минимальную достаточную lane из таблиц: `economy` → Luna/low, `balanced` → Terra/medium, `frontier` → Sol/high. Fallback и service-tier ограничения: [model policy](../model-routing.md).

## Роли

| Роль | Task prefix | Когда применять | Write scope | Model lane | Контракт |
|---|---|---|---|---|---|
| Orchestrator | n/a | всегда | coordination | frontier | [orchestrator.md](orchestrator.md) |
| Product Manager | product_manager | intent и acceptance | нет | balanced | [product-manager.md](product-manager.md) |
| Project Manager | project_manager | scope/reconcile | нет | balanced | [project-manager.md](project-manager.md) |
| Explorer | explorer | repository mapping | нет | economy | [explorer.md](explorer.md) |
| Architect | architect | ImplementationDAG | нет | frontier | [architect.md](architect.md) |
| Architecture Guardian | architecture_guardian | plan/diff gate | нет | frontier | [architecture-guardian.md](architecture-guardian.md) |
| Test-maker | test_maker | per-item adaptive TestAssessment | tests allowlist при add/update | balanced | [test-maker.md](test-maker.md) |
| Implementor | implementor | one atomic slice | production/docs allowlist | balanced | [implementor.md](implementor.md) |
| Reviewer | reviewer | independent review | нет | frontier | [reviewer.md](reviewer.md) |
| QA | qa | behavior verification | нет в repository | balanced | [qa.md](qa.md) |
| YouTrack Operator | youtrack_operator | exact status sync | selected item/status allowlist | economy | [youtrack-operator.md](youtrack-operator.md) |
| DevOps | devops | GitOps desired state | k8s allowlist | balanced | [devops.md](devops.md) |
| Infrastructure Reviewer | infrastructure_reviewer | GitOps gate | нет | frontier | [infrastructure-reviewer.md](infrastructure-reviewer.md) |
| Deployment Agent | deployment_agent | approved rollout | exact approved action | economy | [deployment-agent.md](deployment-agent.md) |

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

## Дополнительные роли v7

| Роль | Task prefix | Когда применять | Write scope | Model lane | Контракт |
|---|---|---|---|---|---|
| browser-qa | browser_qa | по TaskAssessment | read-only | balanced | [browser-qa.md](browser-qa.md) |
| contract-qa | contract_qa | по TaskAssessment | read-only | frontier | [contract-qa.md](contract-qa.md) |
| data-migration-reviewer | data_migration_reviewer | по TaskAssessment | read-only | frontier | [data-migration-reviewer.md](data-migration-reviewer.md) |
| reliability-reviewer | reliability_reviewer | по TaskAssessment | read-only | frontier | [reliability-reviewer.md](reliability-reviewer.md) |
| security-reviewer | security_reviewer | по TaskAssessment | read-only | frontier | [security-reviewer.md](security-reviewer.md) |
| task-assessor | task_assessor | по TaskAssessment | read-only | balanced | [task-assessor.md](task-assessor.md) |

## Выбор команды

[TaskAssessment](../task-assessment.md) определяет применимость ролей; таблица — каталог, не требование запускать всех. Каждый downstream marker повторяет `assessment_revision`. Skills не передают control друг другу: Orchestrator сохраняет единый WorkItem и выбирает процесс/профили.

## YouTrack и продуктовая проработка

Все роли читают [product discovery](../product-discovery.md) перед постановкой/планом. Только YouTrack Operator меняет карточки; Orchestrator проверяет результат независимо.

| Роль | Task prefix | Когда применять | Write scope | Model lane | Контракт |
|---|---|---|---|---|---|
| Effort Estimator | effort_estimator | SP до создания; при delivery без оценки или при изменении плана | read-only | economy | [effort-estimator.md](effort-estimator.md) |

Assignment дополнительно содержит TRACKER=youtrack, ISSUE_SCOPE (exact project keys/IDs), PLAN_REVISION, DECISION_REFS, ESTIMATE_REFS и MUTATION_ALLOWLIST; секреты не передаются. Registry задаёт существующие marker fields; `phase` новых ролей пустой. Effort Estimator не совмещается с автором оцениваемой постановки/плана.

При любом scope эпика назначается отдельный [Project Manager](project-manager.md) с phase=lifecycle для [переходов Stage](../epic-lifecycle.md). Verdicts: stage_ready/awaiting_user/stage_blocked; обязательный EpicStagePlan. Прежние phase/verdicts сохраняются для их исходных назначений. В implementation/bugfix PM работает только в lifecycle; он read-only и не совмещается с Operator.
