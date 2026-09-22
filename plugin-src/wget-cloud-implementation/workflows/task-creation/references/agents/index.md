# Реестр агентов task-creation

Перед запуском роли прочитай её contract. Все роли read-only относительно YouTrack и repository, кроме YouTrack Operator с exact mutation allowlist.

## Общий assignment envelope

```text
WORK_ITEM: <id и цель backlog>
ROLE: <role>
TASK_NAME: <role prefix>_<snake slice>[_ordinal]
TASK_SLICE: <одна ограниченная подзадача>
REPOSITORIES: <разрешённые repositories>
ALLOW_PATHS: <разрешённые paths или read-only>
DENY_PATHS: <запрещённые paths>
INPUT_ARTIFACTS: <TaskRequest, evidence и upstream artifacts>
DECISION_SNAPSHOT: <актуальные scope/product/project revisions и dependency map>
RESUME_CAPSULE_REVISION: <exact restored capsule revision|n/a>
ASSIGNMENT_KEY: <stable role+phase+slice+scope+revisions+artifact ID>
RETRY_REASON: <n/a|new evidence|invalidated revision|failed result|contract correction>
PROJECT_SCOPE: <exact instance URL/project key/issue IDs и mutation allowlist>
LOCAL_INSTRUCTIONS: <AGENTS.md и обязательные docs>
EXPECTED_COMMANDS: <read-only или verification checks>
ASSESSMENT_REVISION: <current TaskAssessment revision; n/a only during assessment/intake>
DOMAIN_PROFILES: <selected domain reference paths>
OUTPUT_CONTRACT: <артефакт и verdict enum>
MODEL_ROUTE: <economy|balanced|frontier>
MODEL: <selected advertised model>
REASONING_EFFORT: <selected effort>
ROUTING_BASIS: <role lane, risk и fallback evidence>
FORK_TURNS: <none|smallest justified positive N>
FORK_JUSTIFICATION: <n/a for none|why artifact cannot replace exact N turns>
SPAWN_PREFLIGHT: <exact model + reasoning_effort + fork_turns args verified>
TIME_BUDGET_MIN: <positive supervision budget in minutes>
CHECKPOINT_INTERVAL_MIN: <positive checkpoint interval in minutes>
MAX_EXTENSIONS: <non-negative extension limit>
PROGRESS_CRITERIA: <objective evidence required at checkpoints and completion>
EFFICIENCY_BUDGET: <max assignments/coordination decisions/unchanged waits/passive wait minutes/expensive checks/rework + checkpoint boundary>
INPUT_REVISION: <exact current workflow revision>
```

`TASK_NAME` строится из prefix таблицы и snake_case slice; итог передаётся в `spawn_agent.task_name`. Orchestrator использует `n/a`, не spawn и работает на `balanced`; frontier допустима только узкому подтверждённому escalation. Каждый субагент сохраняет пользовательские изменения, не commit/push/PR/merge/release/deploy, не расширяет YouTrack scope и не объявляет весь backlog готовым.

Перед spawn сверь [coordination contract](../coordination-efficiency.md): active/completed `ASSIGNMENT_KEY`, ResumeCapsule и EfficiencyBudget. Вызов без явных exact `model`, `reasoning_effort` и `fork_turns` запрещён; обычный fork — `none`, `all` запрещён.

## Model routing policy

Используй минимальную достаточную lane из таблиц: `economy` → Luna/low, `balanced` → Terra/medium, `frontier` → Sol/medium. Любой Sol effort выше `medium` запрещён. Fallback и ограничения: [model policy](../model-routing.md).

## Роли

| Роль | Task prefix | Когда применять | Write scope | Model lane | Контракт |
|---|---|---|---|---|---|
| Orchestrator | n/a | всегда | coordination | balanced | [orchestrator.md](orchestrator.md) |
| Product Manager | product_manager | business workflow и acceptance | нет | balanced | [product-manager.md](product-manager.md) |
| Project Manager | project_manager | schema, priority, sequence | нет | balanced | [project-manager.md](project-manager.md) |
| Implementation Auditor | implementation_auditor | current-state evidence | нет | balanced | [implementation-auditor.md](implementation-auditor.md) |
| Architect | architect | ownership/contracts/decomposition | нет | frontier | [architect.md](architect.md) |
| Backlog Reviewer | backlog_reviewer | независимый quality gate | нет | balanced | [backlog-reviewer.md](backlog-reviewer.md) |
| YouTrack Operator | youtrack_operator | идемпотентная publication | exact YouTrack MCP allowlist | economy | [youtrack-operator.md](youtrack-operator.md) |

## Машинный результат

Каждый spawned агент завершает ответ последней строкой с exact revision:

```text
WGC_AGENT_RESULT: {"role":"<role>","verdict":"<role verdict>","phase":"","input_revision":"<exact-input-revision>"}
```

Orchestrator самостоятельно проверяет артефакт и evidence. Role files задают допустимые verdicts; `phase` всегда пустой.

Task-creation хранит только provisional test policy в task body/AC по [test-assessment.md](../test-assessment.md). Она не добавляет Project fields и не заменяет финальный Test-maker `assessment_ready` при реализации.

## Независимость

- Product Manager не утверждает собственную спецификацию.
- Architect не является Backlog Reviewer.
- Project Manager не подменяет product decisions.
- YouTrack Operator не определяет scope и не считается независимой проверкой своих mutations.

## Дополнительные роли v7

| Роль | Task prefix | Когда применять | Write scope | Model lane | Контракт |
|---|---|---|---|---|---|
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
