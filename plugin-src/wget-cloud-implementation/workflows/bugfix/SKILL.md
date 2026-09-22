---
name: wgc-bugfix
description: Coordinate evidence-driven diagnosis and repair of Wget Cloud defects across frontend, backend microservices, shared front-lib, public sites, and Kubernetes GitOps. Use for YouTrack Bug issues and when a user reports a bug, regression, crash, exception, failed UI/API/realtime/PWA flow, authorization or tenant-isolation defect, production incident, or behavior that no longer matches expectations and asks to fix it. The skill gathers scoped logs and runtime evidence when available, reproduces before patching, establishes a supported root cause, protects regression tests from implementor edits, performs independent review and architecture checks, runs targeted QA including browser/API/security specialists when relevant, and uses gated GitOps rollout only with explicit human approval. Do not use for explanation-only diagnostics with no requested fix, planned feature development, or blind deployment.
---

# WGC Bugfix

## Preflight

Spawned-роли получают минимальную достаточную GPT-6 lane: Luna для economy/focused, Sol/low для диагностики, исправления и technical review. Sol/medium штатно разрешён только Architect и однократно specialist по critical escalation.

## YouTrack и продуктовая готовность

Для карточок работай только через [YouTrack MCP](references/youtrack.md). Прочитай [product discovery](references/product-discovery.md), исследуй код и задачи, предложи альтернативы, задай пользователю material questions. До зависимой реализации получи явный approval на выявленные противоречия/проблемы; молчание не approval. Оценки — [story points](references/story-points.md), отдельный Effort Estimator не подменяет Task Assessor. Для delivery соблюдай [ветки dev/task/epic и squash](references/youtrack-git.md).

Для эпика или его дочерней задачи обязателен [жизненный цикл эпика](references/epic-lifecycle.md): Project Manager управляет этапами и approvals, Operator синхронизирует Stage через MCP. Research не запускает разработку эпика.

## Intake и выбор команды

1. Прочитай root/затронутые AGENTS.md и обязательные project docs; проверь Git baseline и фактический execution path.
2. Прочитай [coordination contract](references/coordination-efficiency.md), [TaskAssessment](references/task-assessment.md) и [registry](references/agents/index.md). Один компактный Task Assessor фиксирует route/RiskMatrix/test ownership; переиспользуй его между fix slices и не запускай повторно без route-affecting изменения.
3. По verdict выбери Light/Standard/Full. Загружай только выбранные [Backend](references/domains/backend.md), [Frontend](references/domains/frontend.md), [Site](references/domains/site.md), [Front-lib](references/domains/front-lib.md), [GitOps](references/domains/gitops.md). Role file — перед конкретным назначением.
4. Перед execution прочитай [test policy](references/test-assessment.md) и [verification](references/verification.md). [Full workflow](references/workflow.md) — только Full. [Hooks](references/hooks.md) — при диагностике; [gates](references/artifacts-and-gates.md) — когда нужен формат артефакта.

## Этот процесс

До production fix зафиксируй observed/expected и минимальное evidence причины. Light/Standard: Orchestrator проверяет baseline/причину/результат, а Implementor добавляет небольшой regression test вместе с fix, если он полезен. Full не запускает каталог ролей автоматически: отдельные investigator/reproducer/RCA reviewer нужны только когда причина действительно не подтверждается локальным evidence. Runtime inspection read-only и scoped.

## Исполнение и готовность

Оркестратор владеет WorkItem, DecisionSnapshot, ResumeCapsule, EfficiencyBudget и transitions. Стандартный workflow — компактный Task Assessor и один Implementor на Sol/low; третий assignment — Reviewer либо specialist только по конкретному риску. Отдельный Test-maker нужен лишь при `test_ownership=protected_test_maker`. Максимум три assignments на slice, один correction batch существующему Implementor и никакого полного restart pipeline. Каждый агент возвращает только назначенный artifact/verdict с current assessment revision. Domain profile не расширяет write permissions. [Model/context policy](references/model-routing.md).

Сохраняй пользовательские изменения. Root/submodules — отдельные repositories. Commit/push/PR/merge/release/deployment требуют явного разрешения. Kubernetes — через approved GitOps; DevOps не является Infrastructure Reviewer.

Scope expansion или новые риски → новая оценка; устаревшие approvals/checks не засчитываются. Не писать тесты без конкретного regression value и не повторять успешные проверки без основания. Требования repository/CI сохраняются. Готовность требует актуальных route gates, доказанной acceptance и честного delivery status. При blocker сообщи его; не изображай пропущенные роли как approved.

Финал: результат, изменённый scope, проверки/evidence, blockers и Git/delivery status. Для Light и compact bugfix приложи Orchestrator marker из TaskAssessment contract.
