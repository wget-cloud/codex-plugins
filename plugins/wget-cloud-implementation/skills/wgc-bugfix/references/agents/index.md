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

Каждому субагенту добавляй: «Работай только в выданном scope. Не сохраняй raw prompt/logs/secrets/PII. Не меняй внешние данные, Git publication или deployment без приложенного разрешения. Не объявляй весь bugfix завершённым. При нехватке evidence остановись с допустимым blocker verdict».

Поля времени задают bounded supervision, а не автоматическую остановку. На checkpoint оркестратор сравнивает objective evidence с `PROGRESS_CRITERIA`. Extension допускается только в пределах `MAX_EXTENSIONS` и логируется с reason, evidence и новой boundary. Первый stall требует correction или rescope; повторный stall либо scope drift — interrupt, inspection partial work и restart/split. Hooks не являются таймерами и не подтверждают соблюдение этих границ.

## Model routing policy

Model lane из registry — default для роли; перед launch оркестратор выбирает только model, advertised активным spawn tool, и записывает итог во все routing-поля envelope. `main-only` означает работу оркестратора в главном агенте: не spawn.

- `fast`: предпочитай `gpt-5.6-luna`/`low`; fallback `gpt-5.6-terra`/`low`, затем `gpt-5.6-sol`/`low`, затем `inherit`.
- `balanced`: предпочитай `gpt-5.6-terra`/`medium`; fallback `gpt-5.6-sol`/`medium`, затем `inherit`.
- `frontier`: предпочитай `gpt-5.6-sol`/`high`; fallback `gpt-5.6-terra`/`high` с пометкой degraded availability, затем `inherit`. `xhigh` допустим только для critical architecture, security, tenant/data-loss риска или конфликтующих evidence. Для любой critical задачи, требующей frontier capability (например, architecture, security, tenant/data-loss, production или deployment), если не осталось известной advertised frontier-capable model и доступен только неизвестный `inherit`, верни `needs_input`, а не понижай маршрут или не наследуй его; для noncritical работы normal fallback `inherit` сохраняется.

Default `FORK_TURNS` — `none`. Если без незаменимого conversational context нельзя выполнить slice, используй минимальное task-justified конечное положительное `N`. `all` наследует model/effort и требует опустить overrides. Не придумывай неподдерживаемые model names. Escalate для high/critical risk, cross-repo, architecture, public contracts/schema/proto, security/auth/tenant, production incidents, GitOps/deployment; capability-bound inconclusive attempt также требует escalation. Для Bug-investigator RCA всегда выбирай `frontier`. De-escalate не более чем на одну lane и только для deterministic low-risk single-repo exact-I/O работы без architecture/security/contract/production/approval judgement. Missing evidence, authority или user input — не причина менять model route.

## Core roles

| Роль | Task prefix | Этап | Write scope | Model lane | Контракт |
|---|---|---|---|---|---|
| Orchestrator | n/a | весь workflow | координационные действия | main-only | [orchestrator.md](orchestrator.md) |
| Bug-triage | bug_triage | triage | нет | fast | [bug-triage.md](bug-triage.md) |
| Bug-investigator | bug_investigator | evidence и RCA | нет | balanced | [bug-investigator.md](bug-investigator.md) |
| Reproducer | reproducer | reproduction/characterization | только task-owned test data | balanced | [reproducer.md](reproducer.md) |
| Root-cause reviewer | root_cause_reviewer | RCA gate | нет | frontier | [root-cause-reviewer.md](root-cause-reviewer.md) |
| Architect | architect | FixPlan | нет | frontier | [architect.md](architect.md) |
| Architecture guardian | architecture_guardian | plan/diff gates | нет | frontier | [architecture-guardian.md](architecture-guardian.md) |
| Test-maker | test_maker | adaptive TestAssessment; conditional regression test | tests allowlist только при add/update | balanced | [test-maker.md](test-maker.md) |
| Implementor | implementor | minimal fix | production/docs allowlist | balanced | [implementor.md](implementor.md) |
| Reviewer | reviewer | code review | нет | balanced | [reviewer.md](reviewer.md) |
| QA | qa | adversarial regression | нет в repository | balanced | [qa.md](qa.md) |

## Conditional roles

| Route signal | Роль | Task prefix | Model lane | Контракт |
|---|---|---|---|---|
| UI/PWA/realtime/browser | Browser QA | browser_qa | balanced | [browser-qa.md](browser-qa.md) |
| auth/RBAC/tenant/PII | Security reviewer | security_reviewer | frontier | [security-reviewer.md](security-reviewer.md) |
| REST/gRPC/proto/schema/events/public exports | Contract QA | contract_qa | frontier | [contract-qa.md](contract-qa.md) |
| `k8s`/CI desired-state diff | DevOps | devops | frontier | [devops.md](devops.md) |
| infrastructure diff | Infrastructure reviewer | infrastructure_reviewer | frontier | [infrastructure-reviewer.md](infrastructure-reviewer.md) |
| exact deployment approval | Deployment agent | deployment_agent | frontier | [deployment-agent.md](deployment-agent.md) |

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
