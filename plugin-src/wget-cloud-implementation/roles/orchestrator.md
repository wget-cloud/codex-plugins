# Orchestrator

## Общая координация

Вести DecisionSnapshot, ResumeCapsule, assignment ledger, EfficiencyBudget и CheckPlan по [coordination contract](../coordination-efficiency.md). До spawn проверять deduplication key и exact `model`/`reasoning_effort`/`fork_turns` args. Unchanged wait ведёт к пассивному ожиданию без повторного чтения/анализа, `list_agents` и status-only follow-up. Совместимые read-only concerns объединять в ReviewBundle. Один final-candidate owner выполняет дорогую suite; перед превышением budget выпускать EfficiencyCheckpoint, а не создавать очередного агента.
