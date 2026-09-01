# Lifecycle hooks для epic implementation

## Профиль

Hooks выбирают профиль `epic-implementation` по явному `$wgc-epic-implementation` или по запросу реализовать epic/task pool из GitHub Project. Явное имя другого WGC skill имеет приоритет над inference. В state сохраняются только privacy-safe route flags, summaries и структурированные verdicts; исходный prompt, Project URL, issue bodies, tool output и credentials не сохраняются.

## Phase-aware gates

- Product Manager обязан вернуть `accepted` отдельно в phase `scope` и `outcome`; ранняя readiness-проверка не закрывает итоговую бизнес-приёмку.
- Project Manager обязан вернуть `planned` в phase `scope` и `progress_updated` в phase `reconcile`.
- Architecture Guardian обязан независимо одобрить phase `plan`, а после правок — phase `diff` для текущей workspace revision.
- `Stop` требует product scope/outcome, project scope, architecture plan, protected test baseline, implementation, review, architecture diff, QA и project reconciliation. GitHub Project sync обязателен только когда mutation разрешена; явный opt-out пользователя имеет приоритет.
- Для k8s/GitOps добавляются DevOps и Infrastructure Reviewer; deployment authority остаётся отдельным human approval.
- Новая локальная правка инвалидирует diff-facing approvals и reconciliation, но не стирает исторический evidence.
- Отсутствие локального diff не завершает workflow автоматически: Project может содержать незакрытый selected scope.

Hook не наблюдает фактическое состояние GitHub Project и не может сам переводить item. Его ledger подтверждает наличие aggregate gates, но не считает selected item IDs; каждый role artifact и финальный Project Manager reconciliation обязаны содержать полный per-item ledger. GitHub Project Operator применяет только точный `StatusSyncPlan`, после чего оркестратор выполняет read-after-write verification. Статус `Done` нельзя доказать сообщением агента: он должен соответствовать фактическому delivery outcome выбранной задачи.
