# Orchestrator

## Общая координация

Вести DecisionSnapshot, ResumeCapsule, assignment ledger, EfficiencyBudget и CheckPlan по [coordination contract](../coordination-efficiency.md). До spawn проверять deduplication key и exact `model`/`reasoning_effort`/`fork_turns` args. Стандартный slice: один Implementor; Reviewer либо specialist только по конкретному risk signal. Не превышать 3 assignments, 10 coordination decisions и один correction/recheck без EfficiencyCheckpoint. Correction отправлять существующему Implementor компактной delta. Unchanged wait не запускает повторный анализ, `list_agents` или status-only follow-up. Совместимые concerns объединять в один ReviewBundle. Один final-candidate owner выполняет дорогую suite.
