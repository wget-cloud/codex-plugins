# Lifecycle hooks WGC

## Содержание

- Назначение
- Набор событий
- Safety policy
- State и производительность
- Completion gate
- Ограничения
- Диагностика и self-test

## Назначение

Плагин использует стандартный автоматически обнаруживаемый файл `hooks/hooks.json`. Manifest намеренно не содержит поле `hooks`: default location достаточно и сохраняет совместимость с validator. Все handlers — `type: command`, используют Python standard library и получают input события как JSON через stdin.

Hooks работают только если `cwd` распознан как coordinator Wget Cloud или один из проектов `frontend`, `backend`, `wget-cloud-front-lib`, `wget-cloud-site`, `k8s`. В остальных repositories runner завершает работу без output и side effects.

После установки или изменения hooks пользователь должен просмотреть и доверить их через стандартный hook trust flow Codex. Изменившийся hash снова требует review.

## Набор событий

| Event | Handler | Поведение |
| --- | --- | --- |
| `SessionStart` | `session-start` | Добавляет текущий project, branch/dirty summary, обязательные docs и project-specific checks. Также срабатывает после compaction через source `compact`. |
| `UserPromptSubmit` | `prompt-submit` | Выбирает профиль `$wgc-implementation` или `$wgc-bugfix`, выводит privacy-safe route flags и фиксирует baseline dirty paths. |
| `SubagentStart` | `subagent-start` | Добавляет repository/scope/Git/deployment boundaries каждому субагенту. |
| `SubagentStop` | `subagent-stop` | Проверяет `WGC_AGENT_RESULT`, role/verdict/phase и назначенную revision; сохраняет структурированный verdict или один раз возвращает агента для исправления. |
| `PreToolUse` | `pre-tool` | До Bash/edit блокирует однозначно опасные действия; для test/legacy/generated/publication changes добавляет предупреждение. |
| `PostToolUse` | `post-tool` | Асинхронно фиксирует touched paths и успешные verification commands; сообщает только релевантные gaps. |
| `Stop` | `stop` | Для активной implementation/bugfix-задачи один раз продолжает turn, если не хватает observable checks или profile-specific gate ledger. |
| `SessionEnd` | `session-end` | Деактивирует и компактно архивирует session ledger в `PLUGIN_DATA`. |

`PreCompact`/`PostCompact` не используются: state обновляется после tool calls, а `SessionStart(source=compact)` уже восстанавливает контекст после compaction. `PermissionRequest` не используется, потому что плагин не должен автоматически разрешать escalation.

## Safety policy

### Блокируется

- прямые Kubernetes mutations; разрешены read-only `get`, `describe`, `logs`, `events`, `top`, `wait`, `diff`, `rollout status`, `auth can-i` и безопасные config queries;
- `helm install/upgrade/uninstall/rollback`;
- mutating `argocd app` и Flux commands;
- `git reset --hard`, forced `git clean`, force-push, worktree-discarding checkout/restore, forced branch deletion;
- `git submodule update --remote` и массовый `submodule foreach`;
- broad Docker prune, Terraform apply/destroy и broad recursive deletion;
- patch за пределами coordinator/repository boundary или внутри `.git`;
- private keys и strong access-token patterns в commands/patches;
- commit при failed staged `git diff --check` или unresolved conflicts.

### Предупреждается, но не блокируется

- изменение test/spec paths: роль не видна в `PreToolUse`, поэтому решение принимает hash/diff gate;
- изменение `legacy/` или generated GitOps profile без видимого source profile;
- commit/push/merge, которым всё равно требуется явное разрешение пользователя;
- runtime log collection без гарантии узкого time/service scope и redaction;
- production change без зафиксированного targeted test/coverage;
- cross-repository diff;
- k8s change без renderer/validation/infrastructure review.

Hook не auto-approve permissions и не выполняет tests, formatting, commit, push или deployment.

При внутренней ошибке `PreToolUse` работает fail-closed и блокирует call до исправления hook. Остальные информационные handlers работают fail-open, чтобы ошибка bookkeeping не ломала рабочую сессию.

## State и производительность

State хранится только в `${PLUGIN_DATA}/hook-state/<session-id>.json`. В product repositories не создаются lock, cache или ledger files. Исходный prompt, текст shell-команд и runtime output не сохраняются — только SHA-256, безопасное имя runner, exit code, профиль, route flags и verification tags.

Async `PostToolUse` не задерживает основную tool operation. JSON updates защищены platform-specific lock и atomic replace. Ledger ограничивает количество commands, paths и guard events.

При активации сохраняется baseline Git status всех пяти repositories. Completion logic учитывает новые/touched paths, а не уже существовавший dirty state пользователя.

## Completion gate

Runner классифицирует изменённые paths и успешные команды:

- production code требует `test`;
- backend production code дополнительно требует `coverage`;
- frontend требует `typecheck`;
- front-lib требует `typecheck` и `build`;
- public front-lib paths требуют consumer check;
- site требует `typecheck`, `lint` и `build`;
- backend proto/Prisma paths требуют штатные generation/validation commands;
- k8s требует `gitops-render` и `validate`.

Lifecycle ledger ожидает структурированные успешные результаты Architect, Test-maker, Reviewer, post-implementation Architecture Guardian и QA; для k8s также Infrastructure Reviewer. Diff-facing approvals привязаны к workspace revision и инвалидируются после новой правки. Финальный текст может перечислить эти verdicts, но не заменяет агентные артефакты. Если evidence отсутствует, первый `Stop` возвращает `decision: block` с точным списком gaps. Следующее событие имеет `stop_hook_active: true`, поэтому runner не создаёт бесконечный цикл: он позволяет завершить turn, деактивирует workflow и сохраняет оставшиеся gaps. Агент обязан выполнить проверки или честно описать blocker.

Профиль bugfix дополнительно требует структурированные gates Bug-triage, Bug-investigator/RCA, Reproducer, Implementor и plan approval Architecture Guardian. Route flags добавляют browser, security, contract, DevOps/infrastructure и approval-gated deployment gates; UI требует e2e/browser evidence, разрешённый deployment — smoke evidence.

Успешное прохождение hook gate не доказывает корректность теста, архитектуры или QA. Оркестратор всё равно проверяет command output, protected hashes, diff scope и отдельные agent artifacts.

## Ограничения

- Tool hooks не покрывают hosted tools и специальные tool paths, которые opt out из lifecycle path.
- `PreToolUse` получает tool name/input, но не надёжную business role субагента. Нельзя механически разрешить Test-maker и одновременно запретить Implementor для одного test path без недокументированной transcript parsing.
- Regex policy намеренно блокирует только действия с высокой уверенностью. Семантические architecture violations остаются Architecture Guardian.
- Verification tags показывают, что команда с подходящим именем завершилась с exit code 0; они не подтверждают качество или полноту coverage.
- В standalone clone project распознаётся по имени Git root. Если repository переименован, hook тихо отключится до обновления detection rules.

## Диагностика и self-test

Проверить конфигурацию и runner:

```bash
python3 -m json.tool hooks/hooks.json
python3 -m py_compile hooks/wgc_hooks.py
python3 -m unittest discover -s hooks/tests -v
```

Если hook не запускается:

1. Проверить, что plugin enabled и hooks feature не отключена.
2. Открыть `/hooks`, найти source и доверить текущий hash.
3. Проверить, что cwd находится в распознаваемом WGC Git repository.
4. Проверить доступность `python3` либо `py -3` на Windows.
5. Проверить stderr hook run и writable `PLUGIN_DATA`.

Не исправлять проблему добавлением hook state в product repository или отключением safety policy без явного решения владельца.
