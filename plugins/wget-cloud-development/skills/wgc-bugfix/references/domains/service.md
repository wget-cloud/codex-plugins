# Go service

Сначала найди запись сервиса в `services.json` и его architecture profile: `stateless-adapter`, `domain-service` или `orchestration-service`. Каждый `services/<name>` имеет собственные `go.mod`, `go.sum`, binary, Dockerfile, image, configuration, release identity, deployment и rollback.

Соблюдай pragmatic Hexagonal Architecture: inbound adapters → application → domain, а внешние runtimes доступны через consumer-owned outbound ports и concrete adapters. Composition root находится в `cmd/<runtime>/main.go`. Generated, SQL, SDK и transport types не проникают в domain. Stateless adapter не получает искусственный domain layer; orchestration service координирует владельцев доменов, но не присваивает их правила или данные.

Минимум для production change в изменённом module: `go test -race ./...`, `go vet ./...`, `golangci-lint run`, coverage ≥90% и `go build ./cmd/...`. Выполняй команды из корня module. Проверяй typed errors и status mapping, deadlines, bounded retries, idempotency, tenant/RBAC, fail-fast config, structured logs без payload/PII, trace propagation, health и graceful shutdown по затронутому пути.
