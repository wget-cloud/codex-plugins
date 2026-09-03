---
name: wgc-bugfix
description: Coordinate evidence-driven diagnosis and repair of Wget Cloud defects across frontend, backend microservices, shared front-lib, public sites, and Kubernetes GitOps. Use when a user reports a bug, regression, crash, exception, failed UI/API/realtime/PWA flow, authorization or tenant-isolation defect, production incident, or behavior that no longer matches expectations and asks to fix it. The skill gathers scoped logs and runtime evidence when available, reproduces before patching, establishes a supported root cause, protects regression tests from implementor edits, performs independent review and architecture checks, runs targeted QA including browser/API/security specialists when relevant, and uses gated GitOps rollout only with explicit human approval. Do not use for explanation-only diagnostics with no requested fix, planned feature development, or blind deployment.
---

# WGC Bugfix

Доказывай цепочку «наблюдение → воспроизведение → RCA → TestAssessment → минимальная правка → независимая проверка». Оркестратор один управляет transitions.

## Preflight — первая операция

До чтения файлов, MCP и субагентов проверь `service_tier = "default"` и `[features].fast_mode = false`. `fast|priority|ultrafast` → `WGC_FAST_MODE_FORBIDDEN`; отсутствующее или неоднозначное значение → `WGC_SERVICE_TIER_UNVERIFIABLE`. Lane `economy` (Luna/low) не является Codex Fast mode.

## Контекст по требованию

1. Прочитай root и затронутые `AGENTS.md`, затем обязательные project docs.
2. Прочитай [routing](references/project-routing.md), [workflow](references/workflow.md), [test policy](references/test-assessment.md), [registry](references/agents/index.md) и [gates](references/artifacts-and-gates.md).
3. Для runtime evidence прочитай [evidence](references/evidence-and-reproduction.md); для UI/API/realtime/PWA/RBAC/contracts — [specialist testing](references/ui-api-security-testing.md); для CI/k8s/release — [GitOps](references/gitops-and-deployment.md). [Hooks](references/hooks.md) читай при диагностике.
4. Role files открывай непосредственно перед spawn; conditional specialists — только по route signal.

## Инварианты

- Production-код не меняется до `reproduced`. `characterized` допустим только с runtime evidence, failing characterization test и явным `reproduction_waiver`.
- Гипотеза не является RCA: покажи конкретный execution path и отвергнутые альтернативы.
- Runtime inspection read-only, узкий по времени/сервису и privacy-safe; raw logs, prompts, tokens, cookies и PII не сохраняются.
- Корень/submodules — отдельные repositories. Сохраняй dirty work; commit/push/PR/release/deployment требуют явного разрешения.
- Test-maker владеет assessment и `add/update` tests/hashes; Implementor их не меняет. Review/guardian/security/contract/infrastructure read-only; QA не чинит findings.
- Fix минимален относительно RCA. Kubernetes — только GitOps; deployment agent не пишет source.

## BugCase и routes

Зафиксируй observed/expected, environment/release, time/location/frequency, actor/tenant/role, severity/impact, steps и redacted evidence handles. Неизвестное пометь `unknown`. `deployment_requested` не равно `deployment_authorized`.

Основной route: `local|ui|cross-repo|incident|deployment`; усилители: `browser|security|contract|gitops`.

## Pipeline

1. Triage определяет blast radius и безопасный порядок исследования.
2. Investigator собирает минимальное evidence; Reproducer фиксирует стабильный baseline.
3. Investigator выпускает RCA; независимый root-cause reviewer требует `root_cause_supported`.
4. Architect проектирует minimal fix/rollback; Guardian одобряет plan revision.
5. Test-maker выпускает `assessment_ready`. Critical defect не допускает `none`; protected hashes должны совпадать.
6. Implementor выполняет один атомарный slice; оркестратор проверяет diff против RCA и hashes.
7. Reviewer/Guardian и применимые security/contract specialists проверяют current revision.
8. QA повторяет исходную репродукцию и boundary/error/concurrency/regression cases; browser QA — реальный UI path.
9. Оркестратор повторяет critical evidence/checks, сверяет consumers/docs и delivery boundaries.
10. Без approval верни `BugfixReport`; с approval следуй GitOps rollout/smoke/observation.

Полные invalidation/rework rules — в [workflow](references/workflow.md).

## Субагенты и готовность

Используй route из [registry](references/agents/index.md), `FORK_TURNS: none` и максимум три активных субагента. Assignment содержит exact scope, facts, artifacts, permissions, source of truth и output contract. Не объединяй investigator/RCA reviewer, implementor/test-maker/reviewer/guardian, DevOps/infrastructure reviewer.

Оркестратор лично проверяет Git state, evidence links, current diff/revision, protected hashes и исходную репродукцию. Готово, когда reproduction до/после доказана, RCA независимо approved, TestAssessment актуален, required checks и specialist gates закрыты, QA pass, docs/contracts/consumers синхронизированы, diff минимален и delivery status честен.

`BugfixReport`: symptom, RCA, fix, regression proof, repositories/files, checks/verdicts, Git/deployment status, risks и human actions.
