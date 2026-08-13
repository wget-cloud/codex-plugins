# UI, API, realtime и security testing

## UI/browser route

Для browser-only дефекта сначала зафиксируй:

- URL/route, viewport, browser, locale/timezone и authentication role;
- release/assets/service-worker version;
- шаг, после которого расходятся expected и observed state;
- console error и узкий network request/response summary;
- поведение после reload, back/forward, reconnect и очистки только task-owned test state.

После fix browser QA повторяет исходный сценарий и проверяет:

- loading/empty/error/success states;
- double submit, slow network, cancellation, retry и stale response;
- keyboard/focus и базовую accessibility для изменённого UI;
- responsive boundary;
- reload/navigation/cache/PWA offline-online transition, если применимо;
- WebSocket disconnect/reconnect, duplicate/out-of-order event и REST reconciliation.

Используй существующий e2e/browser harness проекта. Не добавляй визуальную зависимость или новый framework ради одного теста без архитектурного решения. Не включай auth tokens в screenshots, traces или HAR.

## API/gRPC route

Регрессионный набор должен покрывать не только happy path:

- входной validation и boundary values;
- authentication/authorization и tenant predicate;
- not-found/conflict/idempotency semantics;
- transaction rollback и partial failure;
- timeout/retry/cancellation;
- gRPC ↔ HTTP status/error mapping;
- backward-compatible optional/default fields;
- duplicate delivery/event replay, если путь событийный.

Проверяй фактический gateway endpoint и downstream contract. Passing unit test handler-а не доказывает правильность transport mapping.

## Contract route

Contract QA строит таблицу producer/consumer:

| Boundary | Проверка |
|---|---|
| REST/OpenAPI | route, payload, status, error schema, optional/default semantics |
| gRPC/proto | field numbers, enum evolution, generated code, all consumers |
| Prisma/schema | migration order, existing rows, rollback/forward compatibility |
| front-lib export | package export, `.d.ts`, runtime shape, frontend и site consumers |
| WebSocket/events/Temporal | event schema, ordering, reconnect/replay, versioning, idempotency и retry semantics |

Удаление/переименование поля, изменение default или ужесточение validation считается breaking, даже если TypeScript компилируется.

## Security route

Security reviewer обязателен, когда symptom или fix затрагивает:

- login/session/JWT/refresh/OAuth/invitation;
- roles, permissions, guards, ACL или UI capability mapping;
- tenant/company/branch scoping;
- uploads, documents, user content или PII;
- external integration credentials, webhooks или secrets.

Минимальный matrix:

1. разрешённая роль в своём tenant;
2. запрещённая роль в своём tenant;
3. разрешённая роль с resource ID другого synthetic canary tenant;
4. отсутствующая/expired authentication;
5. direct API вызов в обход UI;
6. error response без утечки существования/данных, где это важно.

Не считать UI hiding security control. Не выполнять destructive exploitation, credential spraying, чтение реальных foreign-tenant данных или cross-tenant mutation в общей среде. Deployment smoke выполняется только на synthetic canary tenants/обезличенных fixtures.

## Test evidence

Для каждой команды зафиксируй working directory, точную команду, exit code и краткий redacted result. Coverage оценивай по изменённым branch/error paths, а не только общему проценту. Flaky pass не закрывает gate: зафиксируй частоту и стабилизируй причину либо объяви blocker.
