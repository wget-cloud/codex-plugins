> V7: набор обязательных role gates выбирает [TaskAssessment](task-assessment.md); фиксированные pipeline-списки ниже относятся к Full. В Light/Standard plan/floor задаёт Assessor; независимые проверки применяются по маршруту. V2/v3 approvals не переносятся в v4.

# Lifecycle hooks для epic implementation

## Профиль

Hooks выбирают профиль `epic-implementation` по явному `$wgc-epic-implementation` или по запросу реализовать epic/task pool из YouTrack. Явное имя другого WGC skill имеет приоритет над inference. В state сохраняются только privacy-safe route flags, summaries и структурированные verdicts; исходный prompt, Project URL, issue bodies, tool output и credentials не сохраняются.

## Phase-aware gates

- Product Manager обязан вернуть `accepted` отдельно в phase `scope` и `outcome`; ранняя readiness-проверка не закрывает итоговую бизнес-приёмку.
- Project Manager обязан вернуть `planned` в phase `scope` и `progress_updated` в phase `reconcile`.
- Architecture Guardian обязан независимо одобрить phase `plan` item-facing marker с exact frozen `item_id`/`item_revision` и текущим per-item `plan_revision`; global/missing/stale marker запрещён. После правок нужен `phase=diff` для текущей workspace revision.
- Project Manager `phase=scope` передаёт frozen список максимум из 100 `selected_items[{item_id,item_revision=sha256,plan_revision,acceptance_revision,minimum_test_criticality}]`; недостающие поля разрешено добавить только matching per-item Architect/Product markers до TestAssessment.
- `Stop` требует для каждого frozen item отдельные TestAssessment, implementation, review, architecture diff, QA и product outcome gates, а также global product/project/architecture/reconciliation. YouTrack sync обязателен только когда mutation разрешена.
- Для k8s/GitOps добавляются DevOps и Infrastructure Reviewer; deployment authority остаётся отдельным human approval.
- Exact assessed production write инвалидирует downstream gates только owning item. Неатрибутируемая docs/YAML/GitOps или иная reviewed правка консервативно сбрасывает downstream gates всех items, чтобы sibling evidence не переносился; исторический evidence при этом не становится текущим gate.
- Отсутствие локального diff не завершает workflow автоматически: Project может содержать незакрытый selected scope.

State v4 валидирует per-item flat markers и TestAssessment из [test-assessment.md](test-assessment.md). Result ledger допускает до 1000 записей, поэтому 100 items сохраняют все required lifecycle gates; retry того же role/phase/item/input revision заменяет прежнюю запись, а overflow блокируется без eviction. V2 migration сохраняет только совместимое privacy-safe non-test verification evidence, сбрасывая legacy `test`/`coverage` evidence и test/review/QA gates; malformed state блокирует completion. Hook не наблюдает фактическое состояние YouTrack и не может переводить item. Project Operator применяет точный StatusSyncPlan, после чего оркестратор делает read-after-write verification.

## YouTrack / SP contracts v8

Новые роли доступны во всех профилях: Effort Estimator (`estimated | needs_input | needs_research`), YouTrack Operator (`published | synced | partially_applied | no_changes | authorization_required | blocked`); phase пустой. В task-creation актуальный estimated закрывает обязательный effort-estimate gate во всех режимах. published/no_changes закрывают project-publish, synced/no_changes — project-sync в delivery с разрешённой YouTrack mutation. Частичный результат не закрывает gate. input_revision/assessment_revision/item identity проверяются как у downstream roles. Hook state не хранит SP rationale, токены или тела карточек. Семантическую готовность, user decisions и реальные MCP записи независимо проверяет Orchestrator: marker сам по себе их не доказывает.

Project Manager scope также передаёт полный `epic_inventory`, а reconcile — `epic_reconciliation` по [batch contract](batch-execution.md). Hook проверяет bounded IDs/revisions/dispositions, сохраняет inventory между партиями и требует итоговый gate epic-inventory. Замена inventory требует inventory_change_decision; raw artifacts не допускаются.

`inventory_change_decision` и `decision_ref` — утверждения Orchestrator со ссылкой на фактическое решение пользователя, а не криптографическое доказательство approval. Hook проверяет их формат, но не происхождение. Orchestrator обязан сверить решение с историей текущей задачи и scope до выдачи marker; придумывать ссылку или трактовать таймаут как согласие запрещено.

Архив завершённых задач хранит item revision, workspace evidence revision и bounded assessed paths. Последующие изменения общих контрактов/config, изменения без надёжного владельца или пересечение с архивным scope сбрасывают соответствующие свидетельства. До финала такие задачи возвращаются в выбранную партию и повторно проходят затронутые gates.

Stage эпика: Project Manager phase=lifecycle и verdict stage_ready/awaiting_user/stage_blocked, exact epic_stage_plan по [контракту](epic-lifecycle.md). Lifecycle verdicts не закрывают project/scope/reconcile gates. Hook проверяет разрешённые переходы, текущие approvals, полный состав и task statuses; успешный Operator marker с plan требует matching current PM plan. Перед записью реальные данные проверяет Orchestrator. Во всех четырёх профилях read-only пауза awaiting_user не требует фиктивной завершённой декомпозиции и не помечает workflow complete.

Подтверждённый переход раннего этапа может завершить текущий ход, сохраняя workflow active и не объявляя backlog complete. Возвраты на Исследование/Груминг допустимы при неполном inventory с подтверждённой причиной; полнота обязательна для продвижения вперёд.
