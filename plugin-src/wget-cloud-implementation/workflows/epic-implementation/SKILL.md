---
name: wgc-epic-implementation
description: Implement a Wget Cloud epic or ordered pool of GitHub Project tasks through product, project, architecture, test, implementation, review, QA, integration, and optional GitOps gates. Use when the user asks to implement an epic, roadmap slice, batch, priority class, or multiple related Project items and expects progress to be tracked in GitHub Project. Do not use to create or audit a backlog without implementation; use wgc-task-creation. For one standalone planned task without Project-level coordination, use wgc-implementation; for a reported defect requiring RCA, use wgc-bugfix.
---

# WGC Epic Implementation

## Preflight

До работы проверь `service_tier=default` и `features.fast_mode=false`. Fast/priority/ultrafast → `WGC_FAST_MODE_FORBIDDEN`; неизвестное → `WGC_SERVICE_TIER_UNVERIFIABLE`. Priority-only spawn — blocker. Модель и reasoning effort наследуются из чата, без overrides.

## Intake и выбор команды

1. Прочитай root/затронутые AGENTS.md и обязательные project docs; проверь Git baseline и фактический execution path.
2. Прочитай [TaskAssessment](references/task-assessment.md) и [registry](references/agents/index.md). Назначь отдельного Task Assessor с узким scope.
3. По verdict выбери Light/Standard/Full. Загружай только выбранные [Backend](references/domains/backend.md), [Frontend](references/domains/frontend.md), [Site](references/domains/site.md), [Front-lib](references/domains/front-lib.md), [GitOps](references/domains/gitops.md). Role file — перед конкретным назначением.
4. Перед execution прочитай [test policy](references/test-assessment.md) и [verification](references/verification.md). [Full workflow](references/workflow.md) — только Full. [Hooks](references/hooks.md) — при диагностике; [gates](references/artifacts-and-gates.md) — когда нужен формат артефакта.

## Этот процесс

Заморозь максимум 100 selected items и зависимости через Project Manager. Затем отдельный Task Assessor для каждого item. Выполняй ready items по waves; Product outcome и Project reconciliation сохраняются. Done отражает реальный delivery. Unknown defect переключает item в RCA workflow.

## Исполнение и готовность

Оркестратор владеет WorkItem и transitions. Каждый агент возвращает только назначенный artifact/verdict с current assessment revision. Domain profile не расширяет write permissions. Сохраняй independence исполнителя, test author и reviewer; Architect не утверждает свой план. Максимум три активных субагента, fork none по умолчанию; [model/context policy](references/model-routing.md).

Сохраняй пользовательские изменения. Root/submodules — отдельные repositories. Commit/push/PR/merge/release/deployment требуют явного разрешения. Kubernetes — через approved GitOps; DevOps не является Infrastructure Reviewer.

Scope expansion или новые риски → новая оценка; устаревшие approvals/checks не засчитываются. Не писать тесты без конкретного regression value и не повторять успешные проверки без основания. Требования repository/CI сохраняются. Готовность требует актуальных route gates, доказанной acceptance и честного delivery status. При blocker сообщи его; не изображай пропущенные роли как approved.

Финал: результат, изменённый scope, проверки/evidence, blockers и Git/delivery status. Для Light и compact bugfix приложи Orchestrator marker из TaskAssessment contract.
