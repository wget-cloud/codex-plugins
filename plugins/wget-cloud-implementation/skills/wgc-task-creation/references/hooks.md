> V7: набор обязательных role gates выбирает [TaskAssessment](task-assessment.md); фиксированные pipeline-списки ниже относятся к Full. В Light/Standard plan/floor задаёт Assessor; независимые проверки применяются по маршруту. V2/v3 approvals не переносятся в v4.

# Lifecycle hooks для создания backlog

## Профиль

Hooks выбирают профиль `task-creation` по явному `$wgc-task-creation` или по сочетанию запроса на создание задач/backlog с указанным YouTrack. Явное имя другого WGC skill имеет приоритет над inference. В state сохраняются только privacy-safe route flags, summaries и структурированные verdicts; исходный prompt, Project URL, bodies задач, tool output и credentials не сохраняются.

## Что проверяется

- `SubagentStop` принимает только role/verdict, объявленные в локальном agent registry.
- `Stop` требует актуальные gates Product Manager, Project Manager, Implementation Auditor, Architect и Backlog Reviewer.
- Если пользователь разрешил внешнюю mutation, дополнительно требуется `youtrack-operator:published` для текущей revision.
- Отсутствие локального diff не завершает workflow автоматически: результат этого skill находится в YouTrack.
- После первой блокировки `Stop` не создаёт бесконечный continuation loop; оставшиеся gaps должны быть честно отражены пользователю.

Hook не доказывает содержимое YouTrack и не заменяет read-after-write verification. Оркестратор обязан самостоятельно перечитать созданные issues/items. YouTrack Operator получает только exact allowlist из утверждённого `MutationPlan`; Project schema, repositories, labels вне согласованного scope и любые другие внешние объекты не изменяются.

Hooks task-creation не принимают окончательное test disposition и не создают Project fields. Provisional `test_policy` проверяют Product Manager, Architect и Backlog Reviewer как часть managed task body/AC; Test-maker implementation-профиля позднее выпускает окончательный TestAssessment.

## YouTrack / SP contracts v8

Новые роли доступны во всех профилях: Effort Estimator (`estimated | needs_input | needs_research`), YouTrack Operator (`published | synced | partially_applied | no_changes | authorization_required | blocked`); phase пустой. В task-creation актуальный estimated закрывает обязательный effort-estimate gate во всех режимах. published/no_changes закрывают project-publish, synced/no_changes — project-sync в delivery с разрешённой YouTrack mutation. Частичный результат не закрывает gate. input_revision/assessment_revision/item identity проверяются как у downstream roles. Hook state не хранит SP rationale, токены или тела карточек. Семантическую готовность, user decisions и реальные MCP записи независимо проверяет Orchestrator: marker сам по себе их не доказывает.

Stage эпика: Project Manager phase=lifecycle и verdict stage_ready/awaiting_user/stage_blocked, exact epic_stage_plan по [контракту](epic-lifecycle.md). Lifecycle verdicts не закрывают project/scope/reconcile gates. Hook проверяет разрешённые переходы, текущие approvals, полный состав и task statuses; успешный Operator marker с plan требует matching current PM plan. Перед записью реальные данные проверяет Orchestrator. Во всех четырёх профилях read-only пауза awaiting_user не требует фиктивной завершённой декомпозиции и не помечает workflow complete.

Подтверждённый переход раннего этапа может завершить текущий ход, сохраняя workflow active и не объявляя backlog complete. Возвраты на Исследование/Груминг допустимы при неполном inventory с подтверждённой причиной; полнота обязательна для продвижения вперёд.
