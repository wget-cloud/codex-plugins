# Lifecycle hooks для bugfix

Плагин использует общий stdlib Python runner `hooks/wgc_hooks.py`. Hooks ускоряют классификацию, добавляют контекст и механически напоминают о gates; они не заменяют чтение `AGENTS.md`, оркестратора или независимые проверки.

## Bugfix profile

`UserPromptSubmit` активирует профиль:

- явно по `$wgc-bugfix`;
- неявно, только когда prompt одновременно содержит действие исправления и сигнал дефекта/регрессии/ошибки.

Обычная разработка остаётся профилем `wgc-implementation`, создание backlog использует `task-creation`, а delivery эпика — `epic-implementation`. В state сохраняются только профиль, route flags, repository/change/check summaries и структурированные verdicts; исходный prompt, Project URL, tool output, логи и секреты не сохраняются.

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
- `SubagentStop`: принимает только валидный для профиля `bugfix` набор role/verdict/phase; Guardian `phase=plan` обязан повторить exact текущий FixPlan `plan_revision`. Записывает verdict/revision; verdict из implementation-профиля не может закрыть bugfix gate.
- `PreToolUse`: запрещает destructive Git и прямые cluster mutations; допускает только точный human-approved clean-cluster Argo bootstrap, описанный в GitOps reference; предупреждает о broad log collection, protected tests и deployment permission.
- `PostToolUse`: классифицирует изменённые repositories, protected-test hashes и выполненные проверки; изменение diff инвалидирует устаревшие approvals.
- `Stop`: один раз продолжает задачу, если для текущего профиля не закрыты применимые checks/gates; затем позволяет честно сообщить blocker.
- `SessionEnd`: сохраняет только минимальное локальное состояние в `.codex/wgc-implementation/state.json`.

## Bugfix completion expectations

Core structured gates: bug-triage, bug-investigator `evidence`, reproducer, bug-investigator `rca`, root-cause reviewer, architect, architecture guardian `plan`, test-maker `assessment_ready`, implementor, reviewer, architecture guardian `diff`, QA. Route flags добавляют browser/security/contract/DevOps/infrastructure/deployment gates. `none` снимает только task-specific test; backend coverage и прочие repository gates сохраняются.

State v3 валидирует flat TestAssessment marker из [test-assessment.md](test-assessment.md), запрещает `critical + none`, неполный reuse и необоснованный `standard + none`. Result ledger допускает до 1000 записей: retry того же role/phase/item/input revision заменяет прежний результат, active gates не вытесняются, overflow блокируется. V2 migration сохраняет только совместимое privacy-safe non-test verification evidence и сбрасывает legacy `test`/`coverage` evidence вместе с test/review/QA gates; malformed state блокирует completion до repository audit/reactivation. In-scope write сохраняет assessment/test-maker gate, out-of-scope/contract/migration/changed protected test инвалидирует его. Criticality не выводится механически из path/extension.

Hooks не могут доказать качество RCA, корректность теста или фактическое здоровье rollout. Оркестратор обязан читать reports, перепроверять команды и сопоставлять revision.

Clean-cluster marker `WGC_GITOPS_BOOTSTRAP_APPROVED=1` не является общим bypass: hook разрешает только repo-defined Argo chart/version/values, file-backed repository credential pipeline и immutable root Application с explicit kubeconfig/context. Marker без exact human approval, incident repair и любые near-miss mutations запрещены.

Любой marker вида `WGC_<...>_APPROVED=1`, кроме exact clean-cluster bootstrap marker, блокируется fail-closed до generic shell classification. Role/actor metadata, `WGC_AGENT_RESULT`, marker или token не предоставляют cluster permissions. `KUBECTL_AUTHORIZATION` потребует exact `task`, `environment`, `context`, `expires_at`, `action_mode` и отдельного human approval, но текущий hook не получает авторитетных runtime role/authorization данных, поэтому mutating `kubectl` сегодня недоступен; будущая поддержка требует отдельного reviewed изменения.

Stable Bash hook contract передаёт только `tool_input.command`, а top-level `cwd` остаётся cwd задачи; при таком payload обычная policy использует cwd события. Если расширенный payload содержит `workdir`, значение должно быть непустой строкой, разрешаться в существующий каталог внутри активного WGC workspace и используется как cwd только для обычных non-bootstrap checks. Некорректное, несуществующее, файловое либо внешнее значение получает privacy-safe deny.

Bootstrap exception никогда не получает supplied `workdir`: он использует отдельный top-level event cwd, а repository выбирает исключительно из доверенного session context как `<coordinator>/k8s` либо exact `repo_root` standalone `k8s`. Canonical k8s path обязан сам быть точным Git root; event cwd допускается только в корне coordinator или этого repository. Values, root Application, SSH key и kubeconfig принимаются только как абсолютные существующие file paths и канонизируются до сравнения; относительные paths и вложенный, подставной либо поглощённый parent Git repository `k8s` получают `deny`. Repo-owned makefile, values и root дополнительно обязаны совпадать с blob из immutable SHA/датированного tag.

## Диагностика

Запустить все unit tests:

```bash
python3 -m unittest discover -s hooks/tests -v
```

Runner принимает JSON события через stdin. Для изолированного запуска передай `WGC_STATE_ROOT` во временный каталог; не используй реальный workspace state в fixtures.
