# Wget Cloud Development Plugin

Версия 2.0.2 содержит два автономных skill для `/Users/estev/wc/wgetcloud/backend-services` без интеграции с task tracker, внешним backlog или MCP:

| Skill | Назначение |
|---|---|
| `wgc-implementation` | planned change → TaskAssessment → implementation → review/QA → optional delivery |
| `wgc-bugfix` | reproduction/RCA → TaskAssessment → minimal fix → review/QA → optional rollout |

Каждый skill содержит собственные role contracts и references. `agents/openai.yaml` хранит только UI metadata. Bundle не содержит MCP server, tracker launcher, tracker credentials, lifecycle карточек или tracker-specific hooks.

## Runtime policy

В обоих `SKILL.md` установлен `MVP_SKIP_TESTS: true`. Пока флаг включён, агенты не создают, не изменяют и не запускают тесты, не считают и не проверяют покрытие. `TestAssessment` фиксирует `test_disposition: none`, `coverage_mode: skipped_by_mvp_flag`, альтернативные проверки и остаточные риски. Сборка, статические и контрактные проверки остаются. Требования `backend-services` и CI к тестам/покрытию не меняются: если они обязательны, результат помечается как не прошедший эти gate. Для возврата обычной политики установите `MVP_SKIP_TESTS: false` в обоих skill.

Стандартный workflow ориентирован на скорость и экономный расход токенов без отдельного профиля: economy — Luna/low, focused — Luna/medium, balanced — Sol/low, architecture — Sol/medium только для Architect. Astra полностью запрещена; Sol выше `medium` запрещён. Один Implementor на Sol/low делает production code; при выключенном флаге он также пишет минимальные tests. Reviewer либо один specialist добавляется только для конкретного риска.

На slice действует жёсткий default budget: максимум 3 assignments, 10 coordination decisions, один unchanged wait без анализа и один correction/recheck. При выключенном флаге Implementor пишет 2–5 минимальных tests вместе с production code. Correction возвращается тому же агенту; полный role pipeline после finding не перезапускается. Test-maker используется только для protected critical baseline при выключенном флаге, а нетестовые T2-проверки запускаются один раз на service/release boundary по repository requirement.

Для нового сервиса skill один раз собирает функциональные решения и запрашивает разрешение на выбранный объём. Внутренние транши не требуют нового пользовательского согласования без изменения продуктовой семантики или scope. Вопросы задаются через доступный UI выбора; варианты остаются в обычном сообщении, если ответ не поступил. Ожидание ответа не имеет искусственного срока и не запускает sleep/status loop.

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
