---
name: wgc-implementation
description: Coordinate architecture-safe planned implementation work across the Wget Cloud frontend, backend microservices, shared front-lib, public sites, and Kubernetes GitOps repositories. Use when asked to implement a YouTrack issue ID or URL, or for feature development, refactors, contracts, cross-repository changes, tests, reviews, QA, infrastructure preparation, rollout, or any planned task that benefits from specialized architect, architecture guardian, test-maker, implementor, reviewer, QA, DevOps, infrastructure reviewer, and deployment agents. For a user-reported defect, regression, failure, crash, or production incident that must be investigated and fixed, use wgc-bugfix instead. Do not use for a simple explanation or read-only question that needs no implementation workflow.
---

# WGC Implementation

## Preflight

Spawned-роли получают минимальную достаточную GPT-5.6 lane: Luna для механических операций, Terra для разработки и review. Sol допустим только по подтверждённому blocker/critical escalation и не назначается всей команде из-за размера задачи.

## YouTrack и продуктовая готовность

Для карточок работай только через [YouTrack MCP](references/youtrack.md). Прочитай [product discovery](references/product-discovery.md), исследуй код и задачи, предложи альтернативы, задай пользователю material questions. До зависимой реализации получи явный approval на выявленные противоречия/проблемы; молчание не approval. Оценки — [story points](references/story-points.md), отдельный Effort Estimator не подменяет Task Assessor. Для delivery соблюдай [ветки dev/task/epic и squash](references/youtrack-git.md).

Для эпика или его дочерней задачи обязателен [жизненный цикл эпика](references/epic-lifecycle.md): Project Manager управляет этапами и approvals, Operator синхронизирует Stage через MCP. Research не запускает разработку эпика.

## Intake и выбор команды

1. Прочитай root/затронутые AGENTS.md и обязательные project docs; проверь Git baseline и фактический execution path.
2. Прочитай [coordination contract](references/coordination-efficiency.md), [TaskAssessment](references/task-assessment.md) и [registry](references/agents/index.md). Один компактный Task Assessor фиксирует route/RiskMatrix/test ownership; переиспользуй его между slices и не запускай повторно без route-affecting изменения.
3. По verdict выбери Light/Standard/Full. Загружай только выбранные [Backend](references/domains/backend.md), [Frontend](references/domains/frontend.md), [Site](references/domains/site.md), [Front-lib](references/domains/front-lib.md), [GitOps](references/domains/gitops.md). Role file — перед конкретным назначением.
4. Перед execution прочитай [test policy](references/test-assessment.md) и [verification](references/verification.md). [Full workflow](references/workflow.md) — только Full. [Hooks](references/hooks.md) — при диагностике; [gates](references/artifacts-and-gates.md) — когда нужен формат артефакта.

## Этот процесс

Один planned WorkItem: новая функция или refactor. Для reported defect выбирай bugfix; для ordered YouTrack pool — epic. Не расширяй задачу до общего аудита.

## Исполнение и готовность

Оркестратор владеет WorkItem, DecisionSnapshot, ResumeCapsule, EfficiencyBudget и transitions. Стандартный workflow — компактный Task Assessor и один Implementor на Terra, который пишет связный slice и минимальные tests. Третий assignment — один Reviewer или specialist только для нетривиального риска. Максимум три assignments на slice и один correction batch существующему Implementor; полный pipeline после finding не перезапускается. Каждый агент возвращает только назначенный artifact/verdict с current assessment revision. Domain profile не расширяет write permissions. [Model/context policy](references/model-routing.md).

Сохраняй пользовательские изменения. Root/submodules — отдельные repositories. Commit/push/PR/merge/release/deployment требуют явного разрешения. Kubernetes — через approved GitOps; DevOps не является Infrastructure Reviewer.

Scope expansion или новые риски → новая оценка; устаревшие approvals/checks не засчитываются. Не писать тесты без конкретного regression value и не повторять успешные проверки без основания. Требования repository/CI сохраняются. Готовность требует актуальных route gates, доказанной acceptance и честного delivery status. При blocker сообщи его; не изображай пропущенные роли как approved.

Финал: результат, изменённый scope, проверки/evidence, blockers и Git/delivery status. Для Light и compact bugfix приложи Orchestrator marker из TaskAssessment contract.
