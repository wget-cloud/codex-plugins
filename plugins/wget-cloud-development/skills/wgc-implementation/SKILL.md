---
name: wgc-implementation
description: Coordinate tracker-independent, architecture-safe planned implementation work in the Wget Cloud backend-services Go workspace. Use for independent microservices, shared platform primitives, Protobuf contracts, repository CI, container images, migrations from the legacy TypeScript backend, or GitOps preparation that benefits from specialized architecture, test, implementation, review, QA, infrastructure, and deployment roles. For a reported defect, regression, crash, or incident that must be investigated and fixed, use wgc-bugfix instead. Do not use for unrelated repositories, a simple explanation, or a read-only question.
---

# WGC Implementation

## MVP flag

`MVP_SKIP_TESTS: true` — переключатель этого автономного skill. При `true` не создавай, не изменяй и не запускай тесты, не вычисляй и не проверяй покрытие, не назначай Test-maker. Передавай значение флага каждому агенту; в `TestAssessment` фиксируй `test_disposition: none`, `coverage_mode: skipped_by_mvp_flag`, альтернативные проверки и остаточный риск даже для critical scope. Это правило имеет приоритет над test-writing, test-running и coverage указаниями в references этого skill. При `false` применяется обычная [test policy](references/test-assessment.md). Требования CI и repository не изменяются: если они всё ещё требуют тесты или покрытие, сообщи об этом как о непроверенном gate и не заявляй release readiness.

## Граница внешних систем

Работай только с запросом пользователя, repository context и доступными runtime evidence. Skill не читает и не изменяет task trackers, backlog или внешние карточки. Если для реализации не хватает acceptance criteria либо нужно выбрать продуктовую семантику, исследуй безопасный локальный контекст и запроси конкретное решение пользователя до зависимой правки.

## Intake и выбор команды

1. Прочитай root/затронутые AGENTS.md и обязательные project docs; проверь Git baseline и фактический execution path.
2. Прочитай [coordination contract](references/coordination-efficiency.md), [TaskAssessment](references/task-assessment.md) и [registry](references/agents/index.md). Создай DecisionSnapshot. Переиспользуй актуальный assessment; для очевидного Light/Standard route выпусти его как Orchestrator, а отдельного Task Assessor назначай только при неоднозначном, Full, cross-module/cross-repo или расширившемся scope.
3. По verdict выбери Light/Standard/Full. Всегда прочитай [repository profile](references/domains/repository.md), затем загружай только выбранные [Service](references/domains/service.md), [Contracts](references/domains/contracts.md), [Platform](references/domains/platform.md), [CI](references/domains/ci.md) и [GitOps](references/domains/gitops.md). Role file — перед конкретным назначением.
4. Перед execution прочитай [test policy](references/test-assessment.md) и [verification](references/verification.md). [Full workflow](references/workflow.md) — только Full; [gates](references/artifacts-and-gates.md) — когда нужен формат артефакта.

## Этот процесс

Один planned WorkItem: новая функция или refactor. Для reported defect выбирай bugfix. Не расширяй задачу до общего аудита или управления backlog.

Для нового микросервиса сначала один раз собери inventory подключённого legacy-поведения, зависимостей и границ нового сервиса. Сведи существенные продуктовые решения в один пакет вопросов, затем покажи единый план сервиса с вариантами объёма и получи разрешение на выбранную реализацию. Это разрешение действует для всех внутренних траншей согласованного объёма; новый вопрос или approval нужен только при новом продуктовом выборе, изменении границ/acceptance либо отдельном Git/delivery действии. Внутренний транш остаётся связным проверяемым поведением, а не отдельным слоем схемы, криптографии или handler-кода.

## Исполнение и готовность

Оркестратор владеет WorkItem, DecisionSnapshot, ResumeCapsule и EfficiencyBudget, но не пишет production code/tests. Стандартный workflow — один Implementor на Sol/low, который делает связный tranche; при `MVP_SKIP_TESTS: false` он также пишет 2–5 минимальных tests. Orchestrator выполняет inline RiskMatrix и targeted verification; один Reviewer либо specialist добавляется только для нетривиального риска. Максимум три assignments на tranche, 10 coordination decisions и один correction batch существующему Implementor; полный pipeline после finding не перезапускается. Sol требует подтверждённого blocker escalation. Каждый агент возвращает только назначенный artifact/verdict с current assessment revision.

Сохраняй пользовательские изменения. Каждый `services/<name>`, `platform` и `contracts` — отдельный Go module внутри одного Git repository; module boundary не является отдельной Git history. Commit/push/PR/merge/release/deployment требуют явного разрешения. Kubernetes — через approved GitOps; DevOps не является Infrastructure Reviewer.

Scope expansion или новые риски → новая оценка; устаревшие approvals/checks не засчитываются. При `MVP_SKIP_TESTS: false` не писать тесты без конкретного regression value и не повторять успешные проверки без основания. Требования repository/CI сохраняются. Готовность требует актуальных route gates, доказанной acceptance и честного delivery status. При blocker сообщи его; не изображай пропущенные роли как approved.

Финал: результат, изменённый scope, проверки/evidence, blockers и Git/delivery status. Для Light приложи Orchestrator marker из TaskAssessment contract.
