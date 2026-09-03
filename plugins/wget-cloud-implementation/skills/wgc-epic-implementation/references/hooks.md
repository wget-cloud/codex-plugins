# Lifecycle hooks для epic implementation

## Профиль

Hooks выбирают профиль `epic-implementation` по явному `$wgc-epic-implementation` или по запросу реализовать epic/task pool из GitHub Project. Явное имя другого WGC skill имеет приоритет над inference. В state сохраняются только privacy-safe route flags, summaries и структурированные verdicts; исходный prompt, Project URL, issue bodies, tool output и credentials не сохраняются.

## Phase-aware gates

- Product Manager обязан вернуть `accepted` отдельно в phase `scope` и `outcome`; ранняя readiness-проверка не закрывает итоговую бизнес-приёмку.
- Project Manager обязан вернуть `planned` в phase `scope` и `progress_updated` в phase `reconcile`.
- Architecture Guardian обязан независимо одобрить phase `plan` item-facing marker с exact frozen `item_id`/`item_revision` и текущим per-item `plan_revision`; global/missing/stale marker запрещён. После правок нужен `phase=diff` для текущей workspace revision.
- Project Manager `phase=scope` передаёт frozen список максимум из 100 `selected_items[{item_id,item_revision=sha256,plan_revision,acceptance_revision,minimum_test_criticality}]`; недостающие поля разрешено добавить только matching per-item Architect/Product markers до TestAssessment.
- `Stop` требует для каждого frozen item отдельные TestAssessment, implementation, review, architecture diff, QA и product outcome gates, а также global product/project/architecture/reconciliation. GitHub Project sync обязателен только когда mutation разрешена.
- Для k8s/GitOps добавляются DevOps и Infrastructure Reviewer; deployment authority остаётся отдельным human approval.
- Exact assessed production write инвалидирует downstream gates только owning item. Неатрибутируемая docs/YAML/GitOps или иная reviewed правка консервативно сбрасывает downstream gates всех items, чтобы sibling evidence не переносился; исторический evidence при этом не становится текущим gate.
- Отсутствие локального diff не завершает workflow автоматически: Project может содержать незакрытый selected scope.

State v3 валидирует per-item flat markers и TestAssessment из [test-assessment.md](test-assessment.md). Result ledger допускает до 1000 записей, поэтому 100 items сохраняют все required lifecycle gates; retry того же role/phase/item/input revision заменяет прежнюю запись, а overflow блокируется без eviction. V2 migration сохраняет только совместимое privacy-safe non-test verification evidence, сбрасывая legacy `test`/`coverage` evidence и test/review/QA gates; malformed state блокирует completion. Hook не наблюдает фактическое состояние GitHub Project и не может переводить item. Project Operator применяет точный StatusSyncPlan, после чего оркестратор делает read-after-write verification.
