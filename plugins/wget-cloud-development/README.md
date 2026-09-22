# Wget Cloud Development Plugin

Версия 1.0.6 содержит два автономных skill для `/Users/estev/wc/wgetcloud/backend-services` без интеграции с task tracker, внешним backlog или MCP:

| Skill | Назначение |
|---|---|
| `wgc-implementation` | planned change → TaskAssessment → implementation → review/QA → optional delivery |
| `wgc-bugfix` | reproduction/RCA → TaskAssessment → minimal fix → review/QA → optional rollout |

Каждый skill содержит собственные role contracts и references. `agents/openai.yaml` хранит только UI metadata. Bundle не содержит MCP server, tracker launcher, tracker credentials, lifecycle карточек или tracker-specific hooks.

## Runtime policy

Роли используют минимально достаточную GPT-5.6 lane из registry. Для `gpt-5.6-sol` действует жёсткий предел `medium`: уровни `high`, `xhigh`, `max` и `ultra` запрещены для оркестратора и субагентов. Одновременно допускается максимум три субагента, `FORK_TURNS` по умолчанию `none`, а полный fork истории запрещён. DecisionSnapshot и ResumeCapsule переживают compaction, assignment ledger исключает дубли, а immutable diff review, selective invalidation и ступени T0–T3 сокращают повторный анализ и дорогие проверки без ослабления независимых gates.

Перед первым production write Full workflow один раз на сервис замораживает cross-slice contracts, auth/tenant semantics, ownership и compatibility. Большие сервисы выполняются траншами связанных RPC/behavior families, а не отдельным полным role pipeline на каждый handler. Implementor пишет production code и обычные slice-local tests; отдельный Test-maker владеет только действительно независимыми protected regression/contract/security tests. Дорогие T2/T3 проверки, immutable snapshot и independent gates повторяются только после релевантной invalidation.

Каждое назначение проходит spawn preflight с явными `model` и `reasoning_effort`; наследование модели и `fork_turns: all` считаются contract violation. EfficiencyBudget ограничивает число назначений, ожиданий, дорогих проверок и rework на транш. На границе сервиса workflow выпускает компактный ServiceHandoff, чтобы следующий сервис не наследовал длинную историю исполнения.

Task Assessor выбирает Light/Standard/Full по риску и сложности. Профили соответствуют фактическим границам репозитория: отдельный Go service module, `contracts`, `platform`, CI/service registry и GitOps. Security, данные, миграции, публичные Protobuf-контракты, concurrency, background work и GitOps не допускают Light. Независимость protected-test author, reviewer и архитектурных gates сохраняется там, где риск оправдывает отдельную роль.

Базовые проверки production-кода: `go test -race ./...`, `go vet ./...`, `golangci-lint run`, `go build ./cmd/...` и coverage ≥90%. Contract changes дополнительно требуют Buf lint/breaking/generation и consumer evidence. `services.json` остаётся source of truth для состава, image и delivery capability каждого сервиса.

Commit, push, PR, merge, release и deployment требуют отдельного явного разрешения. Kubernetes меняется только через approved GitOps. Skill сообщает фактический Git/delivery status и не подменяет недоступные проверки успешными verdicts.

## Проверка и установка

```bash
make validate
codex plugin add wget-cloud-development@wget-cloud
```

После публикации smoke выполняется в новой задаче: активная задача продолжает использовать загруженную при старте cache-версию.
