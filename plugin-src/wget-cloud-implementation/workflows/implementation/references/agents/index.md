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
```

`TASK_NAME` строится как `<Task prefix>_<snake_case task slice>[_<positive ordinal>]`: prefix берётся из таблицы, slice обязателен, ordinal добавляй только при collision/restart sibling-задачи. Полное итоговое значение `TASK_NAME` передай без изменений в `spawn_agent.task_name`. Orchestrator использует `n/a`, не spawn и требует запуска основной задачи на своей `frontier` lane.

Каждому субагенту добавляй: «Работай только в выданном scope. Сохраняй существующие изменения. Не выполняй commit, push, PR, merge, release или deployment без приложенного разрешения. Не объявляй всю задачу завершённой. Если scope недостаточен, верни `needs_input`».

Поля времени задают bounded supervision, а не автоматическую остановку. На checkpoint оркестратор сравнивает objective evidence с `PROGRESS_CRITERIA`. Extension допускается только в пределах `MAX_EXTENSIONS` и логируется с reason, evidence и новой boundary. Первый stall требует correction или rescope; повторный stall либо scope drift — interrupt, inspection partial work и restart/split. Hooks не являются таймерами и не подтверждают соблюдение этих границ.

## Model routing policy

Используй минимальную достаточную lane из таблиц: `economy` → Luna/low, `balanced` → Terra/medium, `frontier` → Sol/high. Fallback и service-tier ограничения: [model policy](../model-routing.md).

## Роли

Не держи более трёх активных субагентов одновременно.

| Роль | Task prefix | Когда применять | Write scope | Model lane | Контракт |
|---|---|---|---|---|---|
| Orchestrator | n/a | всегда | координационные действия | frontier | [orchestrator.md](orchestrator.md) |
| Explorer | explorer | reconnaissance | нет | economy | [explorer.md](explorer.md) |
| Architect | architect | design и DAG | нет | frontier | [architect.md](architect.md) |
| Architecture guardian | architecture_guardian | plan/diff architecture gate | нет | frontier | [architecture-guardian.md](architecture-guardian.md) |
| Test-maker | test_maker | adaptive TestAssessment; conditional tests | только tests allowlist при add/update | balanced | [test-maker.md](test-maker.md) |
| Implementor | implementor | один DAG slice | production/docs allowlist | balanced | [implementor.md](implementor.md) |
| Reviewer | reviewer | code review | нет | frontier | [reviewer.md](reviewer.md) |
| QA | qa | adversarial behavior verification | нет в repository | balanced | [qa.md](qa.md) |
| DevOps | devops | GitOps desired state | `k8s` allowlist | balanced | [devops.md](devops.md) |
| Infrastructure reviewer | infrastructure_reviewer | GitOps review | нет | frontier | [infrastructure-reviewer.md](infrastructure-reviewer.md) |
| Deployment agent | deployment_agent | approved publication/rollout observation | только exact publish action | economy | [deployment-agent.md](deployment-agent.md) |

## Машинный результат

Каждый субагент завершает ответ одной последней строкой, используя exact revision из `SubagentStart`:

```text
WGC_AGENT_RESULT: {"role":"<role>","verdict":"<role verdict>","phase":"<plan|diff только для architecture-guardian, иначе пусто>","input_revision":"<exact-input-revision>"}
```

Строка не заменяет артефакт и evidence. Оркестратор перепроверяет diff, команды и revision. Допустимые verdicts определены в role files и проверяются hooks с учётом профиля `implementation`.

Test-maker использует расширенный flat marker из [test-assessment.md](../test-assessment.md) и verdict `assessment_ready`; generic marker выше для него недостаточен.

Architect marker также обязательно добавляет `plan_revision`, `minimum_test_criticality` и принадлежащий Architect в этом профиле `acceptance_revision`; exact пример находится в [architect.md](architect.md).

Architecture Guardian в `phase=plan` добавляет exact текущий `plan_revision`; missing/stale revision не закрывает gate. Exact marker находится в [architecture-guardian.md](architecture-guardian.md).

## Независимость

- Implementor не совмещается с Test-maker, Reviewer или Architecture guardian.
- Architect не утверждает свой план.
- DevOps не является Infrastructure reviewer.
- Deployment agent не пишет application-код или manifests.
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
| YouTrack Operator | youtrack_operator | разрешённые записи карточек и Stage | exact MCP allowlist | economy | [youtrack-operator.md](youtrack-operator.md) |

Assignment дополнительно содержит TRACKER=youtrack, ISSUE_SCOPE (exact project keys/IDs), PLAN_REVISION, DECISION_REFS, ESTIMATE_REFS и MUTATION_ALLOWLIST; секреты не передаются. Registry задаёт существующие marker fields; `phase` новых ролей пустой. Effort Estimator не совмещается с автором оцениваемой постановки/плана.

При любом scope эпика назначается отдельный [Project Manager](project-manager.md) с phase=lifecycle для [переходов Stage](../epic-lifecycle.md). Verdicts: stage_ready/awaiting_user/stage_blocked; обязательный EpicStagePlan. Прежние phase/verdicts сохраняются для их исходных назначений. В implementation/bugfix PM работает только в lifecycle; он read-only и не совмещается с Operator.

| Role | Task prefix | When | Write scope | Model lane | Contract |
|---|---|---|---|---|---|
| Project Manager | project_manager | Stage эпика при изменении дочерней задачи | read-only | balanced | [project-manager.md](project-manager.md) |
