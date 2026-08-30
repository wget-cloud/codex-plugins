# Реестр агентов bugfix-конвейера

Оркестратор читает этот index полностью, но открывает role contract только непосредственно перед назначением роли. Не загружай downstream-роли заранее и не подключай conditional specialists без route signal.

## Общий assignment envelope

```text
BUG_CASE: <id и redacted symptom>
ROLE: <role>
PHASE: <evidence|rca|plan|diff либо пусто>
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
```

Каждому субагенту добавляй: «Работай только в выданном scope. Не сохраняй raw prompt/logs/secrets/PII. Не меняй внешние данные, Git publication или deployment без приложенного разрешения. Не объявляй весь bugfix завершённым. При нехватке evidence остановись с допустимым blocker verdict».

## Model routing policy

Model lane из registry — default для роли; перед launch оркестратор выбирает только model, advertised активным spawn tool, и записывает итог во все routing-поля envelope. `main-only` означает работу оркестратора в главном агенте: не spawn.

- `fast`: предпочитай `gpt-5.6-luna`/`low`; fallback `gpt-5.6-terra`/`low`, затем `gpt-5.6-sol`/`low`, затем `inherit`.
- `balanced`: предпочитай `gpt-5.6-terra`/`medium`; fallback `gpt-5.6-sol`/`medium`, затем `inherit`.
- `frontier`: предпочитай `gpt-5.6-sol`/`high`; fallback `gpt-5.6-terra`/`high` с пометкой degraded availability, затем `inherit`. `xhigh` допустим только для critical architecture, security, tenant/data-loss риска или конфликтующих evidence. Для любой critical задачи, требующей frontier capability (например, architecture, security, tenant/data-loss, production или deployment), если не осталось известной advertised frontier-capable model и доступен только неизвестный `inherit`, верни `needs_input`, а не понижай маршрут или не наследуй его; для noncritical работы normal fallback `inherit` сохраняется.

Default `FORK_TURNS` — `none`. Если без незаменимого conversational context нельзя выполнить slice, используй минимальное task-justified конечное положительное `N`. `all` наследует model/effort и требует опустить overrides. Не придумывай неподдерживаемые model names. Escalate для high/critical risk, cross-repo, architecture, public contracts/schema/proto, security/auth/tenant, production incidents, GitOps/deployment; capability-bound inconclusive attempt также требует escalation. Для Bug-investigator RCA всегда выбирай `frontier`. De-escalate не более чем на одну lane и только для deterministic low-risk single-repo exact-I/O работы без architecture/security/contract/production/approval judgement. Missing evidence, authority или user input — не причина менять model route.

## Core roles

| Роль | Этап | Write scope | Model lane | Контракт |
|---|---|---|---|---|
| Orchestrator | весь workflow | координационные действия | main-only | [orchestrator.md](orchestrator.md) |
| Bug-triage | triage | нет | fast | [bug-triage.md](bug-triage.md) |
| Bug-investigator | evidence и RCA | нет | balanced | [bug-investigator.md](bug-investigator.md) |
| Reproducer | reproduction/characterization | только task-owned test data | balanced | [reproducer.md](reproducer.md) |
| Root-cause reviewer | RCA gate | нет | frontier | [root-cause-reviewer.md](root-cause-reviewer.md) |
| Architect | FixPlan | нет | frontier | [architect.md](architect.md) |
| Architecture guardian | plan/diff gates | нет | frontier | [architecture-guardian.md](architecture-guardian.md) |
| Test-maker | regression contract | только tests allowlist | balanced | [test-maker.md](test-maker.md) |
| Implementor | minimal fix | production/docs allowlist | balanced | [implementor.md](implementor.md) |
| Reviewer | code review | нет | balanced | [reviewer.md](reviewer.md) |
| QA | adversarial regression | нет в repository | balanced | [qa.md](qa.md) |

## Conditional roles

| Route signal | Роль | Model lane | Контракт |
|---|---|---|---|
| UI/PWA/realtime/browser | Browser QA | balanced | [browser-qa.md](browser-qa.md) |
| auth/RBAC/tenant/PII | Security reviewer | frontier | [security-reviewer.md](security-reviewer.md) |
| REST/gRPC/proto/schema/events/public exports | Contract QA | frontier | [contract-qa.md](contract-qa.md) |
| `k8s`/CI desired-state diff | DevOps | frontier | [devops.md](devops.md) |
| infrastructure diff | Infrastructure reviewer | frontier | [infrastructure-reviewer.md](infrastructure-reviewer.md) |
| exact deployment approval | Deployment agent | frontier | [deployment-agent.md](deployment-agent.md) |

## Машинный результат

Каждый субагент завершает ответ одной последней строкой:

```text
WGC_AGENT_RESULT: {"role":"<role>","verdict":"<role verdict>","phase":"<role-required-phase-or-empty>","input_revision":"<exact-input-revision>"}
```

Hooks проверяют role/verdict/phase с учётом профиля `bugfix`. Оркестратор отдельно проверяет артефакт, evidence и актуальность revision.

## Независимость

Автор RCA не является Root-cause reviewer. Implementor не совмещается с Test-maker/Reviewer/Guardian. DevOps не является Infrastructure reviewer. Deployment agent не пишет source/manifests. При нехватке слотов роли запускаются последовательно, но полномочия не объединяются.
