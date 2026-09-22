# Orchestrator

## Общая координация

Вести DecisionSnapshot, ResumeCapsule, assignment ledger, EfficiencyBudget и CheckPlan по [coordination contract](../coordination-efficiency.md). До spawn проверять deduplication key и exact `model`/`reasoning_effort`/`fork_turns` args. Использовать event-driven wait с backoff; после двух unchanged waits ждать event/checkpoint, не отправлять status-only follow-up. Один final-candidate owner выполняет дорогую suite; read-only gates используют её evidence. Перед превышением budget выпускать EfficiencyCheckpoint, а не создавать очередного агента.
