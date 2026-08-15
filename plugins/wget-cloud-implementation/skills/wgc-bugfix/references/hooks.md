# Lifecycle hooks для bugfix

Плагин использует общий stdlib Python runner `hooks/wgc_hooks.py`. Hooks ускоряют классификацию, добавляют контекст и механически напоминают о gates; они не заменяют чтение `AGENTS.md`, оркестратора или независимые проверки.

## Bugfix profile

`UserPromptSubmit` активирует профиль:

- явно по `$wgc-bugfix`;
- неявно, только когда prompt одновременно содержит действие исправления и сигнал дефекта/регрессии/ошибки.

Обычная разработка остаётся профилем `wgc-implementation`. В state сохраняются только профиль, route flags, repository/change/check summaries и структурированные verdicts; исходный prompt, tool output, логи и секреты не сохраняются.

Route flags:

- `ui` — browser/UI/PWA/realtime;
- `security` — auth/RBAC/permission/tenant;
- `contract` — API/gRPC/proto/schema/public export;
- `incident` — production/staging incident, crash, 5xx, timeout;
- `gitops` — Kubernetes/Helm/Argo/CI/CD;
- `deployment` — явное намерение раскатки.

## Event behavior

- `SessionStart`: краткая карта WGC и текущий active profile.
- `SubagentStart`: repository boundaries, роль, запрет на prompt/log persistence и напоминание read-only evidence rules.
- `SubagentStop`: принимает только валидный для профиля `bugfix` набор role/verdict/phase и записывает verdict/revision; verdict из implementation-профиля не может закрыть bugfix gate.
- `PreToolUse`: запрещает destructive Git и прямые cluster mutations; допускает только точный human-approved clean-cluster Argo bootstrap, описанный в GitOps reference; предупреждает о broad log collection, protected tests и deployment permission.
- `PostToolUse`: классифицирует изменённые repositories, protected-test hashes и выполненные проверки; изменение diff инвалидирует устаревшие approvals.
- `Stop`: один раз продолжает задачу, если для текущего профиля не закрыты применимые checks/gates; затем позволяет честно сообщить blocker.
- `SessionEnd`: сохраняет только минимальное локальное состояние в `.codex/wgc-implementation/state.json`.

## Bugfix completion expectations

Core structured gates: bug-triage, bug-investigator `evidence`, reproducer, bug-investigator `rca`, root-cause reviewer, architect, architecture guardian `plan`, test-maker, implementor, reviewer, architecture guardian `diff`, QA. Route flags добавляют browser/security/contract/DevOps/infrastructure/deployment gates. Для production source hooks также ожидают релевантные tests/coverage; дополнительные typecheck/lint/build определяются типом проекта.

Hooks не могут доказать качество RCA, корректность теста или фактическое здоровье rollout. Оркестратор обязан читать reports, перепроверять команды и сопоставлять revision.

Clean-cluster marker `WGC_GITOPS_BOOTSTRAP_APPROVED=1` не является общим bypass: hook разрешает только repo-defined Argo chart/version/values, file-backed repository credential pipeline и immutable root Application с explicit kubeconfig/context. Marker без exact human approval, incident repair и любые near-miss mutations запрещены.

## Диагностика

Запустить все unit tests:

```bash
python3 -m unittest discover -s hooks/tests -v
```

Runner принимает JSON события через stdin. Для изолированного запуска передай `WGC_STATE_ROOT` во временный каталог; не используй реальный workspace state в fixtures.
