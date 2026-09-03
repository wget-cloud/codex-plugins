---
name: wgc-task-creation
description: Create or refine product-quality Wget Cloud tasks, epics, bug/refactor follow-ups, and ordered backlogs in a GitHub Project from a feature request, audit, gap analysis, or business workflow. Use when the user asks to analyze implementation completeness, decompose work, create issues, populate a project backlog, prioritize dependencies, or turn requirements into executable tasks. Do not use to implement the created tasks; use wgc-epic-implementation for an epic or pool and wgc-implementation for one planned engineering task.
---

# WGC Task Creation

Создавай evidence-backed исполнимый backlog, а не список пожеланий.

## Preflight — первая операция

До чтения файлов, MCP и субагентов проверь `service_tier = "default"` и `[features].fast_mode = false`. `fast|priority|ultrafast` → `WGC_FAST_MODE_FORBIDDEN`; неизвестная конфигурация → `WGC_SERVICE_TIER_UNVERIFIABLE`. Lane `economy` (Luna/low) разрешена.

## Контекст

Прочитай root/затронутые `AGENTS.md` и обязательные project docs, затем [workflow](references/workflow.md), [provisional test policy](references/test-assessment.md), [GitHub contract](references/github-projects.md), [gates](references/artifacts-and-gates.md), [hooks](references/hooks.md) и [registry](references/agents/index.md). Проверь remotes/status, execution paths, contracts, tests, docs и существующие issues/items. Mock/dormant code не считается готовой функцией.

Project может быть URL или owner/number. Если не указан, найди read-only и продолжай только при однозначном match. Массовая публикация требует Project; при недоступном write scope сохрани `BacklogPlan` без частичной mutation.

## Инварианты

- До записи ищи дубли по stable ID, title, parent, URL и Project items.
- Epic принадлежит coordination repo, child task — owner repo. Одна task = одна проверяемая причина изменения.
- Bugs/refactors входят в общий DAG; dependency order и priority — разные поля.
- Не выдумывай product decisions о деньгах, lifecycle, ownership, compliance, migration или UX.
- GitHub mutation разрешена только при явном запросе создать/обновить backlog и выполняется exact `MutationPlan`.
- Test policy остаётся provisional в body/AC; не создавай для неё Project field.
- Этот skill не реализует код и не выполняет commit/push/PR/release/deployment.

## Pipeline

1. Нормализуй `TaskRequest`: goal, actors, flow, outcomes, exclusions, Project, repos и open decisions.
2. Project Manager читает schema/options/views/items/labels и write scope.
3. Auditor строит evidence-backed gap matrix; Product Manager задаёт target flow и cases.
4. Architect определяет ownership/contracts/migration и dependency DAG; Project Manager — sequence/P0–P3/status.
5. Backlog Reviewer независимо проверяет completeness, duplicates, AC, architecture и field mapping.
6. Operator по allowlist идемпотентно создаёт/обновляет issues, sub-issues/items/fields и ordering.
7. Перечитай Project и проверь count, duplicates, fields, hierarchy, labels, owner repos и order.

Каждая task содержит measurable outcome, evidence, ownership/business rules, applicable normal/error/boundary/auth/concurrency cases, provisional test policy, contracts/migration/observability/docs, verifiable AC, dependencies, exclusions, repo/label/priority/parent.

Используй [registry](references/agents/index.md), `FORK_TURNS: none` и максимум три активных субагента. Независимые audits можно параллелить; PM/Architect не утверждают собственную работу.

Готово после однозначного Project, закрытых product decisions, evidence-linked audit, approved backlog review и read-after-write verification. `BacklogReport` содержит Project URL, counts, hierarchy/priority и unresolved gaps.
