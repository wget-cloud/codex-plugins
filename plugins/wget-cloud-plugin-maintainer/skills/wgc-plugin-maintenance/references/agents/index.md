# Реестр агентов plugin-maintenance

Оркестратор читает этот index полностью. Файл конкретной роли открывается непосредственно перед назначением; downstream contracts заранее не загружаются.

## Общий assignment envelope

```text
WORK_ITEM: <proposal/item id и цель>
ROLE: <role>
TASK_NAME: <role prefix>_<snake slice>[_ordinal]
TASK_SLICE: <одна ограниченная подзадача>
REPOSITORY: <absolute codex-plugins root>
ALLOW_PATHS: <exact read/write paths>
DENY_PATHS: <baseline dirty и protected tests>
INPUT_ARTIFACTS: <findings, proposal, tests, diff или evidence>
LOCAL_INSTRUCTIONS: <AGENTS.md, README и component docs>
EXPECTED_COMMANDS: <read-only inspection или проверки>
OUTPUT_CONTRACT: <artifact и verdict enum>
MODEL_ROUTE: <economy|balanced|frontier|main-only>
MODEL: <selected advertised model или inherit>
REASONING_EFFORT: <selected effort или inherit>
ROUTING_BASIS: <lane, risk и benchmark evidence>
FORK_TURNS: <none|smallest justified positive N|all>
TIME_BUDGET_MIN: <positive supervision budget>
CHECKPOINT_INTERVAL_MIN: <positive checkpoint interval>
MAX_EXTENSIONS: <non-negative extension limit>
PROGRESS_CRITERIA: <objective evidence at checkpoints and completion>
```

`TASK_NAME` использует точный prefix из таблицы. Передавай полное значение без изменений в `spawn_agent.task_name`. Orchestrator имеет `n/a` и не spawn.

Каждому субагенту передавай exact repository revision и instruction: работать только в назначенном scope, сохранить baseline dirty paths, не выполнять commit/push/install/release и не считать отсутствие ответа approval. Write-роли получают доказательство Gate 1. Reviewer и QA не исправляют findings.

## Model routing policy

- `economy`: `gpt-5.6-luna/low`, затем `gpt-5.6-terra/low`, затем advertised equivalent или inherit. Это не Codex Fast mode.
- `balanced`: `gpt-5.6-terra/medium`, затем `gpt-5.6-sol/medium`, затем inherit.
- `frontier`: `gpt-5.6-sol/high`, затем `gpt-5.6-terra/high`; неизвестный inherit не заменяет frontier для approval/security архитектуры.
- `main-only`: только Orchestrator.

Не более трёх субагентов одновременно. Default `FORK_TURNS` — `none`; используй минимальный положительный fork только при незаменимом conversational context. Model-route изменения самого plugin проходят benchmark из evaluation contract.

## Роли

| Роль | Task prefix | Когда применять | Write scope | Model lane | Контракт |
|---|---|---|---|---|---|
| Orchestrator | n/a | всегда | coordination и approved delivery | main-only | [orchestrator.md](orchestrator.md) |
| Auditor | auditor | full repository/CI/runtime audit | нет | balanced | [auditor.md](auditor.md) |
| Architect | architect | item boundaries, capability design | нет | frontier | [architect.md](architect.md) |
| Test-maker | test_maker | regression, contract и eval baseline | approved tests/evals only | balanced | [test-maker.md](test-maker.md) |
| Implementor | implementor | один approved item slice | approved non-protected paths | balanced | [implementor.md](implementor.md) |
| Reviewer | reviewer | exact diff and approval review | нет | frontier | [reviewer.md](reviewer.md) |
| QA | qa | adversarial protocol/runtime verification | нет в repository | balanced | [qa.md](qa.md) |

## Машинный результат

Каждый spawned agent завершает последней строкой:

```text
WGC_MAINTAINER_RESULT: {"role":"<role>","verdict":"<allowed-verdict>","input_revision":"<exact assigned revision>"}
```

Строка не заменяет evidence. Orchestrator перепроверяет revision, diff, commands и paths. Hooks принимают только verdicts из role contracts.

Test-maker с `baseline_ready` также возвращает точный `WGC_MAINTAINER_PROTECTED_TESTS` marker из своего role contract; hook связывает paths и SHA-256 с Gate 1 и запрещает последующие edits.

## Независимость

- Auditor не проектирует или реализует исправление.
- Architect не утверждает собственный design.
- Test-maker и Implementor не совмещаются; Implementor не меняет protected tests.
- Reviewer и QA независимы от авторов и read-only.
- Два write-агента не работают одновременно.
