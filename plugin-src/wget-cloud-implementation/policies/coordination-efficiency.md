# Координация и контроль стоимости

Этот контракт обязателен до первого назначения субагента. Стандартное поведение оптимизирует скорость поставки и расход токенов: один write-owner, targeted checks и только доказанно нужные независимые gates. Не создавай отдельный профиль или режим для этого поведения.

## DecisionSnapshot и assignment ledger

Оркестратор ведёт компактный `DecisionSnapshot` с revision IDs work item/item, scope, acceptance, plan, contract, architecture, security и test assessment. Assignment получает только актуальные revisions, нужные artifacts и evidence handles; история чата не является источником истины.

Каждое назначение имеет стабильный `ASSIGNMENT_KEY` из role, phase, slice, scope, revisions и expected artifact, а retry — явный `RETRY_REASON`. Ledger хранит `active|completed|failed|stale`; одинаковый active key не дублируется, completed result переиспользуется до релевантной invalidation. Finding получает стабильный ключ `role + invariant + location + scenario`.

После compaction сначала восстанови `ResumeCapsule`: current phase, revisions, active/completed assignments, blocking findings, diff identity, protected hashes, valid check cache и next transitions. Сверь capsule с Git, agent и tracker state до нового spawn/follow-up.

## Неоднозначные решения и UI

После сбора доступного evidence не трать дорогую модель на угадывание product semantics, UX preference, ownership или несовместимых architecture alternatives. Субагент возвращает root-оркестратору `DECISION_REQUIRED` с `decision_id`, 2–3 взаимоисключающими вариантами, первым recommended вариантом, краткими tradeoffs, затронутым scope и evidence refs. Только root задаёт вопрос пользователю.

Если нативный `request_user_input` доступен в Plan mode, root использует его для кликабельного выбора. В Default mode или при отсутствии инструмента задай один компактный plain-text вопрос с теми же вариантами. Плагин не переключает mode и не имитирует UI директивами. Не повторяй тот же `decision_id` без нового evidence или изменившихся вариантов. Пока решение ожидается, продолжай независимые slices и блокируй только зависимую часть.

## EfficiencyBudget

До execution задай `MAX_AGENT_ASSIGNMENTS`, `MAX_COORDINATION_DECISIONS`, `MAX_UNCHANGED_WAIT_STREAK`, `MAX_PASSIVE_WAIT_MINUTES`, `MAX_EXPENSIVE_CHECKS`, `MAX_REWORK_ROUNDS` и `CHECKPOINT_BOUNDARY`. Default implementation/bugfix/item slice: максимум 3 assignments, 10 coordination decisions, 1 unchanged wait без нового анализа, 10 минут passive wait, 1 дорогая final suite и 1 correction/recheck. Нормальный маршрут использует компактного Task Assessor и одного Implementor; третий assignment — один Reviewer либо specialist вместо набора gates. Product discovery и подтверждённый новый critical risk могут получить записанное расширение, но сложность сама по себе не разрешает полный role pipeline.

Перед превышением бюджета останови новые назначения и выпусти `EfficiencyCheckpoint`: полученный diff/evidence, дубликаты, причина расхода, оставшиеся risks и решение `continue-existing | merge-scope | split | needs_input`. `continue-existing` использует `followup_task` текущему владельцу с компактной delta; новый agent для correction запрещён, пока текущий доступен. Не создавай отдельного Token Auditor. Отсутствие meaningful diff/evidence за checkpoint boundary запрещает бесконечное продолжение того же assignment.

## Контекст и ожидание

Каждый spawn явно передаёт exact `model`, `reasoning_effort` и `fork_turns`. Норма — `fork_turns: none`; `all` запрещён. Положительное N требует `FORK_JUSTIFICATION`, почему минимальный контекст нельзя выразить artifact/capsule.

Используй cursor-based event-driven wait: один интерактивный wait, затем пассивное ожидание до event/checkpoint. Неизменившийся результат не запускает повторное чтение thread/plan, reasoning-цикл, `list_agents`, progress-сообщение пользователю или status-only сообщение агенту; passive wait time не является coordination decision. После одного unchanged wait обнови только компактный supervision checkpoint. Второй timeout без нового evidence требует проверить partial result и решить `continue-existing | interrupt | needs_input`, а не запускать новый polling loop.

## Candidate, reviews и проверки

Один write-owner отвечает за связный vertical slice/item и сам пишет production code и обычные tests. Не запускай полный plan/test/implementation/review/guardian/QA pipeline ни для slice, ни повторно после finding. Один компактный Task Assessor фиксирует `RiskMatrix` и test ownership; отдельные Architect, Guardian и Test-maker назначаются только когда без независимого решения нельзя безопасно продолжать.

Перед read-only gate один раз зафиксируй `DIFF_IDENTITY`. По умолчанию Orchestrator сам проверяет bounded candidate. Если независимый review оправдан, один Reviewer получает единый `ReviewBundle` для correctness, contract, security, data и architecture concerns в пределах своей компетенции. Отдельный specialist заменяет, а не дополняет обычного Reviewer, кроме подтверждённой необходимости независимости. Findings исправляются одним correction batch существующим Implementor и получают один targeted recheck; полный pipeline не перезапускается.

`CheckPlan` задаёт T0/T1/T2/T3 command IDs, owner, trigger и cache key. Write-owner выполняет targeted compile/unit T0 и один affected-scope T1. T2 выполняется один раз только перед service/release boundary, когда его требует repository policy либо пользователь; T3 — только в явно разрешённом delivery scope. Reviewer/Guardian/QA не повторяют успешную идентичную suite. Coverage improvement, полный race/lint/build matrix и дополнительные happy-path tests не блокируют обычный startup slice, если repository gate прямо этого не требует.

Минимум готовности для изменённого поведения: один meaningful regression test; contract/proto check при изменении контракта; auth/tenant negative case при соответствующем риске; race check при concurrency. Full repository suite, image build, deployment check, максимизация coverage и exhaustive edge cases не запускаются по умолчанию. Некритичные findings фиксируются как residual risk или follow-up, а не перезапускают pipeline.

На границе большого сервиса, epic batch или длительного этапа выпусти компактный `HandoffCapsule`: outcome, tree/item/tracker revisions, remaining scope/risks, valid evidence, next input, `STOP_AFTER_BOUNDARY` и `NEXT_SCOPE_ALLOWED`. При stop=true после completion не создавай новых назначений и верни управление пользователю. Следующий этап не получает историю внутренних correction loops.
