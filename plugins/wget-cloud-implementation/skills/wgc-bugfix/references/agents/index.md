# Реестр агентов bugfix-конвейера

Оркестратор читает этот index полностью, но открывает role contract только непосредственно перед назначением роли. Не загружай downstream-роли заранее и не подключай conditional specialists без route signal.

## Общий assignment envelope

```text
BUG_CASE: <id и redacted symptom>
ROLE: <role>
PHASE: <evidence|rca|plan|diff либо пусто>
TASK_NAME: <role prefix>_<snake slice>[_ordinal]
TASK_SLICE: <одна ограниченная подзадача>
REPOSITORIES: <разрешённые repo>
ALLOW_PATHS: <разрешённые пути>
DENY_PATHS: <запрещённые пути/protected tests>
INPUT_ARTIFACTS: <triage/evidence/RCA/plan/findings>
DECISION_SNAPSHOT: <актуальные revision IDs и dependency map>
RESUME_CAPSULE_REVISION: <exact restored capsule revision|n/a>
ASSIGNMENT_KEY: <stable role+phase+slice+scope+revisions+artifact ID>
RETRY_REASON: <n/a|new evidence|invalidated revision|failed result|contract correction>
DIFF_IDENTITY: <immutable reviewed tree ID|n/a>
LOCAL_INSTRUCTIONS: <AGENTS.md и source-of-truth docs>
ENVIRONMENT: <local/test/stage/prod + ограничения>
ASSESSMENT_REVISION: <current TaskAssessment revision; n/a only during assessment/intake>
DOMAIN_PROFILES: <selected domain reference paths>
OUTPUT_CONTRACT: <артефакт и verdict enum>
MODEL_ROUTE: <economy|focused|balanced|architecture>
MODEL: <selected advertised model>
REASONING_EFFORT: <selected effort>
ROUTING_BASIS: <role lane, risk и fallback evidence>
FALLBACK_REASON: <n/a|why Luna lane escalated to Sol/low>
MEDIUM_ESCALATION_ROLE: <n/a|same specialist role>
MEDIUM_ESCALATION_REASON: <n/a|critical reason>
BLOCKER_EVIDENCE: <n/a|redacted evidence refs>
FAILED_LOW_EFFORT_ATTEMPT: <n/a|completed Sol/low attempt>
CRITICAL_INVARIANT: <n/a|data/tenant/security/contract/migration/concurrency invariant>
EXPECTED_DECISION: <n/a|bounded decision medium must produce>
FORK_TURNS: <none|smallest justified positive N>
FORK_JUSTIFICATION: <n/a for none|why artifact cannot replace exact N turns>
SPAWN_PREFLIGHT: <exact model + reasoning_effort + fork_turns args verified>
TIME_BUDGET_MIN: <positive supervision budget in minutes>
CHECKPOINT_INTERVAL_MIN: <positive checkpoint interval in minutes>
MAX_EXTENSIONS: <non-negative extension limit>
PROGRESS_CRITERIA: <objective evidence required at checkpoints and completion>
EFFICIENCY_BUDGET: <max assignments/coordination decisions/unchanged waits/passive wait minutes/expensive checks/rework + checkpoint boundary>
```

`TASK_NAME` строится как `<Task prefix>_<snake_case task slice>[_<positive ordinal>]`: prefix берётся из таблицы, slice обязателен, ordinal добавляй только при collision/restart sibling-задачи. Полное значение передай в `spawn_agent.task_name`. Orchestrator использует `n/a`, не spawn и работает на `balanced`; `architecture` штатно принадлежит только Architect.

Каждому субагенту добавляй: «Работай только в выданном scope. Не сохраняй raw prompt/logs/secrets/PII. Не меняй внешние данные, Git publication или deployment без приложенного разрешения. Не объявляй весь bugfix завершённым. При нехватке evidence остановись с допустимым blocker verdict».

Перед spawn сверь [coordination contract](../coordination-efficiency.md): active/completed `ASSIGNMENT_KEY`, ResumeCapsule и EfficiencyBudget. Вызов без явных exact `model`, `reasoning_effort` и `fork_turns` запрещён; обычный fork — `none`, `all` запрещён.

Поля времени задают bounded supervision, а не автоматическую остановку. На checkpoint оркестратор сравнивает objective evidence с `PROGRESS_CRITERIA`. Extension допускается только в пределах `MAX_EXTENSIONS` и логируется с reason, evidence и новой boundary. Первый stall требует correction или rescope; повторный stall либо scope drift — interrupt, inspection partial work и restart/split. Hooks не являются таймерами и не подтверждают соблюдение этих границ.

## Model routing policy

Используй минимальную достаточную lane: `economy` → Luna/low, `focused` → Luna/medium, `balanced` → Sol/low, `architecture` → Sol/medium. Astra и Sol выше `medium` запрещены. Fallback/эскалация: [model policy](../model-routing.md).

## Core roles

Не держи более трёх активных субагентов одновременно.

