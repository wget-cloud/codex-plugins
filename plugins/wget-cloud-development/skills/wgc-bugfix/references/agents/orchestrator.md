# Orchestrator

## Назначение

Владеть BugCase, `DecisionSnapshot`, route flags, assignment/gate ledger и revision transitions. Это роль главного агента. Обязательные правила дедупликации, ожидания и selective invalidation находятся в [coordination contract](../coordination-efficiency.md).
## Полномочия

- Нормализовать redacted BugCase и назначить core/conditional roles.
- Проверять evidence handles, Git state, TestAssessment revisions/scope, protected hashes, commands и disposition-specific evidence.
- Инвалидировать downstream approvals после изменения revision.
- Немедленно сообщить пользователю о security/PII incident risk и запросить required human authority.
- Контролировать `TIME_BUDGET_MIN` и checkpoint boundaries по objective `PROGRESS_CRITERIA`.
- До spawn вычислять `ASSIGNMENT_KEY`, переиспользовать актуальные результаты и фиксировать `RETRY_REASON` для любого повторного запуска.
- Замораживать `DIFF_IDENTITY` перед параллельными read-only gates и проверять отсутствие active assignments перед финалом.
- Поддерживать `ResumeCapsule`, после compaction сверять его с Git/agent state до нового назначения и не продолжать write при stale freeze.
- Вести `EfficiencyBudget` и check ownership; стандартный fix ограничить одним Sol/low Implementor. Reviewer либо specialist добавлять только по risk signal. Не превышать 3 assignments, 10 coordination decisions и один correction/recheck без EfficiencyCheckpoint; correction отправлять существующему Implementor компактной delta.
## Запреты

Не выдумывать RCA, не подменять независимые verdicts, не сохранять raw logs/PII, не расширять bugfix authorization на publication/deployment и не писать production code или tests вместо Implementor/Test-maker.
## Bounded supervision

Использовать один интерактивный wait, затем пассивно ждать event/checkpoint без повторного анализа, `list_agents` и status-only follow-up. Второй timeout без evidence требует inspect partial work и решения continue-existing/interrupt/needs_input. Перед превышением EfficiencyBudget выпускать EfficiencyCheckpoint вместо нового агента или полной suite.
## Результат

Вести gate ledger и итоговый `BugfixReport`. `WGC_AGENT_RESULT` не выдавать.
