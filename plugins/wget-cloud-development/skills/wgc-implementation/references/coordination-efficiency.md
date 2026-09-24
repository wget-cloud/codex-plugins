# Координация без повторной работы

Этот контракт обязателен до первого назначения субагента. Стандартное поведение оптимизирует скорость поставки и расход токенов: один write-owner, targeted checks и только доказанно нужные независимые gates. Отдельного fast/startup профиля нет.

## DecisionSnapshot

Оркестратор ведёт компактный `DecisionSnapshot` с ревизиями `work_item`, `scope`, `acceptance`, `plan`, `contract`, `architecture`, `security` и `test_plan`. В assignment передаются только актуальные ревизии, нужные артефакты и evidence handles; свободный пересказ истории не является источником истины.

Новое evidence сначала применяется как delta к снимку. Повторный полный Task Assessment нужен только если меняются mode, domains, risk signals, обязательные checks, path boundaries или acceptance. Иначе обнови относящуюся ревизию и сохрани маршрут.

До production implementation заморозь решения, которые меняют несколько slices: wire contract, tenant/auth semantics, data ownership, concurrency/idempotency/background work, compatibility, cutover и rollback. Shared platform primitive допустим при двух доказанных consumers либо как явно согласованный repository baseline.

## Freeze gate и размер WorkItem

Для Full, multi-slice или изменённой architecture/ownership/compatibility boundary перед первым production write установи `FREEZE_STATUS: approved` только после независимого Architecture Guardian approval exact `plan_revision`. Для bounded Light/Standard без таких изменений используй `FREEZE_STATUS: n/a`; TaskAssessment и exact acceptance остаются обязательными. Missing либо unresolved cross-slice поле оставляет Full freeze `pending`; Test-maker и Implementor не запускаются.

Large service или более одного независимо проверяемого behavior family разделяется на bounded vertical WorkItems/DAG slices. Один slice должен давать связный contract/provider/consumer либо законченный service behavior и собственный completion condition. Не переносить весь сервис с десятками RPC одним непрерывным assignment/turn. Следующий зависимый slice начинается после integration gate предыдущего; discovery всего сервиса не означает разрешение реализовать весь найденный scope.

Для migration большого gRPC-сервиса сначала один раз собери полный service inventory и freeze-пакет, затем группируй по 5–10 связанных RPC или одной behavior family. Не запускай полный plan/test/implementation/review/guardian/QA pipeline отдельно для каждого handler, файла, документа или внутреннего scaffold-коммита. Один транш по умолчанию имеет одного write-owner; independent Reviewer добавляется только при нетривиальном risk/diff, а specialist — только вместо дополнительного общего review по наиболее важному risk signal. Service-level Architect и Guardian plan переиспользуются, пока frozen decisions не изменились.

Когда пользователь выбирает функционал нового сервиса, до первого approval собери один `ServiceDecisionPacket`: inventory реально используемых сценариев, границы владения, зависимости, варианты объёма, открытые продуктовые решения и критерии готовности. Сгруппируй независимые вопросы в один раунд после исследования; зависимые вопросы задавай после соответствующего ответа, не переоткрывая уже решённое. После выбора покажи один согласованный service plan и получи разрешение на реализацию выбранного объёма. Это разрешение покрывает его внутренние транши, даже если repository требует для них редакции плана или отдельные плановые файлы. Не превращай технический `plan_revision`, freeze gate, документ или completion gate транша в новый пользовательский approval. Запроси новое решение только при изменении продуктовой семантики, acceptance, ownership, совместимости или объёма; commit/push/PR/release/deployment сохраняют собственные отдельные разрешения.

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

## Неоднозначные решения и UI

После сбора evidence не угадывай product semantics, ownership или несовместимые architecture alternatives дорогой моделью. Субагент возвращает root `DECISION_REQUIRED` с `decision_id`, 2–3 взаимоисключающими вариантами, recommended первым, tradeoffs, scope и evidence refs. Только root спрашивает пользователя: используй доступный нативный выбор (`request_user_input` в Plan mode или `request_user_input_async` в Default mode); если инструмента нет, задай один компактный вопрос с вариантами обычным сообщением. Не переключай mode и не повторяй `decision_id` без нового evidence. Если ответ ещё не получен к завершению независимой работы, оставь в финальном сообщении сам вопрос и все варианты: пользователь может ответить обычным сообщением, даже если UI не показал или закрыл панель. Агент не задаёт срок принятия продуктового решения; исчезновение UI или timeout инструмента не означают отказ или согласие. Продолжай независимые транши и блокируй только зависимый.

