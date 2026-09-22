# Модель чата и контекст

Маршрутизируй каждую роль по минимальной достаточной GPT-6 lane. Размер задачи, режим Full и длительность работы сами по себе не повышают модель. Для spawned-роли передавай явные `model`/`reasoning_effort` overrides. Orchestrator использует `balanced`; активная задача не переключает модель задним числом.

Service tier не является quality gate и не меняет lane.

- `economy`: `gpt-6-luna/low`. Bounded reconnaissance, точные операции и механическая проверка.
- `focused`: `gpt-6-luna/medium`. Product/project work, assessment, estimation, routine review и routine QA без сложного технического решения.
- `balanced`: `gpt-6-sol/low`. Реализация, RCA, protected tests, GitOps preparation и технические gates с нетривиальным риском.
- `architecture`: `gpt-6-sol/medium`. Только Architect и только для реального изменения boundaries, ownership, contracts, compatibility, migration/cutover или межмодульного DAG.

`gpt-6-astra` полностью запрещена: не выбирай её по просьбе, как fallback или для эскалации. Для Sol разрешены только `low` и `medium`; `high`, `xhigh`, `max` и `ultra` запрещены основной задаче и любому spawn. До `spawn_agent` проверь, что exact `model`, `reasoning_effort` и lane совпадают с assignment. Отсутствие override, наследование родительской модели, недопустимый effort или подмена lane запрещают spawn. Если допустимая комбинация недоступна, верни blocker.

Автоматический fallback разрешён только из Luna в `gpt-6-sol/low` с записанным `FALLBACK_REASON`. Обратный fallback для write-owner или critical specialist запрещён. Architect на `gpt-6-sol/medium` не понижается автоматически. Недоступность Sol для critical specialist означает blocker.

Штатный `gpt-6-sol/medium` принадлежит только Architect. Для другого специалиста допустима одна одноразовая medium-эскалация на WorkItem без смены роли, если одновременно:

- есть риск потери данных, tenant/security bypass, несовместимого public contract, необратимой migration либо опасной concurrency;
- завершена попытка на `gpt-6-sol/low`;
- targeted evidence, test или decomposition не сняли blocker;
- assignment содержит `MEDIUM_ESCALATION_ROLE`, `MEDIUM_ESCALATION_REASON`, `BLOCKER_EVIDENCE`, `FAILED_LOW_EFFORT_ATTEMPT`, `CRITICAL_INVARIANT`, `EXPECTED_DECISION`.

Full/large scope, стиль, coverage, обычная неопределённость и большой diff не являются основанием. Эскалация разрешена одному агенту один раз и не распространяется на команду. Если medium не решил blocker, создай blocker/follow-up; effort выше medium запрещён.

Reviewer и QA используют `focused` для routine evidence. Переводи конкретное назначение в `balanced` только при техническом риске, записанном в `ROUTING_BASIS`. Architect не пишет production code, не выполняет RCA/security verdict и не проектирует функции: он выпускает один `ArchitecturePacket` на `architecture_revision` и переиспользует его до изменения boundaries.

Явно передавай `fork_turns: none`; `all` запрещён. Положительное N допустимо только с `FORK_JUSTIFICATION`, когда минимальный незаменимый контекст нельзя выразить artifact/capsule. Передавай узкое assignment с role file, domain profile, revisions, scope, acceptance и evidence handles. Не держи более трёх активных субагентов.

Ограничивай проверки изменённым поведением и repository requirements. После успешных проверок не расширяй их без новых изменений, failures или unresolved critical risk. Делегируй только роли выбранного маршрута.

Источник рекомендаций GPT-6: https://developers.openai.com/api/docs/guides/latest-model
