# GitHub Project contract

## Идентификация

Нормализуй `PROJECT_OWNER`, `PROJECT_NUMBER`, `PROJECT_ID`, URL и точные field/option IDs. Не полагайся на отображаемое имя поля без чтения schema.

## Read before write

1. Прочитай project fields и options.
2. Загрузи все relevant items с pagination.
3. Проверь existing issues во всех owner repositories, включая closed.
4. Проверь наличие labels; создавай недостающий project label только если пользователь запросил разметку и repository writable.

## Идемпотентность

Stable identity состоит из work item code, normalized title, owner repository и parent epic. В body созданного этим workflow issue добавляй служебный HTML marker без пользовательских данных: `wgc-work-item`, Project owner/number, owner repository, parent code и spec revision/hash управляемых полей.

Повторный запуск может автоматически обновить issue только когда marker совпадает, expected `updatedAt`/managed-fields hash не изменился и Project item всё ещё связан с тем же issue. Выполняй compare-and-swap непосредственно перед write. Если найден duplicate без marker либо body/fields были изменены после snapshot, не перезаписывай его: используй как read-only dependency/reference, предложи reuse без изменения или верни `authorization_required` с точным diff. Сам marker не даёт право менять свободный пользовательский текст вне управляемых секций.

## Иерархия

- Umbrella roadmap и cross-repo epics: coordination repository.
- Child issue: repository, который владеет production change.
- Native sub-issue — предпочтительный parent contract; checklist со ссылками остаётся читаемым fallback.

## Поля

- `Status`: точное option name существующего Project; для новых задач обычно Backlog.
- `Priority`: P0 blocker/critical integrity, P1 required v1 path, P2 next valuable increment, P3 deferred cleanup.
- Labels: точный repository/project label плюс `bug` или `refactor`, когда это действительно тип работы.

Если Priority отсутствует, сначала сообщи об этом и получи отдельное разрешение на изменение Project schema; обычный запрос на создание задач не разрешает молча добавлять поля.

## Порядок

Номер в title помогает чтению, но не заменяет ручную позицию Project. После массового добавления явно выставь Project item position по dependency DAG и перечитай список.

## Mutation boundary

Create/edit/add/reorder — внешняя запись. Выполняй её только по утверждённому `MutationPlan` в запрошенном Project и repositories. План обязан содержать expected state/fingerprint каждой обновляемой сущности. Additive публикация разрешает создать недостающий exact label только когда пользователь прямо потребовал эту разметку; иначе запроси разрешение. Не закрывай/архивируй существующие issues, не назначай людей, не создавай Project fields и не меняй чужие или конфликтно изменённые items без отдельного разрешения.
