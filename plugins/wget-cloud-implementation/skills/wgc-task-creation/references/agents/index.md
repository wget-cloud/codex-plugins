# Реестр агентов task-creation

Перед запуском роли прочитай её contract. Все роли read-only относительно GitHub и repository, кроме GitHub Project Operator с exact mutation allowlist.

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
PROJECT_SCOPE: <exact URL/owner/number и mutation allowlist>
LOCAL_INSTRUCTIONS: <AGENTS.md и обязательные docs>
EXPECTED_COMMANDS: <read-only или verification checks>
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

`TASK_NAME` строится из prefix таблицы и snake_case slice; итог передаётся в `spawn_agent.task_name`. Orchestrator не spawn. Каждый субагент сохраняет пользовательские изменения, не commit/push/PR/merge/release/deploy, не расширяет GitHub scope и не объявляет весь backlog готовым.

## Model routing policy

`economy` — deterministic discovery на `gpt-5.6-luna/low` (не Codex Fast mode); `balanced` — bounded work на `gpt-5.6-terra/medium`; `frontier` — product/architecture/gate на `gpt-5.6-sol/high`; `main-only` — главный агент. Используй только advertised model, `FORK_TURNS: none` и не более трёх активных субагентов. Critical capability нельзя молча downgrade.

## Роли

| Роль | Task prefix | Когда применять | Write scope | Model lane | Контракт |
|---|---|---|---|---|---|
| Orchestrator | n/a | всегда | coordination | main-only | [orchestrator.md](orchestrator.md) |
| Product Manager | product_manager | business workflow и acceptance | нет | frontier | [product-manager.md](product-manager.md) |
| Project Manager | project_manager | schema, priority, sequence | нет | balanced | [project-manager.md](project-manager.md) |
| Implementation Auditor | implementation_auditor | current-state evidence | нет | economy | [implementation-auditor.md](implementation-auditor.md) |
| Architect | architect | ownership/contracts/decomposition | нет | frontier | [architect.md](architect.md) |
| Backlog Reviewer | backlog_reviewer | независимый quality gate | нет | frontier | [backlog-reviewer.md](backlog-reviewer.md) |
| GitHub Project Operator | github_project_operator | идемпотентная publication | exact GitHub allowlist | balanced | [github-project-operator.md](github-project-operator.md) |

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
- GitHub Project Operator не определяет scope и не считается независимой проверкой своих mutations.
