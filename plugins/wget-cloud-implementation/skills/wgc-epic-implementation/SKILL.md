---
name: wgc-epic-implementation
description: Implement a Wget Cloud epic or ordered pool of GitHub Project tasks through product, project, architecture, test, implementation, review, QA, integration, and optional GitOps gates. Use when the user asks to implement an epic, roadmap slice, batch, priority class, or multiple related Project items and expects progress to be tracked in GitHub Project. Do not use to create or audit a backlog without implementation; use wgc-task-creation. For one standalone planned task without Project-level coordination, use wgc-implementation; for a reported defect requiring RCA, use wgc-bugfix.
---

# WGC Epic Implementation

Реализуй epic/task pool как серию атомарных delivery units, где GitHub Project является источником scope, порядка, статусов и progress evidence. Главный агент остаётся оркестратором: он выбирает ready wave, применяет Project status transitions, проверяет repository diffs и не позволяет суммарному прогрессу скрыть незавершённую задачу.

## Определить Project и scope

Project можно передать URL, owner/number или естественным языком. Epic/pool задаётся parent issue, item IDs, work item codes, priority/status filter или явно перечисленными задачами.

Если Project не указан, определи owner из remotes и найди Projects read-only. Используй только однозначный match; иначе спроси пользователя. Если pool не указан, не выбирай весь backlog автоматически: попроси epic/filter или предложи минимальную ready wave без начала записи/implementation.

## Сначала загрузить контекст

1. Полностью прочитай корневой и вложенные `AGENTS.md`, README и обязательную architecture/business документацию затронутых repositories.
2. Прочитай [workflow.md](references/workflow.md), [GitHub Project contract](references/github-projects.md), [batch-execution.md](references/batch-execution.md), [artifacts-and-gates.md](references/artifacts-and-gates.md), [lifecycle hooks](references/hooks.md) и [agent registry](references/agents/index.md).
3. Для k8s/release/deployment прочитай [gitops-and-deployment.md](references/gitops-and-deployment.md).
4. Перечитай выбранные issues и Project fields непосредственно перед планированием; не работай по сохранённой копии backlog.
5. Проверь status/branch/upstream/remote/dirty state каждого repository и сохрани пользовательские изменения.

## Неподвижные правила

- Project item и его issue body являются scope contract, но не отменяют более новые явные вводные пользователя. Конфликт возвращается Product Manager и пользователю.
- Не реализуй item, если обязательные dependencies не доставлены, AC непроверяемы, owner repository неизвестен или product decision открыт.
- Один Implementor получает один атомарный item/slice. Два write-агента не работают одновременно в одном repository или общем contract boundary.
- Product Manager, Project Manager, Architecture Guardian, Reviewer, QA и Infrastructure Reviewer read-only относительно repository. Exact Project mutations выполняет GitHub Project Operator по утверждённому sync plan; главный агент независимо проверяет результат.
- Test-maker владеет acceptance/regression tests и фиксирует protected paths/hashes. Implementor не меняет их.
- Не создавай commit, push, PR, merge, release или deployment без явного разрешения. Project-backed implementation разрешает обновлять status выбранных items, но не означает право доставить код.
- Kubernetes меняется только через GitOps source. Deployment требует отдельного approval, привязанного к exact repo/commit/environment/image/rendered diff.
- Не помечай item `Done`, пока его фактический delivery outcome не соответствует договорённому scope. Локально реализованная, но не опубликованная задача остаётся на подходящем pre-delivery status.
- Переводи item только в реально существующий exact status option. Если нужного semantic status нет, оставь последний правдивый существующий status, отрази gate в отчёте и не меняй Project schema без отдельного разрешения.
- При обнаружении неизвестного дефекта переключи конкретный item на evidence-driven bugfix workflow; не маскируй RCA внутри feature batch.

## Выполнить workflow

1. **Project snapshot.** Project Manager читает fields/options/views/items, parent/sub-issues, status, priority, dependencies, linked PRs и формирует immutable `ProjectSnapshot` revision.
2. **Scope selection.** Оркестратор фиксирует `EpicRun`: selected items, exclusions, delivery authority, target environment, concurrency cap и stop conditions.
3. **Readiness/product gate.** Product Manager в phase `scope` проверяет intent и AC каждого selected item. Project Manager отделяет ready, blocked и ambiguous; blocked items не переводятся в In Progress.
4. **Architecture DAG.** Explorer-агенты исследуют независимые repositories. Architect строит contract-first DAG и waves; Architecture Guardian одобряет plan revision.
5. **Wave execution.** Для каждого ready item GitHub Project Operator применяет подтверждённый status → In Progress; Test-maker фиксирует baseline; Implementor выполняет slice; оркестратор проверяет diff/tests/docs и protected hashes.
6. **Independent gates.** После реализации item переводится в существующий эквивалент code review. Reviewer и Architecture Guardian проверяют current revision. Затем status → существующий эквивалент in testing, QA выполняет behavioral/error/security/concurrency checks, а Product Manager в phase `outcome` принимает наблюдаемый бизнес-результат.
7. **Rework.** Любой blocking finding возвращает item в In Progress, инвалидирует downstream approvals и запускает минимальный rework loop. Соседние независимые items могут продолжать работу.
8. **Integration.** После wave оркестратор запускает cross-repo/contract checks, проверяет migration order, root gitlinks и отсутствие scope drift. Project Manager обновляет dependency readiness следующей wave.
9. **Delivery.** Без публикации item остаётся `code review`, `in testing` или `ready for deploy` по фактическому gate. При явно разрешённой доставке выполни Git/PR/release/GitOps границы; только подтверждённо доставленный item получает Done.
10. **Final reconciliation.** Перечитай Project и repositories: selected count, statuses, priority, unresolved blockers, linked changes, gate evidence и next ready wave. Верни `EpicRunReport`.

Точный status mapping и правила mutation находятся в [GitHub Project contract](references/github-projects.md); wave/concurrency — в [batch-execution.md](references/batch-execution.md).

## Управлять субагентами

Перед каждым запуском выбери роль из [agent registry](references/agents/index.md), прочитай её contract и передай assignment envelope с item URL/code, ProjectSnapshot revision, repository/path allowlist, dependency evidence, protected tests и ожидаемым verdict.

Минимальный состав для epic/pool: Product Manager, Project Manager, Architect, Architecture Guardian, Test-maker, Implementor, Reviewer, QA и GitHub Project Operator. Explorer используется для reconnaissance; DevOps/Infrastructure Reviewer/Deployment Agent — только для GitOps/delivery. Не создавай роли ради формальности, но не объединяй независимые gates.

## Условие готовности

EpicRun готов только когда:

- каждый selected item имеет финальный фактический статус и evidence; нет карточек, оставленных In Progress без владельца/blocker;
- Product Manager подтвердил acceptance semantics, Project Manager — dependency/status reconciliation;
- plan и каждый изменённый diff прошли независимые architecture gates;
- tests/typecheck/lint/build/coverage и QA соответствуют риску каждого item;
- cross-repo contracts, migrations, docs и delivery order согласованы;
- Project перечитан после mutation, а статусы не опережают реальность;
- deployment либо доказан health/smoke/observation evidence, либо честно отмечен blocked/failed/rolled back;
- финальный отчёт содержит completed/ready/blocked/deferred items, repository diffs, checks, gates, Git/PR/release/deployment status и следующий ready slice.
