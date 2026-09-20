# API, contract, runtime и security testing

## API/runtime route

Зафиксируй exact service/module, binary/image identity, environment, request/contract revision, observed status/error/latency и correlation ID. Для gRPC/HTTP воспроизведения сохрани redacted request shape без credentials, payload/HTML/documents или PII.

Проверяй:

- application/domain typed error → gRPC/HTTP status mapping;
- deadlines, cancellation, bounded retry и idempotency;
- connection failure, malformed/oversized input и dependency 4xx/5xx;
- trace propagation, bounded metrics labels и отсутствие sensitive payload в logs;
- readiness/liveness и graceful shutdown;
- concurrency через `go test -race ./...` и targeted stress/load evidence по риску.

## Contract route

Protobuf является wire source of truth. Проверяй package/service/RPC names, field numbers/types, optional/default semantics, metadata, deadlines, status codes, message-size limits и всех consumers. Contract diff требует `buf lint`, `buf breaking` against correct base, reproducible generation и clean generated diff. Generated Go code вручную не редактируется.

## Security/data route

Проверяй tenant predicate, RBAC, ownership, cross-tenant negative cases, injection/path traversal/SSRF по фактическому adapter, secret/config boundary и отсутствие PII/document payload в logs. Используй только synthetic task-owned data. Не выполняй destructive exploitation, credential spraying или чтение реальных foreign-tenant данных.

Stateful service владеет собственной schema/migrations; transaction boundary задаёт application use case. Предпочтительный baseline — `pgx`/`sqlc`; другой persistence stack не предполагается без фактического evidence.
