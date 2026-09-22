# Координация и контроль стоимости

Этот контракт обязателен до первого назначения субагента. Он ограничивает повторную работу, но не ослабляет product, security, architecture, review, tracker или delivery gates.

## DecisionSnapshot и assignment ledger

Оркестратор ведёт компактный `DecisionSnapshot` с revision IDs work item/item, scope, acceptance, plan, contract, architecture, security и test assessment. Assignment получает только актуальные revisions, нужные artifacts и evidence handles; история чата не является источником истины.

Каждое назначение имеет стабильный `ASSIGNMENT_KEY` из role, phase, slice, scope, revisions и expected artifact, а retry — явный `RETRY_REASON`. Ledger хранит `active|completed|failed|stale`; одинаковый active key не дублируется, completed result переиспользуется до релевантной invalidation. Finding получает стабильный ключ `role + invariant + location + scenario`.

После compaction сначала восстанови `ResumeCapsule`: current phase, revisions, active/completed assignments, blocking findings, diff identity, protected hashes, valid check cache и next transitions. Сверь capsule с Git, agent и tracker state до нового spawn/follow-up.

## EfficiencyBudget

До execution задай `MAX_AGENT_ASSIGNMENTS`, `MAX_COORDINATION_DECISIONS`, `MAX_UNCHANGED_WAIT_STREAK`, `MAX_PASSIVE_WAIT_MINUTES`, `MAX_EXPENSIVE_CHECKS`, `MAX_REWORK_ROUNDS` и `CHECKPOINT_BOUNDARY`. Default обычного implementation/item slice: 4 assignments, 2 unchanged waits без нового анализа, 1 дорогая final suite, 1 correction/recheck. Full RCA, product discovery или новый specialist risk получает отдельный обоснованный budget extension.

Перед превышением бюджета останови новые назначения и выпусти `EfficiencyCheckpoint`: полученный diff/evidence, дубликаты, причина расхода, оставшиеся risks и решение `continue | merge-scope | split | needs_input`. Не создавай отдельного Token Auditor. Отсутствие meaningful diff/evidence за checkpoint boundary запрещает бесконечное продолжение того же assignment.

## Контекст и ожидание

Каждый spawn явно передаёт exact `model`, `reasoning_effort` и `fork_turns`. Норма — `fork_turns: none`; `all` запрещён. Положительное N требует `FORK_JUSTIFICATION`, почему минимальный контекст нельзя выразить artifact/capsule.

Используй cursor-based event-driven wait: 45–60 секунд первый интерактивный wait, затем exponential backoff. Неизменившийся результат ведёт прямо к пассивному wait без повторного чтения thread/plan, reasoning-цикла, `list_agents` или сообщения агенту; passive wait time не является coordination decision. После двух unchanged waits обнови только компактный supervision checkpoint и жди event/границу.

## Candidate, reviews и проверки

Один write-owner отвечает за связный vertical slice/item. Не запускай полный plan/test/implementation/review/guardian/QA pipeline отдельно на каждый handler, файл, документ или scaffold-коммит. Service/item-level plan approval переиспользуется, пока frozen decisions не изменились.

Перед параллельными read-only gates один раз зафиксируй `DIFF_IDENTITY`. Совместимые concerns объединяй в один `ReviewBundle` независимого reviewer с отдельными verdicts; отдельный specialist нужен только при требуемой независимости или особом evidence boundary. Guardian diff и specialist/QA назначаются только для затронутого concern. Для stable finding допустимы initial verdict, одна correction и один recheck; следующее повторение требует contradiction report и rescope/user decision.

`CheckPlan` задаёт T0/T1/T2/T3 command IDs, owner, trigger и cache key. Write-owner выполняет targeted T0 и один affected-scope T1; один final-candidate owner выполняет дорогую T2; T3 запускается один раз только в разрешённом delivery scope. Reviewer/Guardian/QA не повторяют успешную идентичную suite в той же environment/diff identity. Docs-only diff не инвалидирует executable checks без доказанной зависимости.

На границе большого сервиса, epic batch или длительного этапа выпусти компактный `HandoffCapsule`: outcome, tree/item/tracker revisions, remaining scope/risks, valid evidence, next input, `STOP_AFTER_BOUNDARY` и `NEXT_SCOPE_ALLOWED`. При stop=true после completion не создавай новых назначений и верни управление пользователю. Следующий этап не получает историю внутренних correction loops.
