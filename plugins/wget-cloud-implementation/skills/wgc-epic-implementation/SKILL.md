---
name: wgc-epic-implementation
description: Implement a Wget Cloud epic or ordered pool of YouTrack tasks through MCP with product, project, architecture, test, implementation, review, QA, integration, and optional GitOps gates. Use when the user asks to implement an epic, roadmap slice, batch, priority class, or multiple related YouTrack issues and expects progress to be tracked in YouTrack, including full per-task research and implementation plans before execution. Do not use to create or audit a backlog without implementation; use wgc-task-creation. For one standalone planned task without epic-level coordination, use wgc-implementation; for a reported defect requiring RCA, use wgc-bugfix.
---

# WGC Epic Implementation

## Preflight

Spawned-роли получают минимальную достаточную GPT-5.6 lane: Luna для механических операций, Terra для разработки и review. Sol допустим только по подтверждённому blocker/critical escalation.

## YouTrack и продуктовая готовность

Для карточок работай только через [YouTrack MCP](references/youtrack.md). Прочитай [product discovery](references/product-discovery.md), исследуй код и задачи, предложи альтернативы, задай пользователю material questions. До зависимой реализации получи явный approval на выявленные противоречия/проблемы; молчание не approval. Оценки — [story points](references/story-points.md), отдельный Effort Estimator не подменяет Task Assessor. Для delivery соблюдай [ветки dev/task/epic и squash](references/youtrack-git.md).

Для эпика или его дочерней задачи обязателен [жизненный цикл эпика](references/epic-lifecycle.md): Project Manager управляет этапами и approvals, Operator синхронизирует Stage через MCP. Research не запускает разработку эпика.

## Intake и выбор команды

1. Прочитай root/затронутые AGENTS.md и обязательные project docs; проверь Git baseline и фактический execution path.
2. Прочитай [coordination contract](references/coordination-efficiency.md), [TaskAssessment](references/task-assessment.md) и [registry](references/agents/index.md). Переиспользуй assessment одного frozen item до route-affecting изменения.
3. По verdict выбери Light/Standard/Full. Загружай только выбранные [Backend](references/domains/backend.md), [Frontend](references/domains/frontend.md), [Site](references/domains/site.md), [Front-lib](references/domains/front-lib.md), [GitOps](references/domains/gitops.md). Role file — перед конкретным назначением.
4. Перед execution прочитай [test policy](references/test-assessment.md) и [verification](references/verification.md). [Full workflow](references/workflow.md) — только Full. [Hooks](references/hooks.md) — при диагностике; [gates](references/artifacts-and-gates.md) — когда нужен формат артефакта.

## Этот процесс

Project Manager собирает весь EpicInventory без усечения: все descendants, связанные работы и внешние dependencies. Исследуй все задачи/репозитории и представь отдельный план каждой задачи до реализации; реши вопросы и противоречия. Затем заморозь execution batch максимум 100 selected items; это не предел состава эпика. Отдельный Task Assessor для каждого item. Выполняй ready items по waves; Product outcome и Project reconciliation сохраняются. Done отражает реальный delivery. Unknown defect переключает item в RCA workflow.

## Исполнение и готовность

Оркестратор владеет EpicRun, DecisionSnapshot, ResumeCapsule, EfficiencyBudget и transitions. Один item/slice имеет одного Implementor на Terra; Reviewer либо один specialist добавляется только по нетривиальному item risk. Максимум три assignments на item slice и один correction batch существующему Implementor; замечание не перезапускает полный pipeline. Каждый агент возвращает только назначенный artifact/verdict с current assessment revision. Domain profile не расширяет write permissions. [Model/context policy](references/model-routing.md).

Сохраняй пользовательские изменения. Root/submodules — отдельные repositories. Commit/push/PR/merge/release/deployment требуют явного разрешения. Kubernetes — через approved GitOps; DevOps не является Infrastructure Reviewer.

Scope expansion или новые риски → новая оценка; устаревшие approvals/checks не засчитываются. Не писать тесты без конкретного regression value и не повторять успешные проверки без основания. Требования repository/CI сохраняются. Готовность требует актуальных route gates, доказанной acceptance и честного delivery status. При blocker сообщи его; не изображай пропущенные роли как approved.

Финал: результат, изменённый scope, проверки/evidence, blockers и Git/delivery status. Для Light и compact bugfix приложи Orchestrator marker из TaskAssessment contract.
