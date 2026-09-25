---
name: wgc-bugfix
description: Coordinate tracker-independent, evidence-driven diagnosis and repair of defects in the Wget Cloud backend-services Go workspace. Use for service, platform, Protobuf/gRPC contract, CI matrix, container, migration, security, tenant-isolation, concurrency, background-work, or GitOps failures that must be reproduced and fixed. The skill establishes a supported root cause, protects regression tests from implementor edits, performs independent review and architecture checks, runs targeted API/contract/security QA, and uses gated rollout only with explicit human approval. Do not use for unrelated repositories, explanation-only diagnostics, planned feature development, or blind deployment.
---

# WGC Bugfix

## MVP flag

`MVP_SKIP_TESTS: true` — переключатель этого автономного skill. При `true` не создавай, не изменяй и не запускай тесты, не вычисляй и не проверяй покрытие, не назначай Test-maker. Передавай значение флага каждому агенту; в `TestAssessment` фиксируй `test_disposition: none`, `coverage_mode: skipped_by_mvp_flag`, альтернативное evidence и остаточный риск даже для critical fix. Это правило имеет приоритет над test-writing, test-running и coverage указаниями в references этого skill. При `false` применяется обычная [test policy](references/test-assessment.md). Требования CI и repository не изменяются: если они всё ещё требуют тесты или покрытие, сообщи об этом как о непроверенном gate и не заявляй release readiness.

## Граница внешних систем

Работай только с сообщением пользователя, repository context и доступными runtime evidence. Skill не читает и не изменяет task trackers, backlog или внешние карточки. Если expected behavior не определено либо исправление требует продуктового выбора, исследуй безопасный локальный контекст и запроси конкретное решение пользователя до production-правки.

## Intake и выбор команды

1. Прочитай root/затронутые AGENTS.md и обязательные project docs; проверь Git baseline и фактический execution path.
2. Прочитай [coordination contract](references/coordination-efficiency.md), [TaskAssessment](references/task-assessment.md) и [registry](references/agents/index.md). Создай DecisionSnapshot. Переиспользуй актуальный assessment; для очевидного Light/Standard route выпусти его как Orchestrator, а отдельного Task Assessor назначай только при неоднозначном, Full, cross-module/cross-repo или расширившемся scope.
3. По verdict выбери Light/Standard/Full. Всегда прочитай [repository profile](references/domains/repository.md), затем загружай только выбранные [Service](references/domains/service.md), [Contracts](references/domains/contracts.md), [Platform](references/domains/platform.md), [CI](references/domains/ci.md) и [GitOps](references/domains/gitops.md). Role file — перед конкретным назначением.
4. Перед execution прочитай [test policy](references/test-assessment.md) и [verification](references/verification.md). [Full workflow](references/workflow.md) — только Full; [gates](references/artifacts-and-gates.md) — когда нужен формат артефакта.

## Этот процесс

До production fix зафиксируй observed/expected и минимальное evidence причины. Light/Standard: Orchestrator проверяет baseline/причину/результат; при `MVP_SKIP_TESTS: false` Implementor добавляет небольшой regression test вместе с fix, если он полезен. Full не запускает каталог ролей автоматически: investigator/reproducer/RCA reviewer нужны только при действительно неоднозначной причине. Runtime inspection read-only и scoped.

## Исполнение и готовность

Оркестратор владеет WorkItem, DecisionSnapshot, ResumeCapsule и EfficiencyBudget, но не пишет production code/tests. Стандартный workflow — один Implementor на Sol/low и targeted verification; один Reviewer либо specialist добавляется только по конкретному риску. При `MVP_SKIP_TESTS: false` отдельный Test-maker нужен лишь для protected critical baseline. Максимум три assignments на fix, 10 coordination decisions и один correction batch существующему Implementor; полный pipeline не перезапускается. Sol требует подтверждённого blocker escalation. Каждый агент возвращает только назначенный artifact/verdict с current assessment revision.

Сохраняй пользовательские изменения. Каждый `services/<name>`, `platform` и `contracts` — отдельный Go module внутри одного Git repository; module boundary не является отдельной Git history. Commit/push/PR/merge/release/deployment требуют явного разрешения. Kubernetes — через approved GitOps; DevOps не является Infrastructure Reviewer.

Scope expansion или новые риски → новая оценка; устаревшие approvals/checks не засчитываются. При `MVP_SKIP_TESTS: false` не писать тесты без конкретного regression value и не повторять успешные проверки без основания. Требования repository/CI сохраняются. Готовность требует актуальных route gates, доказанной acceptance и честного delivery status. При blocker сообщи его; не изображай пропущенные роли как approved.

Финал: результат, изменённый scope, проверки/evidence, blockers и Git/delivery status. Для Light и compact bugfix приложи Orchestrator marker из TaskAssessment contract.
