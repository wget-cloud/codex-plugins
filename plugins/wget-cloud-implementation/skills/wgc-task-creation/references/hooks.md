# Lifecycle hooks для создания backlog

## Профиль

Hooks выбирают профиль `task-creation` по явному `$wgc-task-creation` или по сочетанию запроса на создание задач/backlog с указанным GitHub Project. Явное имя другого WGC skill имеет приоритет над inference. В state сохраняются только privacy-safe route flags, summaries и структурированные verdicts; исходный prompt, Project URL, bodies задач, tool output и credentials не сохраняются.

## Что проверяется

- `SubagentStop` принимает только role/verdict, объявленные в локальном agent registry.
- `Stop` требует актуальные gates Product Manager, Project Manager, Implementation Auditor, Architect и Backlog Reviewer.
- Если пользователь разрешил внешнюю mutation, дополнительно требуется `github-project-operator:published` для текущей revision.
- Отсутствие локального diff не завершает workflow автоматически: результат этого skill находится в GitHub Project.
- После первой блокировки `Stop` не создаёт бесконечный continuation loop; оставшиеся gaps должны быть честно отражены пользователю.

Hook не доказывает содержимое GitHub Project и не заменяет read-after-write verification. Оркестратор обязан самостоятельно перечитать созданные issues/items. GitHub Project Operator получает только exact allowlist из утверждённого `MutationPlan`; Project schema, repositories, labels вне согласованного scope и любые другие внешние объекты не изменяются.
