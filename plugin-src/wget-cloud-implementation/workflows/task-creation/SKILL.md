---
name: wgc-task-creation
description: Create or refine product-quality Wget Cloud tasks, epics, bug/refactor follow-ups, and ordered backlogs in YouTrack through MCP with product interviews, project research, alternatives, and story-point estimation, from a feature request, audit, gap analysis, or business workflow. Use when the user asks to analyze implementation completeness, decompose work, create issues, populate a project backlog, prioritize dependencies, or turn requirements into executable tasks. Do not use to implement the created tasks; use wgc-epic-implementation for an epic or pool and wgc-implementation for one planned engineering task.
---

# WGC Task Creation

## Preflight

До работы проверь `service_tier=default` и `features.fast_mode=false`. Fast/priority/ultrafast → `WGC_FAST_MODE_FORBIDDEN`; неизвестное → `WGC_SERVICE_TIER_UNVERIFIABLE`. Priority-only spawn — blocker. Модель и reasoning effort наследуются из чата, без overrides.

## YouTrack и продуктовая готовность

Для карточок работай только через [YouTrack MCP](references/youtrack.md). Прочитай [product discovery](references/product-discovery.md), исследуй код и задачи, предложи альтернативы, задай пользователю material questions. До зависимой реализации получи явный approval на выявленные противоречия/проблемы; молчание не approval. Оценки — [story points](references/story-points.md), отдельный Effort Estimator не подменяет Task Assessor. Для delivery соблюдай [ветки dev/task/epic и squash](references/youtrack-git.md).

## Intake и выбор команды

1. Прочитай root/затронутые AGENTS.md и обязательные project docs; проверь Git baseline и фактический execution path.
2. Прочитай [TaskAssessment](references/task-assessment.md) и [registry](references/agents/index.md). Назначь отдельного Task Assessor с узким scope.
3. По verdict выбери Light/Standard/Full. Загружай только выбранные [Backend](references/domains/backend.md), [Frontend](references/domains/frontend.md), [Site](references/domains/site.md), [Front-lib](references/domains/front-lib.md), [GitOps](references/domains/gitops.md). Role file — перед конкретным назначением.
4. Перед execution прочитай [test policy](references/test-assessment.md) и [verification](references/verification.md). [Full workflow](references/workflow.md) — только Full. [Hooks](references/hooks.md) — при диагностике; [gates](references/artifacts-and-gates.md) — когда нужен формат артефакта.

## Этот процесс

Не реализуй application code. Для создания задачи/эпика всегда назначь Product Manager, Implementation Auditor, Project Manager, отдельного Effort Estimator и независимого Backlog Reviewer; Architect — для декомпозиции/технических вариантов и Full. Проведи раунды интервью до/после исследования. Найди project keys и дубли через MCP. Для эпика нужна полная декомпозиция и проработка каждой задачи. Публикуй только после решений пользователя и review по exact MutationPlan; запрос «создай» уже даёт authority в своём scope. Read-after-write обязателен. Test policy остаётся provisional.

## Исполнение и готовность

Оркестратор владеет WorkItem и transitions. Каждый агент возвращает только назначенный artifact/verdict с current assessment revision. Domain profile не расширяет write permissions. Сохраняй independence исполнителя, test author и reviewer; Architect не утверждает свой план. Максимум три активных субагента, fork none по умолчанию; [model/context policy](references/model-routing.md).

Сохраняй пользовательские изменения. Root/submodules — отдельные repositories. Commit/push/PR/merge/release/deployment требуют явного разрешения. Kubernetes — через approved GitOps; DevOps не является Infrastructure Reviewer.

Scope expansion или новые риски → новая оценка; устаревшие approvals/checks не засчитываются. Не писать тесты без конкретного regression value и не повторять успешные проверки без основания. Требования repository/CI сохраняются. Готовность требует актуальных route gates, доказанной acceptance и честного delivery status. При blocker сообщи его; не изображай пропущенные роли как approved.

Финал: результат, изменённый scope, проверки/evidence, blockers и Git/delivery status. Для Light и compact bugfix приложи Orchestrator marker из TaskAssessment contract.
