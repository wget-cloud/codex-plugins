# Модель чата и контекст

Маршрутизируй каждую роль по минимальной достаточной GPT-6 lane. Размер задачи и режим Full сами по себе не повышают модель. Orchestrator использует `balanced`.

- `economy`: `gpt-6-luna/low` — reconnaissance и механические операции.
- `focused`: `gpt-6-luna/medium` — assessment, routine review и routine QA.
- `balanced`: `gpt-6-sol/low` — реализация, tests, RCA, GitOps preparation и technical gates.
- `architecture`: `gpt-6-sol/medium` — только Architect при изменении boundaries, ownership, contracts, compatibility, migration/cutover или DAG.

`gpt-6-astra` полностью запрещена, включая явный запрос и fallback. Для Sol разрешены только `low` и `medium`; `high`, `xhigh`, `max` и `ultra` запрещены. Каждый spawn обязан явно передать exact `model`, `reasoning_effort` и `fork_turns`; наследование и недопустимый lane запрещают spawn.

Автоматический fallback разрешён только Luna → `gpt-6-sol/low` с `FALLBACK_REASON`. Write-owner/critical specialist не понижается на Luna; Architect не имеет downgrade fallback. Если допустимая модель недоступна, верни blocker.

Sol/medium штатно использует только Architect. Один другой специалист может сохранить роль и однократно получить medium на WorkItem лишь при critical data/tenant/security/public-contract/irreversible-migration/concurrency риске после неудачной Sol/low попытки. Обязательны `MEDIUM_ESCALATION_ROLE`, `MEDIUM_ESCALATION_REASON`, `BLOCKER_EVIDENCE`, `FAILED_LOW_EFFORT_ATTEMPT`, `CRITICAL_INVARIANT`, `EXPECTED_DECISION`. Full/large, стиль, coverage и размер diff не достаточны; повторная эскалация и effort выше medium запрещены.

Routine Reviewer/QA используют `focused`, техническое назначение — `balanced` с risk в `ROUTING_BASIS`. Architect выпускает один переиспользуемый `ArchitecturePacket` на `architecture_revision`; он не пишет code, не выполняет RCA/security verdict и не проектирует функции.

Явно используй `fork_turns: none`; `all` запрещён. Положительное N требует `FORK_JUSTIFICATION`. После успешных targeted checks не расширяй проверки без нового diff, failure или unresolved critical risk.

Источник рекомендаций GPT-6: https://developers.openai.com/api/docs/guides/latest-model
