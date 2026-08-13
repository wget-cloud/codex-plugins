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
```

Каждому субагенту добавляй: «Работай только в выданном scope. Не сохраняй raw prompt/logs/secrets/PII. Не меняй внешние данные, Git publication или deployment без приложенного разрешения. Не объявляй весь bugfix завершённым. При нехватке evidence остановись с допустимым blocker verdict».

## Core roles

| Роль | Этап | Write scope | Контракт |
|---|---|---|---|
| Orchestrator | весь workflow | координационные действия | [orchestrator.md](orchestrator.md) |
| Bug-triage | triage | нет | [bug-triage.md](bug-triage.md) |
| Bug-investigator | evidence и RCA | нет | [bug-investigator.md](bug-investigator.md) |
| Reproducer | reproduction/characterization | только task-owned test data | [reproducer.md](reproducer.md) |
| Root-cause reviewer | RCA gate | нет | [root-cause-reviewer.md](root-cause-reviewer.md) |
| Architect | FixPlan | нет | [architect.md](architect.md) |
| Architecture guardian | plan/diff gates | нет | [architecture-guardian.md](architecture-guardian.md) |
| Test-maker | regression contract | только tests allowlist | [test-maker.md](test-maker.md) |
| Implementor | minimal fix | production/docs allowlist | [implementor.md](implementor.md) |
| Reviewer | code review | нет | [reviewer.md](reviewer.md) |
| QA | adversarial regression | нет в repository | [qa.md](qa.md) |

## Conditional roles

| Route signal | Роль | Контракт |
|---|---|---|
| UI/PWA/realtime/browser | Browser QA | [browser-qa.md](browser-qa.md) |
| auth/RBAC/tenant/PII | Security reviewer | [security-reviewer.md](security-reviewer.md) |
| REST/gRPC/proto/schema/events/public exports | Contract QA | [contract-qa.md](contract-qa.md) |
| `k8s`/CI desired-state diff | DevOps | [devops.md](devops.md) |
| infrastructure diff | Infrastructure reviewer | [infrastructure-reviewer.md](infrastructure-reviewer.md) |
| exact deployment approval | Deployment agent | [deployment-agent.md](deployment-agent.md) |

## Машинный результат

Каждый субагент завершает ответ одной последней строкой:

```text
WGC_AGENT_RESULT: {"role":"<role>","verdict":"<role verdict>","phase":"<role-required-phase-or-empty>","input_revision":"<exact-input-revision>"}
```

Hooks проверяют role/verdict/phase с учётом профиля `bugfix`. Оркестратор отдельно проверяет артефакт, evidence и актуальность revision.

## Независимость

Автор RCA не является Root-cause reviewer. Implementor не совмещается с Test-maker/Reviewer/Guardian. DevOps не является Infrastructure reviewer. Deployment agent не пишет source/manifests. При нехватке слотов роли запускаются последовательно, но полномочия не объединяются.
