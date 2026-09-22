# Координация без повторной работы

Этот контракт обязателен до первого назначения субагента. Он дополняет role contracts и gates, но не ослабляет независимость ролей или repository requirements.

## DecisionSnapshot

Оркестратор ведёт компактный `DecisionSnapshot` с ревизиями `work_item`, `scope`, `acceptance`, `plan`, `contract`, `architecture`, `security` и `test_plan`. В assignment передаются только актуальные ревизии, нужные артефакты и evidence handles; свободный пересказ истории не является источником истины.

Новое evidence сначала применяется как delta к снимку. Повторный полный Task Assessment нужен только если меняются mode, domains, risk signals, обязательные checks, path boundaries или acceptance. Иначе обнови относящуюся ревизию и сохрани маршрут.

До production implementation заморозь решения, которые меняют несколько slices: wire contract, tenant/auth semantics, data ownership, concurrency/idempotency/background work, compatibility, cutover и rollback. Shared platform primitive допустим при двух доказанных consumers либо как явно согласованный repository baseline.

## Freeze gate и размер WorkItem

Для Full, multi-slice или изменённой architecture/ownership/compatibility boundary перед первым production write установи `FREEZE_STATUS: approved` только после независимого Architecture Guardian approval exact `plan_revision`. Для bounded Light/Standard без таких изменений используй `FREEZE_STATUS: n/a`; TaskAssessment и exact acceptance остаются обязательными. Missing либо unresolved cross-slice поле оставляет Full freeze `pending`; Test-maker и Implementor не запускаются.

Large service или более одного независимо проверяемого behavior family разделяется на bounded vertical WorkItems/DAG slices. Один slice должен давать связный contract/provider/consumer либо законченный service behavior и собственный completion condition. Не переносить весь сервис с десятками RPC одним непрерывным assignment/turn. Следующий зависимый slice начинается после integration gate предыдущего; discovery всего сервиса не означает разрешение реализовать весь найденный scope.

Для migration большого gRPC-сервиса сначала один раз собери полный service inventory и freeze-пакет, затем группируй по 5–10 связанных RPC или одной behavior family. Не запускай полный plan/test/implementation/review/guardian/QA pipeline отдельно для каждого handler, файла, документа или внутреннего scaffold-коммита. Один транш по умолчанию имеет одного write-owner и одного independent Reviewer; остальные роли добавляются только по risk signal либо invalidated concern. Service-level Architect и Guardian plan переиспользуются, пока frozen decisions не изменились.

Изменение frozen auth, contract, ownership, data или compatibility решения создаёт новую revision, останавливает зависимый write slice и инвалидирует только затронутые plan/test/implementation/review evidence. Продолжать реализацию поверх `FREEZE_STATUS: pending|stale` запрещено.

## ResumeCapsule после compaction

До долгого ожидания и после каждого принятого gate оркестратор обновляет компактный `ResumeCapsule`:

```text
WORK_ITEM
CURRENT_PHASE
DECISION_SNAPSHOT_REVISIONS
APPROVED_PLAN_REVISION
FREEZE_STATUS
ACTIVE_ASSIGNMENTS
COMPLETED_ASSIGNMENTS
BLOCKING_FINDINGS
DIFF_IDENTITY
PROTECTED_TEST_HASHES
VALID_CHECK_CACHE
NEXT_ALLOWED_TRANSITIONS
EFFICIENCY_BUDGET
SERVICE_TARGET
REMAINING_SERVICE_SCOPE
STOP_AFTER_SERVICE
SERVICE_COMPLETION_CONDITION
NEXT_SERVICE_ALLOWED
```

После compaction/restart сначала восстанови capsule, сверь Git tree, active agents и revisions и пометь несовпавшие артефакты `stale`. До этой сверки нельзя spawn/follow-up прежнего Explorer, Architect, Test-maker или Implementor. Свободный пересказ истории и порядковый suffix имени не восстанавливают ledger.

На завершении сервиса выпусти `ServiceHandoff`: outcome, commit/tree identity, remaining RPC/risks, valid evidence и следующий service input. При `STOP_AFTER_SERVICE=true` после completion condition очисти active ledger, установи `NEXT_SERVICE_ALLOWED=false`, не создавай новых назначений и верни управление пользователю. Иначе следующий сервис получает только handoff, без истории correction loops.

## EfficiencyBudget

До execution задай на WorkItem или транш: `MAX_AGENT_ASSIGNMENTS`, `MAX_COORDINATION_DECISIONS`, `MAX_UNCHANGED_WAIT_STREAK`, `MAX_PASSIVE_WAIT_MINUTES`, `MAX_EXPENSIVE_CHECKS`, `MAX_REWORK_ROUNDS` и `CHECKPOINT_BOUNDARY`. Default обычного транша: 4 assignments, 2 unchanged waits без нового анализа, 1 дорогая T2 suite, 1 correction/recheck; specialist gate по новому risk signal требует записанного budget extension. Бюджет не ослабляет обязательный safety gate и не превращает незавершённую работу в success.

Перед превышением бюджета останови новые назначения и выпусти `EfficiencyCheckpoint`: полученный diff/evidence, причина расхода, дубликаты, оставшиеся риски и решение `continue | merge-scope | split | needs_input`. Не создавай Token Auditor и не трать новый агент только на подсчёт. Если за одну checkpoint boundary нет meaningful diff/evidence, не продолжай тем же assignment бесконечно.

## Assignment ledger и дедупликация

Каждое назначение получает:

