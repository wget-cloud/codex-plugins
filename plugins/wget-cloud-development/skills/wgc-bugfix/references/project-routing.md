# Маршрутизация backend-services

Target repository: `/Users/estev/wc/wgetcloud/backend-services`. `services.json`, root `AGENTS.md`, service docs и фактический execution path являются source of truth.

| Симптом | Начальный owner | Обязательные границы |
|---|---|---|
| Один runtime/service | `services/<name>` | module, architecture profile, transport → application → domain/ports → adapters, config и runtime lifecycle |
| gRPC/Protobuf compatibility | `contracts` + provider/consumers | field/RPC compatibility, status/deadline semantics, generated diff, Buf и consumer tests |
| Общий config/logging/telemetry/middleware | `platform` | минимум два consumers или approved baseline, отсутствие business/service DTO, affected-service matrix |
| Не тот CI row/image/delivery flag | `services.json`, `scripts/ci`, workflows | affected/unaffected services, `force_all`, per-service identity, disabled-delivery guard |
| Container/runtime failure | service Dockerfile + composition root | one binary, non-root, fail-fast config, health, graceful shutdown, image scan |
| Rollout/config/secret wiring | external GitOps owner | exact service/environment/image, Vault/External Secrets, render, rollout, smoke и rollback |

Каждый service — независимый Go module, image и deployment boundary, но repository имеет одну Git history. Прямые imports между `services/*` запрещены. `go.work` облегчает локальные checks, но не объединяет runtimes. Изменение contracts, `platform` или repository tooling требует доказанного consumer/affected-service audit.

Перед исправлением сервиса прочитай `doc/services/<name>/README.md`, `BUSINESS_LOGIC.md` и `ARCHITECTURE.md`. Для мигрирующего сервиса также прочитай `doc/migration/<name>.md`; не объявляй Go runtime delivery owner до фактических rollout/soak/ownership gates.