## EfficiencyBudget

До execution задай на WorkItem или транш: `MAX_AGENT_ASSIGNMENTS`, `MAX_COORDINATION_DECISIONS`, `MAX_UNCHANGED_WAIT_STREAK`, `MAX_PASSIVE_WAIT_MINUTES`, `MAX_EXPENSIVE_CHECKS`, `MAX_REWORK_ROUNDS` и `CHECKPOINT_BOUNDARY`. Default: максимум 3 assignments, 10 coordination decisions, 1 unchanged wait без нового анализа, 10 минут passive wait при supervision субагента, 1 дорогая T2 suite и 1 correction/recheck. `MAX_PASSIVE_WAIT_MINUTES` не ограничивает время ответа пользователя на вопрос. Нормальный маршрут использует одного Implementor; второй assignment — Reviewer только при нетривиальном risk/diff, третий — один specialist вместо набора gates. Сложность сама по себе не разрешает полный role pipeline.

Перед превышением бюджета останови новые назначения и выпусти `EfficiencyCheckpoint`: полученный diff/evidence, причина расхода, дубликаты, оставшиеся риски и решение `continue-existing | merge-scope | split | needs_input`. Correction отправляй существующему Implementor через `followup_task` компактной delta; replacement запрещён, пока текущий агент доступен. Не создавай Token Auditor и не трать новый агент только на подсчёт.

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

После назначения используй cursor-based event-driven ожидание. После одного unchanged wait переходи к пассивному ожиданию без повторного чтения thread/plan, reasoning-цикла, `list_agents`, progress update или status-only follow-up. Второй timeout без нового evidence требует inspect partial result и решения `continue-existing | interrupt | needs_input`, а не нового polling loop.

Ожидание решения пользователя не является supervision агента: когда независимой работы больше нет, закончи ход с одним устойчивым вопросом и жди нового сообщения. Не вызывай `sleep`, циклический `wait`, не публикуй напоминания «жду ответа» и не создавай искусственный deadline. При позднем ответе сначала сверь `decision_id` и актуальность зависимого плана; если они не изменились, применяй ответ без повторного исследования и согласования.

## Вертикальные slices и freeze

Implementor получает минимальный связный vertical slice, который можно собрать и проверить: contract/provider/consumer path либо законченный service behavior. Не дроби работу по слоям только ради числа агентов. Параллельные write-slices разрешены лишь без общего repository/contract owner.

Implementor владеет production code и минимальными unit/integration tests своего транша. Orchestrator выполняет inline `RiskMatrix`; отдельные Architect, Task Assessor, Guardian и Test-maker назначаются только когда без независимого решения нельзя безопасно продолжать. Test-maker нужен лишь для protected critical baseline, а не для обычного happy path или каждого bugfix.

Orchestrator координирует и проверяет evidence, но не пишет production code или tests. Architect не выполняет plan/diff-review собственного решения. Один `Test-maker owner` владеет TestAssessment/protected paths для exact `test_plan` revision; replacement требует `REPLACEMENT_REASON`, нового `TEST_OWNER_ID` и invalidation прежнего TestAssessment/protected hashes. Эти роли нельзя объединять даже после compaction или нехватки слотов.

Перед read-only gate зафиксируй `DIFF_IDENTITY`. По умолчанию bounded candidate проверяет Orchestrator. Если review оправдан, один Reviewer получает `ReviewBundle`; отдельный specialist заменяет обычного Reviewer, кроме подтверждённой необходимости независимости. Findings исправляются одним correction batch, полный pipeline не перезапускается.

## Ступени проверки и evidence cache

- `T0`: узкий compile/unit check после небольшой правки.
- `T1`: affected module/service/consumer checks после завершения slice.
- `T2`: полные repository-required tests, race/vet/lint/build/coverage один раз на service/release boundary, если это требует repository policy или пользователь.
- `T3`: image/scan/contract smoke/integration и delivery evidence один раз для release candidate, если применимо.

Минимум готовности: meaningful regression test для изменённого поведения; contract/proto check при изменении контракта; auth/tenant negative case при таком риске; race check при concurrency. Full repository suite, image/deploy checks, максимизация coverage и exhaustive edge cases не запускаются по умолчанию. Некритичные findings становятся residual risk/follow-up и не перезапускают pipeline.

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
