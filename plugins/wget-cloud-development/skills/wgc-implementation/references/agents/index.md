# Реестр агентов implementation-конвейера

Открывай файл роли непосредственно перед её назначением и не загружай downstream-роли заранее. Оркестратор читает этот index полностью, а затем передаёт субагенту конкретный role contract вместе с task scope.

Если в `SKILL.md` установлено `MVP_SKIP_TESTS: true`, передавай флаг каждому назначенному агенту. Убери test paths из `ALLOW_PATHS`, добавь их в `DENY_PATHS`; Test-maker не назначай. Всем ролям запрещено писать, менять и запускать тесты и проверять coverage. Смена флага инвалидирует TestAssessment и CheckPlan.

## Общий assignment envelope

```text
WORK_ITEM: <id и цель>
ROLE: <role>
MVP_SKIP_TESTS: <true|false из SKILL.md>
TASK_NAME: <role prefix>_<snake slice>[_ordinal]
TASK_SLICE: <одна ограниченная подзадача>
REPOSITORIES: <разрешённые repo>
ALLOW_PATHS: <разрешённые пути>
DENY_PATHS: <запрещённые пути, включая protected tests>
INPUT_ARTIFACTS: <план, findings, acceptance criteria>
DECISION_SNAPSHOT: <актуальные revision IDs и dependency map>
RESUME_CAPSULE_REVISION: <exact restored capsule revision|n/a before first capsule>
ASSIGNMENT_KEY: <stable role+phase+slice+scope+revisions+artifact ID>
RETRY_REASON: <n/a|new evidence|invalidated revision|failed/blocked result|contract correction>
DIFF_IDENTITY: <immutable reviewed tree ID|n/a>
FREEZE_STATUS: <pending|approved|stale|n/a>
LOCAL_INSTRUCTIONS: <AGENTS.md и обязательные docs>
EXPECTED_COMMANDS: <проверки>
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
FORK_JUSTIFICATION: <n/a for none|why an artifact cannot replace the exact N turns>
SPAWN_PREFLIGHT: <exact model + reasoning_effort + fork_turns args verified>
TIME_BUDGET_MIN: <positive supervision budget in minutes>
CHECKPOINT_INTERVAL_MIN: <positive checkpoint interval in minutes>
MAX_EXTENSIONS: <non-negative extension limit>
PROGRESS_CRITERIA: <objective evidence required at checkpoints and completion>
EFFICIENCY_BUDGET: <max assignments/waits/expensive checks/rework + checkpoint boundary>
```

`TASK_NAME` строится как `<Task prefix>_<snake_case task slice>[_<positive ordinal>]`: prefix берётся из таблицы, slice обязателен, ordinal добавляй только при collision/restart sibling-задачи. Полное итоговое значение `TASK_NAME` передай без изменений в `spawn_agent.task_name`. Orchestrator использует `n/a`, не spawn и работает на `balanced`; `architecture` штатно принадлежит только Architect.

Каждому субагенту добавляй: «Работай только в выданном scope. Сохраняй существующие изменения. Не выполняй commit, push, PR, merge, release или deployment без приложенного разрешения. Не объявляй всю задачу завершённой. Если scope недостаточен, верни `needs_input`».

Перед spawn проверь assignment ledger из [coordination contract](../coordination-efficiency.md): одинаковый active key не дублируется, completed key переиспользуется, а retry требует изменённого key и явного `RETRY_REASON`. После compaction сначала восстанови и сверь `RESUME_CAPSULE_REVISION`. Вызов `spawn_agent` без явных exact `model`, `reasoning_effort` и `fork_turns` запрещён; обычное значение fork — `none`, `all` запрещён.

Поля времени задают bounded supervision, а не автоматическую остановку. Используй event-driven ожидание вместо частого polling. На checkpoint оркестратор сравнивает objective evidence с `PROGRESS_CRITERIA`. Extension допускается только в пределах `MAX_EXTENSIONS` и логируется с reason, evidence и новой boundary. Первый stall требует correction или rescope; повторный stall либо scope drift — interrupt, inspection partial work и restart/split.

## Model routing policy

Используй минимальную достаточную lane: `economy` → Luna/low, `focused` → Luna/medium, `balanced` → Sol/low, `architecture` → Sol/medium. Astra и Sol выше `medium` запрещены. Fallback/эскалация: [model policy](../model-routing.md).

## Роли

Не держи более трёх активных субагентов одновременно.

