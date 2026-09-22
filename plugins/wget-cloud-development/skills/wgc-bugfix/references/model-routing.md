# Модель чата и контекст

Маршрутизируй все роли по минимальной достаточной GPT-5.6 lane. Стандартная диагностика и исправление, включая Full по размеру, остаются на Terra; размер задачи сам по себе не разрешает Sol. Orchestrator использует `balanced`. Активная задача не переключает модель задним числом.

- `economy`: `gpt-5.6-luna/low`; fallback — `gpt-5.6-terra/low`. Для bounded reconnaissance, точных операций и механической проверки.
- `balanced`: `gpt-5.6-terra/medium`; fallback — `gpt-5.6-luna/medium`, затем `gpt-5.6-sol/medium`. Для обычной инженерной реализации и тестирования.
- `frontier`: `gpt-5.6-sol/medium`; fallback — `gpt-5.6-terra/medium`. Только для подтверждённого сложного blocker, неразрешимого Terra архитектурного решения либо одного critical security/data/migration/RCA gate. Implementor, Test-maker, обычный Reviewer и Task Assessor не получают frontier автоматически.

Доступность моделей бери из активного инструмента и запиши фактически выбранные `MODEL`, `REASONING_EFFORT` и fallback basis в assignment. Для `gpt-5.6-sol` разрешены только поддерживаемые уровни `low` и `medium`; `high`, `xhigh`, `max` и `ultra` считаются contract violation для основной задачи и любого spawn. До вызова `spawn_agent` выполни spawn preflight: аргументы вызова обязаны содержать exact `model` и `reasoning_effort`, совпадающие с assignment и этим пределом; отсутствие любого аргумента, наследование родительской модели, превышение Sol-cap или подмена lane запрещают spawn. Не используй `inherit` как model lane или неявный fallback; если ни одна допустимая комбинация недоступна, верни blocker. Не выбирай Astra, если пользователь отдельно не запросил её.

`fork_turns` должен быть явно передан как `none`; `all` запрещён. Положительное N допустимо только с записанным `FORK_JUSTIFICATION`, когда минимальный незаменимый контекст нельзя выразить артефактом. Передавай узкое assignment с role file, domain profile, DecisionSnapshot revisions, scope, acceptance и ссылками на evidence. Не держи более трёх активных субагентов. Независимый reviewer получает собственный компактный контекст и immutable diff.

Явно ограничивай проверки изменённым поведением и repository requirements. После успешных проверок не расширяй их без новых изменений, failures или unresolved risk. Sol escalation допустим только с `BLOCKER_EVIDENCE` и `SOL_ESCALATION_REASON`; сначала отправь Terra-агенту компактную correction delta. Делегируй только роли выбранного маршрута.

Источник рекомендаций GPT-6: https://developers.openai.com/api/docs/guides/latest-model
