---
name: wgc-implementation
description: Coordinate architecture-safe planned implementation work across the Wget Cloud frontend, backend microservices, shared front-lib, public sites, and Kubernetes GitOps repositories. Use for feature development, refactors, contracts, cross-repository changes, tests, reviews, QA, infrastructure preparation, rollout, or any planned task that benefits from specialized architect, architecture guardian, test-maker, implementor, reviewer, QA, DevOps, infrastructure reviewer, and deployment agents. For a user-reported defect, regression, failure, crash, or production incident that must be investigated and fixed, use wgc-bugfix instead. Do not use for a simple explanation or read-only question that needs no implementation workflow.
---

# WGC Implementation

## Preflight

До работы проверь `service_tier=default` и `features.fast_mode=false`. Fast/priority/ultrafast → `WGC_FAST_MODE_FORBIDDEN`; неизвестное → `WGC_SERVICE_TIER_UNVERIFIABLE`. Priority-only spawn — blocker. Модель и reasoning effort наследуются из чата, без overrides.

## Intake и выбор команды

1. Прочитай root/затронутые AGENTS.md и обязательные project docs; проверь Git baseline и фактический execution path.
2. Прочитай [TaskAssessment](references/task-assessment.md) и [registry](references/agents/index.md). Назначь отдельного Task Assessor с узким scope.
3. По verdict выбери Light/Standard/Full. Загружай только выбранные [Backend](references/domains/backend.md), [Frontend](references/domains/frontend.md), [Site](references/domains/site.md), [Front-lib](references/domains/front-lib.md), [GitOps](references/domains/gitops.md). Role file — перед конкретным назначением.
4. Перед execution прочитай [test policy](references/test-assessment.md) и [verification](references/verification.md). [Full workflow](references/workflow.md) — только Full. [Hooks](references/hooks.md) — при диагностике; [gates](references/artifacts-and-gates.md) — когда нужен формат артефакта.

## Этот процесс

Один planned WorkItem: новая функция или refactor. Для reported defect выбирай bugfix; для ordered Project pool — epic. Не расширяй задачу до общего аудита.

## Исполнение и готовность

Оркестратор владеет WorkItem и transitions. Каждый агент возвращает только назначенный artifact/verdict с current assessment revision. Domain profile не расширяет write permissions. Сохраняй independence исполнителя, test author и reviewer; Architect не утверждает свой план. Максимум три активных субагента, fork none по умолчанию; [model/context policy](references/model-routing.md).

Сохраняй пользовательские изменения. Root/submodules — отдельные repositories. Commit/push/PR/merge/release/deployment требуют явного разрешения. Kubernetes — через approved GitOps; DevOps не является Infrastructure Reviewer.

Scope expansion или новые риски → новая оценка; устаревшие approvals/checks не засчитываются. Не писать тесты без конкретного regression value и не повторять успешные проверки без основания. Требования repository/CI сохраняются. Готовность требует актуальных route gates, доказанной acceptance и честного delivery status. При blocker сообщи его; не изображай пропущенные роли как approved.

Финал: результат, изменённый scope, проверки/evidence, blockers и Git/delivery status. Для Light и compact bugfix приложи Orchestrator marker из TaskAssessment contract.
