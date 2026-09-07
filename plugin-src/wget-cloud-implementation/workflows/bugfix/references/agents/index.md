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
LOCAL_INSTRUCTIONS: <AGENTS.md и source-of-truth docs>
ENVIRONMENT: <local/test/stage/prod + ограничения>
ASSESSMENT_REVISION: <current TaskAssessment revision; n/a only during assessment/intake>
DOMAIN_PROFILES: <selected domain reference paths>
OUTPUT_CONTRACT: <артефакт и verdict enum>
MODEL_ROUTE: <inherit|main-only>
MODEL: inherit
REASONING_EFFORT: inherit
ROUTING_BASIS: <TaskAssessment mode/risk; inherited chat model>
FORK_TURNS: <none|smallest justified positive N|all>
TIME_BUDGET_MIN: <positive supervision budget in minutes>
CHECKPOINT_INTERVAL_MIN: <positive checkpoint interval in minutes>
MAX_EXTENSIONS: <non-negative extension limit>
PROGRESS_CRITERIA: <objective evidence required at checkpoints and completion>
```

`TASK_NAME` строится как `<Task prefix>_<snake_case task slice>[_<positive ordinal>]`: prefix берётся из таблицы, slice обязателен, ordinal добавляй только при collision/restart sibling-задачи. Полное итоговое значение `TASK_NAME` передай без изменений в `spawn_agent.task_name`. Orchestrator использует `n/a` и не spawn.

Каждому субагенту добавляй: «Работай только в выданном scope. Не сохраняй raw prompt/logs/secrets/PII. Не меняй внешние данные, Git publication или deployment без приложенного разрешения. Не объявляй весь bugfix завершённым. При нехватке evidence остановись с допустимым blocker verdict».

Поля времени задают bounded supervision, а не автоматическую остановку. На checkpoint оркестратор сравнивает objective evidence с `PROGRESS_CRITERIA`. Extension допускается только в пределах `MAX_EXTENSIONS` и логируется с reason, evidence и новой boundary. Первый stall требует correction или rescope; повторный stall либо scope drift — interrupt, inspection partial work и restart/split. Hooks не являются таймерами и не подтверждают соблюдение этих границ.

## Model routing policy

Все роли наследуют model/effort чата; overrides при spawn опускаются. Model lane `inherit` — одинаковая модель, не снижение качества. Service tier проверяется отдельно. Подробности: [model policy](../model-routing.md).

## Core roles

Не держи более трёх активных субагентов одновременно.

| Роль | Task prefix | Этап | Write scope | Model lane | Контракт |
|---|---|---|---|---|---|
| Orchestrator | n/a | весь workflow | координационные действия | main-only | [orchestrator.md](orchestrator.md) |
| Bug-triage | bug_triage | triage | нет | inherit | [bug-triage.md](bug-triage.md) |
| Bug-investigator | bug_investigator | evidence и RCA | нет | inherit | [bug-investigator.md](bug-investigator.md) |
| Reproducer | reproducer | reproduction/characterization | только task-owned test data | inherit | [reproducer.md](reproducer.md) |
| Root-cause reviewer | root_cause_reviewer | RCA gate | нет | inherit | [root-cause-reviewer.md](root-cause-reviewer.md) |
| Architect | architect | FixPlan | нет | inherit | [architect.md](architect.md) |
| Architecture guardian | architecture_guardian | plan/diff gates | нет | inherit | [architecture-guardian.md](architecture-guardian.md) |
| Test-maker | test_maker | adaptive TestAssessment; conditional regression test | tests allowlist только при add/update | inherit | [test-maker.md](test-maker.md) |
| Implementor | implementor | minimal fix | production/docs allowlist | inherit | [implementor.md](implementor.md) |
| Reviewer | reviewer | code review | нет | inherit | [reviewer.md](reviewer.md) |
| QA | qa | adversarial regression | нет в repository | inherit | [qa.md](qa.md) |

## Conditional roles

| Route signal | Роль | Task prefix | Model lane | Контракт |
|---|---|---|---|---|
| UI/PWA/realtime/browser | Browser QA | browser_qa | inherit | [browser-qa.md](browser-qa.md) |
| auth/RBAC/tenant/PII | Security reviewer | security_reviewer | inherit | [security-reviewer.md](security-reviewer.md) |
| REST/gRPC/proto/schema/events/public exports | Contract QA | contract_qa | inherit | [contract-qa.md](contract-qa.md) |
| `k8s`/CI desired-state diff | DevOps | devops | inherit | [devops.md](devops.md) |
| infrastructure diff | Infrastructure reviewer | infrastructure_reviewer | inherit | [infrastructure-reviewer.md](infrastructure-reviewer.md) |
| exact deployment approval | Deployment agent | deployment_agent | inherit | [deployment-agent.md](deployment-agent.md) |

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
| data-migration-reviewer | data_migration_reviewer | по TaskAssessment | read-only | inherit | [data-migration-reviewer.md](data-migration-reviewer.md) |
| reliability-reviewer | reliability_reviewer | по TaskAssessment | read-only | inherit | [reliability-reviewer.md](reliability-reviewer.md) |
| task-assessor | task_assessor | по TaskAssessment | read-only | inherit | [task-assessor.md](task-assessor.md) |

## Выбор команды

[TaskAssessment](../task-assessment.md) определяет применимость ролей; таблица — каталог, не требование запускать всех. Каждый downstream marker повторяет `assessment_revision`. Skills не передают control друг другу: Orchestrator сохраняет единый WorkItem и выбирает процесс/профили.
