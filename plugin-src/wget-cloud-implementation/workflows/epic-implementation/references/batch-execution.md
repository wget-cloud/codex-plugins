> V7: набор обязательных role gates выбирает [TaskAssessment](task-assessment.md); фиксированные pipeline-списки ниже относятся к Full. В Light/Standard plan/floor задаёт Assessor; независимые проверки применяются по маршруту. V2/v3 approvals не переносятся в v4.

# Волны и массовая реализация

## Построение DAG

Dependency edge задаётся contract/schema, data migration, package publication, service availability, test fixture или explicit issue dependency. Priority не создаёт dependency автоматически.

## Ready wave

Item ready, если его product acceptance однозначна, обязательные predecessors доставлены/доступны в текущей рабочей среде, repository/path scope свободен и нужные secrets/authority не требуются прямо сейчас.

## Concurrency conflict graph

Запрещай параллельные write slices, если они затрагивают один repository, один proto/schema/public export, один migration chain, один generated output или один GitOps values/application boundary. Read-only Explorer/Reviewer могут идти параллельно на независимых областях.

Начинай с минимальной волны. Увеличивай concurrency только после успешной первой интеграции и при наличии свободных agent slots. Project size не является основанием запускать все items сразу.

## Checkpoint

Для каждого item фиксируй objective progress: diff, tests, artifact, blocker. Сообщение «работаю» не прогресс. Первый stall → correction/rescope; повторный stall/scope drift → interrupt, inspect partial work, split/restart.

## Failure isolation

Failure одного item блокирует только его descendants и shared boundary. Независимые branches DAG могут продолжать работу, если integration baseline остаётся зелёным.

## Полный inventory между партиями

До первой партии Project Manager phase=scope передаёт `epic_inventory`:

```json
{"revision":"sha256","items":[{"item_id":"BE-11","item_revision":"sha256"}],"external_dependencies":[]}
```

Вычисли revision как SHA-256 UTF-8 `json.dumps({items, external_dependencies}, sort_keys=True, separators=(',', ':'))`, списки отсортированы по item_id. Только IDs и SHA-256, без тел карточек. Весь состав сначала исследуется и планируется; `selected_items` — только текущая партия реализации ≤100. Inventory ограничен 10000 записями в каждом списке; превышение означает явный blocker, не truncation. Внешняя dependency не может одновременно считаться членом эпика.

При смене партии сохраняй inventory. Замена его состава/revision требует `inventory_change_decision` (opaque handle решения пользователя). Храни очищенные evidence artifacts всех завершённых партий; их нельзя заменять успешностью последней партии.

Project Manager phase=reconcile передаёт `epic_reconciliation` с `inventory_revision` и списками `items`/`external_dependencies`, точно совпадающими по IDs/revisions с inventory. Каждая строка: `item_id`, `item_revision`, `disposition`, `evidence_refs` (1–10 opaque handles), `decision_ref` (пусто либо handle решения пользователя).

Для member dispositions: implemented (выполнена в этом run с независимыми gates), already-delivered (фактическая доставка/AC проверены, повторная реализация не нужна), blocked-by-external, deferred, cancelled. Последние два требуют decision_ref; blocked/deferred не закрывают весь run. Cancelled допустим для завершения только после явно согласованного изменения product scope и повторной проверки outcome, а не как доказательство выполнения требования. Для external dependencies: satisfied, blocking, not-required; последнее требует decision_ref.

Already-delivered карточки остаются в inventory, но не требуют фиктивных новых implementation gates: проверь предыдущие артефакты и оставшиеся AC. Если проверка/исправление ещё нужно, включи соответствующий work slice в selected_items с реальным планом и оценкой. Не сбрасывай Stage ради ledger. Перед итоговым report Orchestrator перечитывает ВЕСЬ inventory через MCP и независимо проверяет evidence каждой партии/уже доставленной задачи.

Hook требует gate `epic-inventory`: полный актуальный report без blocked/deferred/blocking. Он проверяет покрытие и revisions, но не может доказать правдивость evidence/решения пользователя. Ошибки/неполнота возвращают blocked и честный промежуточный отчёт; завершение batch не означает завершение эпика.

Если весь эпик уже доставлен/согласованно отменён и новая реализация не нужна, scope marker передаёт `selected_items: []` вместе с полным `epic_inventory`. Это не пустой эпик: нужен полный reconciliation с already-delivered/cancelled и проверкой outcome. При пустой execution партии implemented dispositions не могут обойти implementation gates.

Перед заменой партии hook сохраняет completed_epic_items только для удаляемых из active ledger items с пройденными актуальными per-item gates. Final disposition implemented требует либо такого подтверждения прошлой партии с тем же item_revision, либо presence в текущем selected_items с его обязательными gates. Один report не создаёт доказательство исполнения прошлых партий.