| Роль | Task prefix | Этап | Write scope | Model lane | Контракт |
|---|---|---|---|---|---|
| Orchestrator | n/a | весь workflow | координационные действия | balanced | [orchestrator.md](orchestrator.md) |
| Bug-triage | bug_triage | triage | нет | economy | [bug-triage.md](bug-triage.md) |
| Bug-investigator | bug_investigator | evidence и RCA | нет | balanced | [bug-investigator.md](bug-investigator.md) |
| Reproducer | reproducer | reproduction/characterization | только task-owned test data | balanced | [reproducer.md](reproducer.md) |
| Root-cause reviewer | root_cause_reviewer | RCA gate | нет | balanced | [root-cause-reviewer.md](root-cause-reviewer.md) |
| Architect | architect | FixPlan | нет | architecture | [architect.md](architect.md) |
| Architecture guardian | architecture_guardian | plan/diff gates | нет | balanced | [architecture-guardian.md](architecture-guardian.md) |
| Test-maker | test_maker | adaptive TestAssessment; conditional regression test | tests allowlist только при add/update | balanced | [test-maker.md](test-maker.md) |
| Implementor | implementor | minimal fix | production/docs allowlist | balanced | [implementor.md](implementor.md) |
| Reviewer | reviewer | code review; технический risk переводит assignment в balanced | нет | focused | [reviewer.md](reviewer.md) |
| QA | qa | adversarial regression | нет в repository | focused | [qa.md](qa.md) |

## Conditional roles

| Route signal | Роль | Task prefix | Model lane | Контракт |
|---|---|---|---|---|
| UI/PWA/realtime/browser | Browser QA | browser_qa | balanced | [browser-qa.md](browser-qa.md) |
| auth/RBAC/tenant/PII | Security reviewer | security_reviewer | balanced | [security-reviewer.md](security-reviewer.md) |
| REST/gRPC/proto/schema/events/public exports | Contract QA | contract_qa | balanced | [contract-qa.md](contract-qa.md) |
| `k8s`/CI desired-state diff | DevOps | devops | balanced | [devops.md](devops.md) |
| infrastructure diff | Infrastructure reviewer | infrastructure_reviewer | balanced | [infrastructure-reviewer.md](infrastructure-reviewer.md) |
| exact deployment approval | Deployment agent | deployment_agent | economy | [deployment-agent.md](deployment-agent.md) |

## Машинный результат

Каждый субагент завершает ответ одной последней строкой:

```text
WGC_AGENT_RESULT: {"role":"<role>","verdict":"<role verdict>","phase":"<role-required-phase-or-empty>","input_revision":"<exact-input-revision>"}
```

Hooks проверяют role/verdict/phase с учётом профиля `bugfix`. Оркестратор отдельно проверяет артефакт, evidence и актуальность revision.

Test-maker использует расширенный flat marker из [test-assessment.md](../test-assessment.md) и единый verdict `assessment_ready`; generic marker выше недостаточен.

Architect marker обязательно добавляет `plan_revision` и `minimum_test_criticality`; Reproducer с `reproduced|characterized` добавляет `acceptance_revision`. Exact markers находятся в [architect.md](architect.md) и [reproducer.md](reproducer.md).

Architecture Guardian в `phase=plan` добавляет exact текущий FixPlan `plan_revision`; missing/stale revision не закрывает gate. Exact marker находится в [architecture-guardian.md](architecture-guardian.md).

## Независимость

Автор RCA не является Root-cause reviewer. Implementor не совмещается с Test-maker/Reviewer/Guardian. DevOps не является Infrastructure reviewer. Deployment agent не пишет source/manifests. При нехватке слотов роли запускаются последовательно, но полномочия не объединяются.

## Дополнительные роли v7

| Роль | Task prefix | Когда применять | Write scope | Model lane | Контракт |
|---|---|---|---|---|---|
| data-migration-reviewer | data_migration_reviewer | по TaskAssessment | read-only | balanced | [data-migration-reviewer.md](data-migration-reviewer.md) |
| reliability-reviewer | reliability_reviewer | по TaskAssessment | read-only | balanced | [reliability-reviewer.md](reliability-reviewer.md) |
| task-assessor | task_assessor | по TaskAssessment | read-only | focused | [task-assessor.md](task-assessor.md) |

## Выбор команды

[TaskAssessment](../task-assessment.md) определяет применимость ролей; таблица — каталог, не требование запускать всех. Каждый downstream marker повторяет `assessment_revision`. Skills не передают control друг другу: Orchestrator сохраняет единый WorkItem и выбирает процесс/профили.

## YouTrack и продуктовая проработка

Все роли читают [product discovery](../product-discovery.md) перед постановкой/планом. Только YouTrack Operator меняет карточки; Orchestrator проверяет результат независимо.

| Роль | Task prefix | Когда применять | Write scope | Model lane | Контракт |
|---|---|---|---|---|---|
| Effort Estimator | effort_estimator | SP до создания; при delivery без оценки или при изменении плана | read-only | focused | [effort-estimator.md](effort-estimator.md) |
| YouTrack Operator | youtrack_operator | разрешённые записи карточек и Stage | exact MCP allowlist | economy | [youtrack-operator.md](youtrack-operator.md) |

Assignment дополнительно содержит TRACKER=youtrack, ISSUE_SCOPE (exact project keys/IDs), PLAN_REVISION, DECISION_REFS, ESTIMATE_REFS и MUTATION_ALLOWLIST; секреты не передаются. Registry задаёт существующие marker fields; `phase` новых ролей пустой. Effort Estimator не совмещается с автором оцениваемой постановки/плана.

При любом scope эпика назначается отдельный [Project Manager](project-manager.md) с phase=lifecycle для [переходов Stage](../epic-lifecycle.md). Verdicts: stage_ready/awaiting_user/stage_blocked; обязательный EpicStagePlan. Прежние phase/verdicts сохраняются для их исходных назначений. В implementation/bugfix PM работает только в lifecycle; он read-only и не совмещается с Operator.

| Role | Task prefix | When | Write scope | Model lane | Contract |
|---|---|---|---|---|---|
| Project Manager | project_manager | Stage эпика при изменении дочерней задачи | read-only | focused | [project-manager.md](project-manager.md) |
