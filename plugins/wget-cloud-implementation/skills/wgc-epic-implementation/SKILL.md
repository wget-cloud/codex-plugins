---
name: wgc-epic-implementation
description: Implement a Wget Cloud epic or ordered pool of GitHub Project tasks through product, project, architecture, test, implementation, review, QA, integration, and optional GitOps gates. Use when the user asks to implement an epic, roadmap slice, batch, priority class, or multiple related Project items and expects progress to be tracked in GitHub Project. Do not use to create or audit a backlog without implementation; use wgc-task-creation. For one standalone planned task without Project-level coordination, use wgc-implementation; for a reported defect requiring RCA, use wgc-bugfix.
---

# WGC Epic Implementation

Исполняй Project pool атомарными delivery units; Project хранит scope/order/status, оркестратор — gate truth.

## Preflight — первая операция

До чтения файлов, MCP и субагентов проверь `service_tier = "default"` и `[features].fast_mode = false`. `fast|priority|ultrafast` → `WGC_FAST_MODE_FORBIDDEN`; неизвестная конфигурация → `WGC_SERVICE_TIER_UNVERIFIABLE`. Lane `economy` (Luna/low) разрешена.

## Контекст

Прочитай root/затронутые `AGENTS.md` и обязательные docs, затем [workflow](references/workflow.md), [test policy](references/test-assessment.md), [GitHub contract](references/github-projects.md), [batch execution](references/batch-execution.md), [gates](references/artifacts-and-gates.md), [hooks](references/hooks.md) и [registry](references/agents/index.md). Для delivery прочитай [GitOps](references/gitops-and-deployment.md). Перечитай Project/items и Git state перед планированием.

Project/pool должны быть однозначны. Не выбирай весь backlog автоматически; без exact epic/filter/item set не начинай mutation или implementation.

## Инварианты

- Не реализуй item с незакрытыми dependencies, непроверяемыми AC, неизвестным owner repo или open product decision.
- Один Implementor — один atomic slice; writers не пересекают repo/contract boundary.
- PMs/Guardian/Reviewer/QA/Infrastructure Reviewer repository read-only; Operator меняет только approved Project fields.
- Каждый frozen item имеет собственный TestAssessment и protected-test contract.
- Commit/push/PR/release/deployment требуют явного разрешения. Status никогда не опережает фактический delivery.
- Kubernetes — только GitOps. Неизвестный defect переключается в bugfix/RCA workflow.

## Pipeline

1. Project Manager создаёт immutable snapshot schema/items/dependencies/statuses/PRs.
2. Заморозь максимум 100 selected items с item/plan/acceptance revisions и minimum criticality; зафиксируй exclusions, authority, concurrency и stop conditions.
3. Product/Project gates отделяют ready/blocked/ambiguous. Architect строит contract-first DAG; Guardian одобряет revision.
4. Для каждой ready wave Operator ставит truthful status; Test-maker выпускает per-item assessment; Implementor делает slice; оркестратор проверяет diff/docs/hashes.
5. Reviewer/Guardian, QA и Product outcome gate проверяют current item revision. Blocking finding возвращает item в rework и инвалидирует downstream approvals.
6. После wave проверь cross-repo contracts/migrations/gitlinks; пересчитай readiness следующей wave.
7. Без delivery authority оставь truthful pre-delivery status. `Done` — только для реально доставленного outcome.
8. Перечитай Project и верни `EpicRunReport`.

Используй role contracts из [registry](references/agents/index.md), `FORK_TURNS: none` и максимум три активных субагента. Assignment повторяет exact item ID/revision, snapshot, scope, dependencies, tests и verdict contract. Не объединяй независимые gates.

Готово, когда каждый selected item имеет truthful status/evidence, product/project reconciliation, approved architecture/current diff, актуальный assessment, reviewer/QA/outcome gates, согласованные contracts/docs/order и честный deployment result. Отчёт перечисляет completed/ready/blocked/deferred items, diffs/checks и next slice.