- `ASSIGNMENT_KEY`: стабильный hash/ID от role, phase, task slice, scope, DecisionSnapshot revisions и expected artifact;
- `RETRY_REASON`: `n/a` либо конкретные new evidence, invalidated revision, failed/blocked result или исправляемый contract violation;
- `DIFF_IDENTITY`: hash/ID immutable tree для review/QA, иначе `n/a`.

Ledger хранит состояния `active|completed|failed|stale`. Перед каждым spawn/follow-up атомарно проверь, что same `ASSIGNMENT_KEY` отсутствует в active и completed с актуальными зависимостями. Не запускай второй active assignment с тем же key. Completed result переиспользуется, пока его зависимости актуальны. Ordinal в имени не является основанием для retry. Если изменился только вход, отправь существующему агенту компактный delta; новый запуск допустим только с новым key и `RETRY_REASON`.

Finding получает стабильный ключ `role + invariant + location + scenario`. Повтор того же finding обновляет evidence/status, а не создаёт новый цикл.

## Контекст и ожидание

Между supervision boundaries применяй exponential backoff.

`FORK_TURNS: none` — норма; `all` запрещён. Положительное N допустимо только для минимального незаменимого фрагмента разговора, который нельзя безопасно выразить артефактом. Reviewer получает собственный компактный контекст и immutable diff, а не историю implementor.

После назначения используй cursor-based event-driven ожидание. Первое интерактивное ожидание ограничь 45–60 секундами. Неизменившийся результат ведёт прямо к следующему пассивному wait без повторного чтения thread/plan, reasoning-цикла, `list_agents` или сообщения агенту; считай время отдельно от coordination decisions. После двух unchanged waits обнови только компактный supervision checkpoint и жди event/границу, не создавая status-only follow-up. Пользовательский progress update не является input агенту.

## Вертикальные slices и freeze

Implementor получает минимальный связный vertical slice, который можно собрать и проверить: contract/provider/consumer path либо законченный service behavior. Не дроби работу по слоям только ради числа агентов. Параллельные write-slices разрешены лишь без общего repository/contract owner.

Implementor владеет production code и обычными unit/integration tests своего транша. Test-maker нужен отдельно только для TestAssessment и protected tests, независимость которых оправдана critical security/tenant/data/migration/public-contract/concurrency invariant или доказанным regression risk. Не защищай весь test tree и не создавай отдельного test-maker ради механического happy-path теста, который reviewer может проверить вместе с diff.

Orchestrator координирует и проверяет evidence, но не пишет production code или tests. Architect не выполняет plan/diff-review собственного решения. Один `Test-maker owner` владеет TestAssessment/protected paths для exact `test_plan` revision; replacement требует `REPLACEMENT_REASON`, нового `TEST_OWNER_ID` и invalidation прежнего TestAssessment/protected hashes. Эти роли нельзя объединять даже после compaction или нехватки слотов.

Перед параллельными Reviewer, Architecture Guardian и conditional specialists зафиксируй `DIFF_IDENTITY` и запрети writes. Любая правка создаёт новую identity и инвалидирует только зависящие от изменённого concern результаты.

## Ступени проверки и evidence cache

- `T0`: узкий compile/unit check после небольшой правки.
- `T1`: affected module/service/consumer checks после завершения slice.
- `T2`: полные repository-required tests, race/vet/lint/build/coverage после diff freeze.
- `T3`: image/scan/contract smoke/integration и delivery evidence один раз для release candidate, если применимо.

Повторяй только invalidated ступени. Cache key включает check ID, tree/diff identity, environment fingerprint, scoped paths и dependency/config identity. Failed run, неизвестная зависимость или изменение source/lock/config отменяет соответствующий cache entry. Ledger хранит только privacy-safe metadata, не raw commands/output.

Для одной `DIFF_IDENTITY` назначь одного owner каждой дорогой команды. Идентичную успешную T2/T3 команду в том же environment не повторяют Reviewer, Guardian и QA. Docs-only или test-comment diff не запускает Go race/build заново без доказанной executable dependency. Immutable snapshot/tree identity создаётся один раз на candidate, а не перед каждым read-only gate. Для large service предпочитай чистый отдельный worktree; если это невозможно, один раз зафиксируй baseline и не пересобирай архив после каждого чтения.

## Selective invalidation

- behavior/source diff инвалидирует связанные T0–T2, code review, QA и затронутые specialist gates;
- contract diff дополнительно инвалидирует consumers, Contract QA и compatibility evidence;
- architecture/ownership diff инвалидирует Architecture Guardian и зависимые plan slices;
- test plan/protected test diff инвалидирует test assessment и regression evidence;
- infra/release identity diff инвалидирует T3, infrastructure/deployment gates;
- documentation-only diff не сбрасывает code gates, если не меняет executable contract.

При неясной зависимости выбирай более широкий безопасный набор, но фиксируй причину. Не сбрасывай все gates автоматически.

## Ограничитель rework-цикла

Для одного stable finding допустимы: исходный verdict, одна correction и один recheck. Третье появление того же finding/reason запрещает слепой restart: оркестратор формирует `ContradictionReport` с конфликтующими требованиями, evidence, owner решения и допустимыми вариантами, затем rescope/split либо запрашивает решение пользователя. Новый доказанный дефект или новая revision начинают отдельный цикл с новым ключом.

## Готовность и метрики

Перед финалом нет active assignments, stale required artifacts, незакрытых blocking findings или проверок, относящихся к другой `DIFF_IDENTITY`.

Для улучшения процесса можно хранить только агрегаты: runtime по роли, суммарное wait time/count, retries и причины, invalidations, accepted/duplicate findings, число дорогих checks и cache reuse. Не сохраняй prompts, reasoning, raw command output, production logs, secrets или customer data. Метрики диагностируют задержки, но не являются gate.
