# Wget Cloud Development Plugin

Версия 1.0.1 содержит два автономных skill для `/Users/estev/wc/wgetcloud/backend-services` без интеграции с task tracker, внешним backlog или MCP:

| Skill | Назначение |
|---|---|
| `wgc-implementation` | planned change → TaskAssessment → implementation → review/QA → optional delivery |
| `wgc-bugfix` | reproduction/RCA → TaskAssessment → minimal fix → review/QA → optional rollout |

Каждый skill содержит собственные role contracts и references. `agents/openai.yaml` хранит только UI metadata. Bundle не содержит MCP server, tracker launcher, tracker credentials, lifecycle карточек или tracker-specific hooks.

## Runtime policy

Skills работают только при `service_tier = "default"` и `[features].fast_mode = false`. Роли используют минимально достаточную GPT-5.6 lane из registry. Одновременно допускается максимум три субагента, `FORK_TURNS` по умолчанию `none`.

Task Assessor выбирает Light/Standard/Full по риску и сложности. Профили соответствуют фактическим границам репозитория: отдельный Go service module, `contracts`, `platform`, CI/service registry и GitOps. Security, данные, миграции, публичные Protobuf-контракты, concurrency, background work и GitOps не допускают Light. Независимость исполнителя, автора тестов, reviewer и архитектурных gates сохраняется.

Базовые проверки production-кода: `go test -race ./...`, `go vet ./...`, `golangci-lint run`, `go build ./cmd/...` и coverage ≥90%. Contract changes дополнительно требуют Buf lint/breaking/generation и consumer evidence. `services.json` остаётся source of truth для состава, image и delivery capability каждого сервиса.

Commit, push, PR, merge, release и deployment требуют отдельного явного разрешения. Kubernetes меняется только через approved GitOps. Skill сообщает фактический Git/delivery status и не подменяет недоступные проверки успешными verdicts.

## Проверка и установка

```bash
make validate
codex plugin add wget-cloud-development@wget-cloud
```

После публикации smoke выполняется в новой задаче: активная задача продолжает использовать загруженную при старте cache-версию.
