# Bugfix workflow

## State machine

```text
reported
  -> triaged
  -> evidence_ready
  -> reproduced | characterized_with_waiver
  -> root_cause_supported
  -> root_cause_approved
  -> fix_plan_approved
  -> test_assessment_ready
  -> implemented
  -> reviewed
  -> architecture_approved
  -> qa_passed
  -> ready
  -> deployed_healthy (только при разрешённом deployment)
```

Допустимые остановки: `needs_input`, `not_reproduced`, `blocked`, `deployment_not_authorized`, `deployment_failed`, `rolled_back`. Это честные состояния, а не неудача оркестратора.

## Основной поток

| Этап | Владелец | Вход | Выход | Gate |
|---|---|---|---|---|
| Intake | orchestrator | комментарий пользователя | `BugCase` | кейс не содержит выдуманных фактов |
| Triage | bug-triage | `BugCase` | `TriageReport` | `triaged` |
| Evidence | bug-investigator `phase=evidence` | кейс и triage | `EvidenceBundle` | `evidence_ready` |
| Reproduction | reproducer | кейс и evidence | `ReproductionReport` | `reproduced`, либо `characterized` с human waiver |
| RCA | bug-investigator `phase=rca` | reproduction + evidence | `RootCauseAnalysis` | `root_cause_supported` |
| RCA review | root-cause-reviewer | RCA + evidence | `RootCauseReviewReport` | `approved` |
| Design | architect | RCA | `FixPlan` | `approved` guardian |
| Test assessment | test-maker | RCA + approved plan | `TestAssessment` + conditional TestPlan | `assessment_ready` |
| Fix | implementor | approved plan + protected tests | `ImplementationReport` | `implemented` |
| Review | reviewer + guardian | current diff | reports | оба `approved` |
| QA | qa + conditional specialists | reviewed revision | QA reports | все `pass/approved` |
| Delivery | orchestrator | complete ledger | `BugfixReport` | `ready` |

## Маршруты и conditional gates

| Сигнал | Дополнительный агент | Дополнительный gate |
|---|---|---|
| UI, browser, PWA, realtime | browser-qa | browser reproduction + `pass` |
| auth, RBAC, permissions, tenant isolation | security-reviewer | `approved` |
| REST/gRPC/proto/schema/public export | contract-qa | `pass` и consumer compatibility |
| `k8s`, values, manifests, CI/CD | devops + infrastructure-reviewer | `prepared` + `approved` |
| Явный rollout/deploy approval | deployment-agent | `deployed_healthy` + smoke |

WebSocket event schema, event ordering/replay и reconnect protocol считаются contract boundary и активируют Contract QA.

Incident route не отменяет основной поток. Сначала стабилизируй понимание blast radius и release identity; emergency mitigation или rollback требует отдельного разрешения, а постоянное исправление всё равно проходит regression и review.

При возможной активной cross-tenant/PII утечке немедленно сообщи пользователю о security-incident risk и необходимости назначить human incident owner. Не отправляй внешние сообщения и не меняй систему без полномочий. Никогда не воспроизводи утечку чтением реальных foreign-tenant данных; используй synthetic canary tenants или уже существующие redacted evidence handles.

## Rework и invalidation

- `not_reproduced`: вернись к intake/evidence; production-код не менять. Исключительный waiver-маршрут линеен: (1) evidence однозначно локализует ветку; (2) architect выпускает ограниченный `CharacterizationPlan`; (3) guardian одобряет только этот plan; (4) человек явно задаёт `reproduction_waiver`; (5) test-maker создаёт failing task-owned `CharacterizationTest`; (6) reproducer независимо запускает его и возвращает `characterized`; (7) investigator формирует RCA, root-cause reviewer её одобряет; (8) architect, guardian и test-maker повторно выпускают финальные FixPlan/TestAssessment gates. CharacterizationTest может стать `reuse/update`, но waiver не разрешает `none` для critical fix. Ранние approvals не закрывают финальные gates.
- `root_cause_supported` не достигнут: продолжи read-only исследование или остановись `needs_input`; не выбирай «наиболее вероятную» правку.
- Guardian отклонил план: architect выпускает новую revision плана; старый approval недействителен.
- Implementor изменил protected test: отклони его результат, восстановление поручить test-maker/оркестратору без потери пользовательских изменений, обновить hashes и повторить реализацию.
- Reviewer/guardian/security/contract/QA нашли blocking defect: исправление создаёт новую revision и инвалидирует все downstream approvals.
- Любое изменение production diff после approval инвалидирует reviewer, guardian, QA, browser, security и contract gates.
- Изменение `k8s` diff инвалидирует DevOps, infrastructure review и deployment result.
- Failed deployment не исправлять вручную в кластере. Зафиксировать evidence, выбрать Git revert/forward fix через GitOps после разрешения, затем повторить review и rollout gates.

## Безопасная параллельность

- Bug-triage и первичный read-only project mapping можно вести параллельно после BugCase.
- Независимые evidence-запросы допустимы параллельно, если они не создают нагрузку и не раскрывают секреты.
- Reviewer и architecture guardian могут работать параллельно на одной immutable revision.
- Browser, security и contract QA могут работать параллельно после code review, если используют отдельные test data и не мешают друг другу.
- Write-агенты не работают параллельно в одном repository или общем contract boundary.

## Bounded supervision

Каждый assignment задаёт `TIME_BUDGET_MIN`, `CHECKPOINT_INTERVAL_MIN`, `MAX_EXTENSIONS` и объективные `PROGRESS_CRITERIA`. На каждом checkpoint оркестратор требует objective evidence: фактический diff, команды или другой измеримый результат; сообщение «работаю» прогрессом не считается. Extension возможен только в пределах `MAX_EXTENSIONS`, а его log обязан содержать reason, evidence и new boundary.

Первый stall требует correction или rescope. Повторный stall либо scope drift требует interrupt, inspection partial work и затем restart с уточнённым контрактом или split на меньшие slices. Временной budget — граница supervision, а не причина объявить результат готовым или blocked. Lifecycle hooks не являются таймерами и не обеспечивают checkpoints.

## Kubectl authorization boundary

Для будущей mutating `kubectl` поддержки необходим `KUBECTL_AUTHORIZATION` с exact `task`, `environment`, `context`, `expires_at`, `action_mode` и отдельным явным human approval. Текущие runtime role/authorization данные не авторитетны, поэтому mutating `kubectl` сегодня недоступен. DevOps role, actor metadata, `WGC_AGENT_RESULT`, marker или token не дают разрешения; поддержка требует отдельного reviewed изменения. Exact clean-cluster bootstrap остаётся отдельным фиксированным исключением.

## Разрешения

Bugfix authorization покрывает локальные правки и релевантные проверки в поставленном пользователем scope. Отдельно требуются: commit, push, PR, merge, изменение внешних данных, destructive cleanup, production mutation, release и deployment. Approval на deployment должен содержать environment и immutable release identity.
