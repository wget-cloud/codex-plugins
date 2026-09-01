# Workflow создания backlog

## Состояния

`intake → project_discovered → audited → product_specified → decomposed → reviewed → published → verified`

Переход запрещён, если входной артефакт относится к старой revision требований или Project schema.

## Разрешённая параллельность

- Implementation Auditor может разделить read-only аудит по независимым репозиториям.
- Product Manager и Project Manager могут параллельно анализировать соответственно бизнес-семантику и существующий Project после первичного intake.
- Architect начинает decomposition только после согласованного product flow и audit evidence.
- GitHub mutation выполняет один GitHub Project Operator по exact allowlist. Параллельные массовые записи запрещены: они усложняют дедупликацию и ordering.

## Rework

- Пробел в бизнес-семантике → Product Manager или пользователь.
- Неверный owner/contract boundary → Architect.
- Неверный порядок/priority/Project field → Project Manager.
- Дубли, непроверяемые AC, смешанный scope → Backlog Reviewer возвращает `changes_requested`.

## Остановка

Верни `needs_input`, если Project неоднозначен, отсутствует обязательный product decision или нет внешней авторизации. Не создавай зависимые issues «на потом» с выдуманной семантикой.
