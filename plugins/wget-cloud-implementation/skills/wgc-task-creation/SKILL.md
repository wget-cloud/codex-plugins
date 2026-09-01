---
name: wgc-task-creation
description: Create or refine product-quality Wget Cloud tasks, epics, bug/refactor follow-ups, and ordered backlogs in a GitHub Project from a feature request, audit, gap analysis, or business workflow. Use when the user asks to analyze implementation completeness, decompose work, create issues, populate a project backlog, prioritize dependencies, or turn requirements into executable tasks. Do not use to implement the created tasks; use wgc-epic-implementation for an epic or pool and wgc-implementation for one planned engineering task.
---

# WGC Task Creation

Преобразуй вводные пользователя и фактическое состояние системы в проверенный backlog, а не в список общих пожеланий. Главный агент остаётся оркестратором и проверяет результаты субагентов. Product Manager отвечает за ценность и бизнес-логику, Project Manager — за исполнимую очередь, а GitHub Project Operator — за строго ограниченную публикацию по утверждённому `MutationPlan`.

## Определить GitHub Project

Проект можно передать URL вида `https://github.com/orgs/<owner>/projects/<number>`, owner/number или естественным языком. Если проект не указан:

1. Определи owner из Git remotes и локального контекста.
2. Найди доступные Projects read-only.
3. Используй проект только если выбор однозначен; иначе задай один короткий вопрос до внешних записей.

GitHub Project обязателен для массового создания. Если доступ к Projects отсутствует, не оставляй частично опубликованный backlog без явного отчёта: запроси нужный scope/авторизацию, сохрани подготовленный `BacklogPlan` и продолжи после подтверждения.

## Сначала загрузить контекст

1. Полностью прочитай корневой `AGENTS.md`, затем инструкции и обязательную документацию затронутых репозиториев.
2. Прочитай [workflow.md](references/workflow.md), [GitHub Project contract](references/github-projects.md), [artifacts-and-gates.md](references/artifacts-and-gates.md), [lifecycle hooks](references/hooks.md) и [agent registry](references/agents/index.md).
3. Проверь фактические remotes, ветки/status, source execution path, contracts/schema, тесты, docs и уже существующие GitHub issues/items. Mock, placeholder, dormant или неподключённый код не считай готовой функцией.
4. Не полагайся на название страницы или README как единственное доказательство реализации.

## Неподвижные правила

- Не создавай дубли. Перед записью ищи по stable work item ID, нормализованному заголовку, parent issue, URL и существующим Project items.
- Эпики размещай в координационном repository, а исполнимые дочерние задачи — в repository-владельце изменения. Cross-repo работу дели по contract/delivery boundaries.
- Каждая задача описывает одну проверяемую причину изменения. Не смешивай независимые feature, bugfix, refactor, infra и cleanup.
- Баги и рефакторинги включай в общий DAG: блокирующие/data-loss/security/financial риски раньше функций, cleanup без влияния — после rollout.
- Приоритет и порядок — разные измерения. P0 может стоять поздно в DAG как release gate; dependency sequence всё равно должен быть явным.
- Пользовательские продуктовые решения не заменяй техническими предположениями. Если выбор меняет деньги, lifecycle, ownership, compliance, migration или UX, спроси пользователя.
- Создание/редактирование issues и Project items допустимо только когда пользователь попросил создать/добавить/обновить backlog. Анализ без такого запроса остаётся read-only.
- Не выполнять implementation, commit, push, PR, merge, release или deployment в этом skill.

## Выполнить workflow

1. **Intake.** Нормализуй `TaskRequest`: цель, actors, workflow, expected outcomes, exclusions, указанный/разрешённый Project, repositories и неизвестные продуктовые решения.
2. **Project discovery.** Project Manager read-only проверяет поля, Status/Priority options, views, existing items, issue repositories, labels и write scope.
3. **Implementation audit.** Implementation Auditor исследует фактическую готовность по независимым repository/domain slices и возвращает evidence-backed gap matrix.
4. **Product specification.** Product Manager формирует целевой business flow, normal/error/boundary cases и вопросы, которые нельзя безопасно вывести из контекста. Оркестратор задаёт пользователю только материальные вопросы и обновляет revision требований.
5. **Architecture decomposition.** Architect определяет ownership, contract boundaries, migration/compatibility, dependency DAG и минимальные атомарные задачи.
6. **Delivery planning.** Project Manager присваивает sequence, P0–P3, parent/child hierarchy, repository/label, readiness и рекомендуемый status.
7. **Backlog gate.** Backlog Reviewer независимо проверяет полноту, отсутствие дублей, PM-качество, архитектурную исполнимость, dependencies и соответствие полям Project. При `changes_requested` верни замечания авторам и повтори gate.
8. **GitHub mutation.** GitHub Project Operator получает exact allowlist и создаёт/обновляет issues идемпотентно, добавляет native sub-issues и Project items, выставляет точные Status/Priority/labels и явно позиционирует items в dependency order. Главный агент независимо перепроверяет результат.
9. **Verification.** Перечитай Project после записи: count, missing fields, ordering, hierarchy, labels, owner repos, duplicate titles/URLs и тела выборочных задач. Верни `BacklogReport` со ссылками и нерешёнными вопросами.

## Качество задачи

Каждая исполнимая задача обязана содержать:

- цель и измеримый бизнес-результат;
- текущую проблему/evidence, если это bug или refactor;
- бизнес-логику и ownership boundary;
- normal, error, boundary, authorization/tenant, concurrency/retry cases по применимости;
- требования к contracts, migration, observability, tests/coverage и docs;
- критерии приёмки, проверяемые без чтения намерений автора;
- зависимости, exclusions, repository, label, priority и parent epic.

Используй [GitHub Project contract](references/github-projects.md) для mutation и [artifacts-and-gates.md](references/artifacts-and-gates.md) для формата результатов.

## Управлять субагентами

Перед каждым запуском выбери роль из [agent registry](references/agents/index.md), прочитай её файл и передай полный assignment envelope. Независимые repository audits можно выполнять параллельно. Product Manager не утверждает собственную спецификацию, Architect не является Backlog Reviewer, а Project Manager не подменяет продуктовые решения.

## Условие готовности

Skill завершён только когда:

- Project однозначно определён и доступ проверен;
- product decisions закрыты либо явно помечены `needs_input` до публикации зависимых задач;
- аудит связан с конкретными source/contract/test evidence;
- backlog reviewer дал `approved` для текущей revision;
- GitHub mutation была идемпотентной и верифицирована чтением Project;
- все созданные items имеют owner repository, требуемые labels, Status, Priority, parent и правильную позицию;
- финальный отчёт даёт ссылку на Project/roadmap, количество эпиков/задач, priority distribution и известные пробелы.
