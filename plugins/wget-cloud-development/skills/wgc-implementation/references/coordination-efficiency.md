# Координация без повторной работы

Этот контракт обязателен до первого назначения субагента. Он дополняет role contracts и gates, но не ослабляет независимость ролей или repository requirements.

## DecisionSnapshot

Оркестратор ведёт компактный `DecisionSnapshot` с ревизиями `work_item`, `scope`, `acceptance`, `plan`, `contract`, `architecture`, `security` и `test_plan`. В assignment передаются только актуальные ревизии, нужные артефакты и evidence handles; свободный пересказ истории не является источником истины.

Новое evidence сначала применяется как delta к снимку. Повторный полный Task Assessment нужен только если меняются mode, domains, risk signals, обязательные checks, path boundaries или acceptance. Иначе обнови относящуюся ревизию и сохрани маршрут.

До production implementation заморозь решения, которые меняют несколько slices: wire contract, tenant/auth semantics, data ownership, concurrency/idempotency/background work, compatibility, cutover и rollback. Shared platform primitive допустим при двух доказанных consumers либо как явно согласованный repository baseline.

## Freeze gate и размер WorkItem

Перед первым production write установи `FREEZE_STATUS: approved` только после независимого Architecture Guardian approval для exact `plan_revision`. Freeze-пакет содержит полный affected behavior/RPC inventory, data model и ownership, auth/tenant matrix, contracts/events, compatibility/migration, background/retry semantics, acceptance revision и DAG. Missing либо unresolved cross-slice поле оставляет `FREEZE_STATUS: pending`; Test-maker и Implementor не запускаются.

Large service или более одного независимо проверяемого behavior family разделяется на bounded vertical WorkItems/DAG slices. Один slice должен давать связный contract/provider/consumer либо законченный service behavior и собственный completion condition. Не переносить весь сервис с десятками RPC одним непрерывным assignment/turn. Следующий зависимый slice начинается после integration gate предыдущего; discovery всего сервиса не означает разрешение реализовать весь найденный scope.

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
```

После compaction/restart сначала восстанови capsule, сверь Git tree, active agents и revisions и пометь несовпавшие артефакты `stale`. До этой сверки нельзя spawn/follow-up прежнего Explorer, Architect, Test-maker или Implementor. Свободный пересказ истории и порядковый suffix имени не восстанавливают ledger.

## Assignment ledger и дедупликация

Каждое назначение получает:

- `ASSIGNMENT_KEY`: стабильный hash/ID от role, phase, task slice, scope, DecisionSnapshot revisions и expected artifact;
- `RETRY_REASON`: `n/a` либо конкретные new evidence, invalidated revision, failed/blocked result или исправляемый contract violation;
- `DIFF_IDENTITY`: hash/ID immutable tree для review/QA, иначе `n/a`.

Ledger хранит состояния `active|completed|failed|stale`. Перед каждым spawn/follow-up атомарно проверь, что same `ASSIGNMENT_KEY` отсутствует в active и completed с актуальными зависимостями. Не запускай второй active assignment с тем же key. Completed result переиспользуется, пока его зависимости актуальны. Ordinal в имени не является основанием для retry. Если изменился только вход, отправь существующему агенту компактный delta; новый запуск допустим только с новым key и `RETRY_REASON`.

Finding получает стабильный ключ `role + invariant + location + scenario`. Повтор того же finding обновляет evidence/status, а не создаёт новый цикл.

## Контекст и ожидание

`FORK_TURNS: none` — норма; `all` запрещён. Положительное N допустимо только для минимального незаменимого фрагмента разговора, который нельзя безопасно выразить артефактом. Reviewer получает собственный компактный контекст и immutable diff, а не историю implementor.

После назначения используй cursor-based event-driven ожидание. Первое интерактивное ожидание ограничь 45–60 секундами; при неизменившемся состоянии не отправляй агенту сообщение и увеличивай следующую границу exponential backoff до supervision boundary. Не делай фиксированный 30-секундный polling, повторный `list_agents` без нового сигнала или status-only follow-up. Checkpoint нужен при `needs_attention`, завершении, изменении revision, достижении supervision boundary или доказанном stall. Пользовательский progress update не является input агенту.

## Вертикальные slices и freeze

Implementor получает минимальный связный vertical slice, который можно собрать и проверить: contract/provider/consumer path либо законченный service behavior. Не дроби работу по слоям только ради числа агентов. Параллельные write-slices разрешены лишь без общего repository/contract owner.

Orchestrator координирует и проверяет evidence, но не пишет production code или tests. Architect не выполняет plan/diff-review собственного решения. Один `Test-maker owner` владеет TestAssessment/protected paths для exact `test_plan` revision; replacement требует `REPLACEMENT_REASON`, нового `TEST_OWNER_ID` и invalidation прежнего TestAssessment/protected hashes. Эти роли нельзя объединять даже после compaction или нехватки слотов.

Перед параллельными Reviewer, Architecture Guardian и conditional specialists зафиксируй `DIFF_IDENTITY` и запрети writes. Любая правка создаёт новую identity и инвалидирует только зависящие от изменённого concern результаты.

## Ступени проверки и evidence cache

- `T0`: узкий compile/unit check после небольшой правки.
- `T1`: affected module/service/consumer checks после завершения slice.
- `T2`: полные repository-required tests, race/vet/lint/build/coverage после diff freeze.
- `T3`: image/scan/contract smoke/integration и delivery evidence один раз для release candidate, если применимо.

Повторяй только invalidated ступени. Cache key включает check ID, tree/diff identity, environment fingerprint, scoped paths и dependency/config identity. Failed run, неизвестная зависимость или изменение source/lock/config отменяет соответствующий cache entry. Ledger хранит только privacy-safe metadata, не raw commands/output.

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
