# Full workflow details

Этот reference загружается только для Full. Full меняет глубину исследования, но не default team: один Terra Implementor исправляет подтверждённую причину и добавляет минимальный regression test. Investigator, Reviewer либо один specialist добавляется только при конкретной неопределённости/риске. Лимит 3 assignments и один correction batch из [coordination contract](coordination-efficiency.md) имеет приоритет; полный pipeline после finding не перезапускается.

# Bugfix workflow

## State machine

```text
reported
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
| Evidence | bug-investigator `phase=evidence` | `BugCase`; включает bounded triage | `EvidenceBundle` | `evidence_ready` |
| Reproduction | reproducer | кейс и evidence | `ReproductionReport` | `reproduced`, либо `characterized` с human waiver |
| RCA | bug-investigator `phase=rca` | reproduction + evidence | `RootCauseAnalysis` | `root_cause_supported` |
| RCA review | root-cause-reviewer | RCA + evidence | `RootCauseReviewReport` | `approved` |
| Design | architect только при architecture/ownership/compatibility/multi-slice signal; иначе investigator/orchestrator | RCA | bounded `FixPlan` | Guardian только для Full architecture concern |
| Test assessment | assessment owner; Test-maker только для regression add/update/protected critical | RCA + plan | `TestAssessment` + conditional TestPlan | `assessment_ready` |
| Fix | implementor | approved plan + protected tests | `ImplementationReport` | `implemented` |
| Review | reviewer; guardian только при изменённом architecture concern | current diff | reports | применимые `approved` |
| QA | conditional QA/specialists | reviewed revision | concern reports | только выбранные gates `pass/approved` |
| Delivery | orchestrator | complete ledger | `BugfixReport` | `ready` |

## Маршруты и conditional gates

| Сигнал | Дополнительный агент | Дополнительный gate |
|---|---|---|
| auth, RBAC, permissions, tenant isolation | security-reviewer | `approved` |
| REST/gRPC/proto/schema/public export | contract-qa | `pass` и consumer compatibility |
| `k8s`, values, manifests, CI/CD | devops + infrastructure-reviewer | `prepared` + `approved` |
| Явный rollout/deploy approval | deployment-agent | `deployed_healthy` + smoke |

WebSocket event schema, event ordering/replay и reconnect protocol считаются contract boundary и активируют Contract QA.

Compact localized route не создаёт отдельные Triage, Architect, Guardian или QA assignments без соответствующего signal. Incident route всё равно требует доказательства причины и regression, но не означает автоматический запуск всего каталога ролей.

До production fix заморозь affected behavior/RPC inventory и решения, общие для нескольких slices: wire contract, tenant/auth semantics, data ownership, concurrency/idempotency/background work, compatibility, cutover и rollback. Exact FixPlan должен иметь `FREEZE_STATUS: approved`. Implementor получает один bounded vertical fix slice; не дроби execution path между write-агентами по слоям и не переноси весь large service одним assignment.

При возможной активной cross-tenant/PII утечке немедленно сообщи пользователю о security-incident risk и необходимости назначить human incident owner. Не отправляй внешние сообщения и не меняй систему без полномочий. Никогда не воспроизводи утечку чтением реальных foreign-tenant данных; используй synthetic canary tenants или уже существующие redacted evidence handles.

## Rework и invalidation

- `not_reproduced`: вернись к intake/evidence; production-код не менять. Исключительный waiver-маршрут линеен: (1) evidence однозначно локализует ветку; (2) architect выпускает ограниченный `CharacterizationPlan`; (3) guardian одобряет только этот plan; (4) человек явно задаёт `reproduction_waiver`; (5) test-maker создаёт failing task-owned `CharacterizationTest`; (6) reproducer независимо запускает его и возвращает `characterized`; (7) investigator формирует RCA, root-cause reviewer её одобряет; (8) architect, guardian и test-maker повторно выпускают финальные FixPlan/TestAssessment gates. CharacterizationTest может стать `reuse/update`, но waiver не разрешает `none` для critical fix. Ранние approvals не закрывают финальные gates.
- `root_cause_supported` не достигнут: продолжи read-only исследование или остановись `needs_input`; не выбирай «наиболее вероятную» правку.
- Guardian отклонил план: architect выпускает новую revision плана; старый approval недействителен.
- Implementor изменил protected test: отклони его результат, восстановление поручить test-maker/оркестратору без потери пользовательских изменений, обновить hashes и повторить реализацию.
- Reviewer/guardian/security/contract/QA нашли blocking defect: исправление создаёт новую revision и инвалидирует зависящие от изменённого concern downstream approvals.
- Изменение production diff после approval создаёт новую `DIFF_IDENTITY`; selective invalidation из coordination contract определяет, какие reviewer/guardian/QA/security/contract gates повторить.
- Изменение `k8s` diff инвалидирует DevOps, infrastructure review и deployment result.
- Failed deployment не исправлять вручную в кластере. Зафиксировать evidence, выбрать Git revert/forward fix через GitOps после разрешения, затем повторить review и rollout gates.

## Безопасная параллельность

- Bug-triage и первичный read-only project mapping можно вести параллельно после BugCase.
- Независимые evidence-запросы допустимы параллельно, если они не создают нагрузку и не раскрывают секреты.
- Reviewer и architecture guardian могут работать параллельно только на одной замороженной `DIFF_IDENTITY`.
- Security и contract QA могут работать параллельно после code review, если используют отдельные test data и не мешают друг другу.
- Write-агенты не работают параллельно в одном repository или общем contract boundary.

## Bounded supervision

Каждый assignment задаёт `TIME_BUDGET_MIN`, `CHECKPOINT_INTERVAL_MIN`, `MAX_EXTENSIONS` и объективные `PROGRESS_CRITERIA`. После spawn используй cursor-based event-driven wait: первое интерактивное ожидание 45–60 секунд, затем exponential backoff до supervision boundary без status-only follow-up. На checkpoint оркестратор требует objective evidence: фактический diff, команды или другой измеримый результат; сообщение «работаю» прогрессом не считается. Extension возможен только в пределах `MAX_EXTENSIONS`, а его log обязан содержать reason, evidence и new boundary.

Первый stall требует correction или rescope. Повторный stall либо scope drift требует interrupt, inspection partial work и затем restart с уточнённым контрактом или split на меньшие slices. Третье повторение того же stable finding/reason требует `ContradictionReport` и решения о rescope/user input, а не нового restart. После compaction до новых назначений восстанови ResumeCapsule и сверь Git/agent state. Временной budget — граница supervision, а не причина объявить результат готовым или blocked.

## Kubectl authorization boundary

Для будущей mutating `kubectl` поддержки необходим `KUBECTL_AUTHORIZATION` с exact `task`, `environment`, `context`, `expires_at`, `action_mode` и отдельным явным human approval. Текущие runtime role/authorization данные не авторитетны, поэтому mutating `kubectl` сегодня недоступен. DevOps role, actor metadata, `WGC_AGENT_RESULT`, marker или token не дают разрешения; поддержка требует отдельного reviewed изменения. Exact clean-cluster bootstrap остаётся отдельным фиксированным исключением.

## Разрешения

Bugfix authorization покрывает локальные правки и релевантные проверки в поставленном пользователем scope. Отдельно требуются: commit, push, PR, merge, изменение внешних данных, destructive cleanup, production mutation, release и deployment. Approval на deployment должен содержать environment и immutable release identity.
