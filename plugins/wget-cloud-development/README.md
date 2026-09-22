# Wget Cloud Development Plugin

Версия 1.0.7 содержит два автономных skill для `/Users/estev/wc/wgetcloud/backend-services` без интеграции с task tracker, внешним backlog или MCP:

| Skill | Назначение |
|---|---|
| `wgc-implementation` | planned change → TaskAssessment → implementation → review/QA → optional delivery |
| `wgc-bugfix` | reproduction/RCA → TaskAssessment → minimal fix → review/QA → optional rollout |

Каждый skill содержит собственные role contracts и references. `agents/openai.yaml` хранит только UI metadata. Bundle не содержит MCP server, tracker launcher, tracker credentials, lifecycle карточек или tracker-specific hooks.

## Runtime policy

Роли используют минимально достаточную GPT-5.6 lane из registry. Terra/medium допустима для Light/Standard orchestration, Sol/medium — для Full и сложных critical routes; effort выше `medium` не используется без явного запроса пользователя. Одновременно допускается максимум три субагента, `FORK_TURNS` по умолчанию `none`, а полный fork истории запрещён. DecisionSnapshot и ResumeCapsule переживают compaction, assignment ledger исключает дубли, а immutable diff review, selective invalidation и ступени T0–T3 сокращают повторный анализ и дорогие проверки без ослабления независимых gates.

Перед первым production write Full workflow один раз на сервис замораживает cross-slice contracts, auth/tenant semantics, ownership и compatibility. Большие сервисы выполняются траншами связанных RPC/behavior families, а не отдельным полным role pipeline на каждый handler. Implementor пишет production code и обычные slice-local tests; отдельный Test-maker владеет только действительно независимыми protected regression/contract/security tests. Дорогие T2/T3 проверки, immutable snapshot и independent gates повторяются только после релевантной invalidation.

Каждое назначение проходит spawn preflight с явными `model` и `reasoning_effort`; наследование модели и `fork_turns: all` считаются contract violation. EfficiencyBudget отдельно считает назначения, retries, coordination decisions, unchanged waits, passive wait time, дорогие проверки и rework. Неизменившийся wait не запускает повторный анализ или status-only follow-up. На границе сервиса workflow выпускает компактный ServiceHandoff и выполняет явный `STOP_AFTER_SERVICE`.

Orchestrator выбирает Light/Standard/Full и вызывает отдельного Task Assessor только при неоднозначном, Full, cross-module/cross-repo или расширившемся scope. Criticality тестов не переводит задачу автоматически в Full: bounded critical change использует Standard-critical с точечными specialist gates. Профили соответствуют фактическим границам репозитория: отдельный Go service module, `contracts`, `platform`, CI/service registry и GitOps.

Базовые проверки production-кода берутся из актуальных `AGENTS.md`, workflows и строки сервиса в `services.json`: `go test -race ./...`, `go vet ./...`, `golangci-lint run`, `go build ./cmd/...` и exact `coverageMin`/ratchet. Contract changes дополнительно требуют Buf lint/breaking/generation и consumer evidence. `services.json` остаётся source of truth для состава, coverage, image и delivery capability каждого сервиса.

Commit, push, PR, merge, release и deployment требуют отдельного явного разрешения. Kubernetes меняется только через approved GitOps. Skill сообщает фактический Git/delivery status и не подменяет недоступные проверки успешными verdicts.

## Проверка и установка

```bash
make validate
codex plugin add wget-cloud-development@wget-cloud
```

После публикации smoke выполняется в новой задаче: активная задача продолжает использовать загруженную при старте cache-версию.
