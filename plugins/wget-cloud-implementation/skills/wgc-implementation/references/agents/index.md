# Реестр агентов implementation-конвейера

Открывай файл роли непосредственно перед её назначением и не загружай downstream-роли заранее. Оркестратор читает этот index полностью, а затем передаёт субагенту конкретный role contract вместе с task scope.

## Общий assignment envelope

```text
WORK_ITEM: <id и цель>
ROLE: <role>
TASK_NAME: <role prefix>_<snake slice>[_ordinal]
TASK_SLICE: <одна ограниченная подзадача>
REPOSITORIES: <разрешённые repo>
ALLOW_PATHS: <разрешённые пути>
DENY_PATHS: <запрещённые пути, включая protected tests>
INPUT_ARTIFACTS: <план, findings, acceptance criteria>
LOCAL_INSTRUCTIONS: <AGENTS.md и обязательные docs>
EXPECTED_COMMANDS: <проверки>
OUTPUT_CONTRACT: <артефакт и verdict enum>
MODEL_ROUTE: <fast|balanced|frontier|main-only>
MODEL: <selected advertised model или inherit>
REASONING_EFFORT: <selected effort или inherit>
ROUTING_BASIS: <role lane, risk signals и fallback>
FORK_TURNS: <none|smallest justified positive N|all>
TIME_BUDGET_MIN: <positive supervision budget in minutes>
CHECKPOINT_INTERVAL_MIN: <positive checkpoint interval in minutes>
MAX_EXTENSIONS: <non-negative extension limit>
PROGRESS_CRITERIA: <objective evidence required at checkpoints and completion>
```

`TASK_NAME` строится как `<Task prefix>_<snake_case task slice>[_<positive ordinal>]`: prefix берётся из таблицы, slice обязателен, ordinal добавляй только при collision/restart sibling-задачи. Полное итоговое значение `TASK_NAME` передай без изменений в `spawn_agent.task_name`. Orchestrator использует `n/a` и не spawn.

Каждому субагенту добавляй: «Работай только в выданном scope. Сохраняй существующие изменения. Не выполняй commit, push, PR, merge, release или deployment без приложенного разрешения. Не объявляй всю задачу завершённой. Если scope недостаточен, верни `needs_input`».

Поля времени задают bounded supervision, а не автоматическую остановку. На checkpoint оркестратор сравнивает objective evidence с `PROGRESS_CRITERIA`. Extension допускается только в пределах `MAX_EXTENSIONS` и логируется с reason, evidence и новой boundary. Первый stall требует correction или rescope; повторный stall либо scope drift — interrupt, inspection partial work и restart/split. Hooks не являются таймерами и не подтверждают соблюдение этих границ.

## Model routing policy

Model lane из registry — default для роли; перед launch оркестратор выбирает только model, advertised активным spawn tool, и записывает итог во все routing-поля envelope. `main-only` означает работу оркестратора в главном агенте: не spawn.

- `fast`: предпочитай `gpt-5.6-luna`/`low`; fallback `gpt-5.6-terra`/`low`, затем `gpt-5.6-sol`/`low`, затем `inherit`.
- `balanced`: предпочитай `gpt-5.6-terra`/`medium`; fallback `gpt-5.6-sol`/`medium`, затем `inherit`.
- `frontier`: предпочитай `gpt-5.6-sol`/`high`; fallback `gpt-5.6-terra`/`high` с пометкой degraded availability, затем `inherit`. `xhigh` допустим только для critical architecture, security, tenant/data-loss риска или конфликтующих evidence. Для любой critical задачи, требующей frontier capability (например, architecture, security, tenant/data-loss, production или deployment), если не осталось известной advertised frontier-capable model и доступен только неизвестный `inherit`, верни `needs_input`, а не понижай маршрут или не наследуй его; для noncritical работы normal fallback `inherit` сохраняется.

Default `FORK_TURNS` — `none`. Если без незаменимого conversational context нельзя выполнить slice, используй минимальное task-justified конечное положительное `N`. `all` наследует model/effort и требует опустить overrides. Не придумывай неподдерживаемые model names. Escalate для high/critical risk, cross-repo, architecture, public contracts/schema/proto, security/auth/tenant, production incidents, GitOps/deployment; capability-bound inconclusive attempt также требует escalation. De-escalate не более чем на одну lane и только для deterministic low-risk single-repo exact-I/O работы без architecture/security/contract/production/approval judgement. Missing evidence, authority или user input — не причина менять model route.

## Роли

| Роль | Task prefix | Когда применять | Write scope | Model lane | Контракт |
|---|---|---|---|---|---|
| Orchestrator | n/a | всегда | координационные действия | main-only | [orchestrator.md](orchestrator.md) |
| Explorer | explorer | reconnaissance | нет | fast | [explorer.md](explorer.md) |
| Architect | architect | design и DAG | нет | frontier | [architect.md](architect.md) |
| Architecture guardian | architecture_guardian | plan/diff architecture gate | нет | frontier | [architecture-guardian.md](architecture-guardian.md) |
| Test-maker | test_maker | executable acceptance baseline | только tests allowlist | balanced | [test-maker.md](test-maker.md) |
| Implementor | implementor | один DAG slice | production/docs allowlist | balanced | [implementor.md](implementor.md) |
| Reviewer | reviewer | code review | нет | balanced | [reviewer.md](reviewer.md) |
| QA | qa | adversarial behavior verification | нет в repository | balanced | [qa.md](qa.md) |
| DevOps | devops | GitOps desired state | `k8s` allowlist | frontier | [devops.md](devops.md) |
| Infrastructure reviewer | infrastructure_reviewer | GitOps review | нет | frontier | [infrastructure-reviewer.md](infrastructure-reviewer.md) |
| Deployment agent | deployment_agent | approved publication/rollout observation | только exact publish action | frontier | [deployment-agent.md](deployment-agent.md) |

## Машинный результат

Каждый субагент завершает ответ одной последней строкой, используя exact revision из `SubagentStart`:

```text
WGC_AGENT_RESULT: {"role":"<role>","verdict":"<role verdict>","phase":"<plan|diff только для architecture-guardian, иначе пусто>","input_revision":"<exact-input-revision>"}
```

Строка не заменяет артефакт и evidence. Оркестратор перепроверяет diff, команды и revision. Допустимые verdicts определены в role files и проверяются hooks с учётом профиля `implementation`.

## Независимость

- Implementor не совмещается с Test-maker, Reviewer или Architecture guardian.
- Architect не утверждает свой план.
- DevOps не является Infrastructure reviewer.
- Deployment agent не пишет application-код или manifests.
- Два write-агента не работают одновременно в одном repository или contract boundary.
