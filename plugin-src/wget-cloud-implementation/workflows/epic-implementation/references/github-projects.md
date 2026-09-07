# GitHub Project execution contract

## Snapshot

Зафиксируй Project URL/ID, fields/options IDs, selected item IDs/URLs, parent/sub-issues, status, priority, dependencies, linked PRs и timestamp/revision. Перед mutation проверь, что item не изменён внешне несовместимым образом.

## Status mapping

Используй только точные option names существующего Project, включая их фактическое написание. Семантические переходы:

- Backlog — задача не прошла readiness.
- ready for development — AC/owner/dependencies готовы.
- In Progress — write scope назначен и implementation начат.
- code review — implementation и минимальные checks завершены.
- in testing — reviewer и architecture diff gate approved.
- ready for deploy — QA/integration pass, но delivery ещё требуется.
- Done — согласованный delivery завершён и проверен; для local-only scope допускается только если пользователь явно определил local completion как конечный результат.

Если semantic status отсутствует в schema, не создавай option и не подменяй его приблизительным значением. Оставь item в последнем существующем правдивом status, сохрани достигнутый semantic gate в `EpicRunReport` и запроси отдельное разрешение на изменение schema, если оно действительно необходимо. Не делай переход через несколько состояний без evidence. Rework возвращает в существующий эквивалент In Progress; если его нет, применяется тот же safe fallback. Blocker хранится в issue comment/body/status field только в пределах явного mutation scope; не закрывай issue.

## Ownership

Project Manager предлагает переход, главный агент утверждает sync plan, а GitHub Project Operator применяет его по exact item/status allowlist. Главный агент выполняет независимый read-after-write.

## Idempotency и конфликты

Mutation повторяется по item ID и ожидаемому предыдущему status. При несовпадении перечитай item и replan; не перезаписывай чужое изменение вслепую.

## Final verification

Перечитай все selected items, посчитай статусы, найди missing fields и карточки In Progress без активного work slice. Сверь native hierarchy и linked delivery artifacts.