| Роль | Task prefix | Когда применять | Write scope | Model lane | Контракт |
|---|---|---|---|---|---|
| Orchestrator | n/a | всегда | координационные действия | balanced | [orchestrator.md](orchestrator.md) |
| Explorer | explorer | reconnaissance | нет | economy | [explorer.md](explorer.md) |
| Architect | architect | design и DAG | нет | architecture | [architect.md](architect.md) |
| Architecture guardian | architecture_guardian | plan/diff architecture gate | нет | balanced | [architecture-guardian.md](architecture-guardian.md) |
| Test-maker | test_maker | TestAssessment; protected critical tests только при независимой ценности | protected tests allowlist | balanced | [test-maker.md](test-maker.md) |
| Implementor | implementor | один vertical tranche | production/docs и обычные slice-local tests | balanced | [implementor.md](implementor.md) |
| Reviewer | reviewer | code review; технический risk переводит assignment в balanced | нет | focused | [reviewer.md](reviewer.md) |
| QA | qa | adversarial behavior verification | нет в repository | focused | [qa.md](qa.md) |
| DevOps | devops | GitOps desired state | `k8s` allowlist | balanced | [devops.md](devops.md) |
| Infrastructure reviewer | infrastructure_reviewer | GitOps review | нет | balanced | [infrastructure-reviewer.md](infrastructure-reviewer.md) |
| Deployment agent | deployment_agent | approved publication/rollout observation | только exact publish action | economy | [deployment-agent.md](deployment-agent.md) |

## Машинный результат

Каждый субагент завершает ответ одной последней строкой, используя exact revision из `SubagentStart`:

```text
WGC_AGENT_RESULT: {"role":"<role>","verdict":"<role verdict>","phase":"<plan|diff только для architecture-guardian, иначе пусто>","input_revision":"<exact-input-revision>"}
```

Строка не заменяет артефакт и evidence. Оркестратор связывает её с ledger по exact `input_revision`/`ASSIGNMENT_KEY` и перепроверяет diff, команды и допустимость role/verdict/phase. Однозначный marker без двоеточия перед валидным JSON можно локально нормализовать; неоднозначный JSON требует correction.

Test-maker использует расширенный flat marker из [test-assessment.md](../test-assessment.md) с обязательным `test_ownership` и verdict `assessment_ready`; generic marker выше для него недостаточен.

Architect marker также обязательно добавляет `plan_revision`, `minimum_test_criticality` и принадлежащий Architect в этом профиле `acceptance_revision`; exact пример находится в [architect.md](architect.md).

Architecture Guardian в `phase=plan` добавляет exact текущий `plan_revision`; missing/stale revision не закрывает gate. Exact marker находится в [architecture-guardian.md](architecture-guardian.md).

## Независимость

- Implementor не меняет protected tests Test-maker, не совмещается с Reviewer или Architecture guardian, но владеет обычными непомеченными slice-local tests.
- Architect не утверждает свой план.
- Architect не выполняет Guardian plan/diff gate, а Orchestrator не пишет production code или tests.
- Один Test-maker owner владеет exact test-plan revision; replacement требует нового `TEST_OWNER_ID` и `REPLACEMENT_REASON`.
- DevOps не является Infrastructure reviewer.
- Deployment agent не пишет application-код или manifests.
- Два write-агента не работают одновременно в одном repository или contract boundary.

## Дополнительные роли v7

| Роль | Task prefix | Когда применять | Write scope | Model lane | Контракт |
|---|---|---|---|---|---|
| contract-qa | contract_qa | по TaskAssessment | read-only | balanced | [contract-qa.md](contract-qa.md) |
| data-migration-reviewer | data_migration_reviewer | по TaskAssessment | read-only | balanced | [data-migration-reviewer.md](data-migration-reviewer.md) |
| reliability-reviewer | reliability_reviewer | по TaskAssessment | read-only | balanced | [reliability-reviewer.md](reliability-reviewer.md) |
| security-reviewer | security_reviewer | по TaskAssessment | read-only | balanced | [security-reviewer.md](security-reviewer.md) |
| task-assessor | task_assessor | по TaskAssessment | read-only | focused | [task-assessor.md](task-assessor.md) |

## Выбор команды

[TaskAssessment](../task-assessment.md) определяет применимость ролей; таблица — каталог, не требование запускать всех. Assessment revision хранится в assignment ledger и не обязана повторяться в marker. Skills не передают control друг другу.
