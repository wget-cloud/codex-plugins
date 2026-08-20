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
| `SubagentStop` | `subagent-stop` | Проверяет профильный `WGC_AGENT_RESULT`, точный набор role/verdict/phase и назначенную revision; сохраняет структурированный verdict или один раз возвращает агента для исправления. |
| `PreToolUse` | `pre-tool` | До Bash/edit блокирует однозначно опасные действия; для test/legacy/generated/publication changes добавляет предупреждение. |
| `PostToolUse` | `post-tool` | Синхронно и в пределах bounded timeout фиксирует touched paths и успешные verification commands; сообщает только релевантные gaps. |
| `Stop` | `stop` | Для активной implementation/bugfix-задачи один раз продолжает turn, если не хватает observable checks или profile-specific gate ledger. |
| `SessionEnd` | `session-end` | Деактивирует и компактно архивирует session ledger в `PLUGIN_DATA`. |

`PreCompact`/`PostCompact` не используются: state обновляется после tool calls, а `SessionStart(source=compact)` уже восстанавливает контекст после compaction. `PermissionRequest` не используется, потому что плагин не должен автоматически разрешать escalation.

## Safety policy

### Блокируется

- прямые Kubernetes mutations вне точного clean-cluster bootstrap-контракта; разрешены read-only `get`, `describe`, `logs`, `events`, `top`, `wait`, `diff`, `rollout status`, `auth can-i` и безопасные config queries;
- `helm install/upgrade/uninstall/rollback` вне exact bootstrap-команды;
- mutating `argocd app` и Flux commands вне точного storage-only staged-sync исключения;
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

### Clean-cluster bootstrap exception

Исключение существует только для fixed point: новый WGC cluster ещё не имеет Argo CD, поэтому GitOps reconciler физически не может применить первый root. Перед каждым разрешённым вызовом человек должен одобрить exact cluster context, kubeconfig, repository revision и bootstrap action. Команда обязана начинаться с `WGC_GITOPS_BOOTSTRAP_APPROVED=1`; marker без такого approval запрещён процессом и не является auto-approval.

Hook fail-closed сверяет repository-owned `infrastructure/k8s/bootstrap/argocd/makefile`, `values.yaml` и `bootstrap/roots/<context>.yaml`; blobs всех трёх файлов должны точно совпасть с immutable `targetRevision` root Application. Shell expansions, redirections, alternate executable paths и любые separators кроме двух exact pipes запрещены. Разрешены только:

- `helm upgrade --install` exact release/chart/version/values в namespace `argocd`, с explicit kubeconfig/context, wait и timeout;
- exact pipeline, который строит repository Secret локально из SSH key file, добавляет только Argo repository label и применяет stdin в `argocd`; inline key запрещён;
- `kubectl apply` exact root Application `<context>.yaml`, если repo URL/path/context согласованы, а `targetRevision` — immutable SHA или датированный release tag.

Любой дополнительный segment, другой chart/version/namespace/context/path/secret/label/URL, mutable revision или обычная cluster mutation по-прежнему получает `deny`. После появления root Application все workload/controller/app изменения выполняются через Git и Argo; marker нельзя использовать для repair, sync или обхода ownership.

### Storage-only staged-sync exception

После отдельного human approval hook разрешает только пять последовательных операций для `twc-wise-finch`: cluster root → core bundle → local-path storage → local-path smoke bundle → storage smoke. Команда обязана байт-в-байт совпадать с `/usr/bin/env -i` contract, содержать только фиксированную среду и запускать root-owned `/usr/bin/python3 /usr/local/libexec/wget-cloud-staged-sync/runner.py` с согласованной парой `--stage`/`--app` и immutable revision `6c2c3e9dadde2eec3d13fde830bc6db0392b13b8`.

Hook сначала fd-attests `/bin/ls`, затем exact canonical ancestor chain `/`, `/usr`, `/usr/bin` как stable root:wheel `0755` directories с пустым ACL, совпадающей pre/post-lstat identity и одновременно `effectiveWritable=false`/`effectiveDeletable=false`; только после этого fd-attests `/usr/bin/env` и `/usr/bin/python3`. Затем проверяются SHA-256, root/wheel ownership, read-only mode и отсутствие symlink/hardlink для установленного runner и manifest. Runner повторно fail-closed проверяет root-owned non-writable ancestor chain, directory/file modes, exact Darwin UUID read-only ACL, link counts, fd-based pre/post hashes/device/inode identity, effective non-writability, versioned `argocd-v3.0.0-darwin-arm64` и системные binaries, exact kubeconfig hash/context/server/CA и безопасную embedded-cert schema. Live Argo evidence обязано подтверждать полный normalized desired-state contract каждого predecessor/target, exact app-of-apps owner tracking label для stages 2–5 и отсутствие tracking label у root, их status/revision и повторный полный target contract после sync; target до sync ровно OutOfSync с допустимым health, conditions пусты и нет незавершённой либо failed operation. Child processes используют только sanitized environment, `shell=False` и exact argv для одного sync, wait и read-only state checks. Raw `argocd`, selectors, multi-app sync, wrappers, дополнительные flags, shell extensions, proxy/Argo environment overrides, ingress apps `twc-wise-finch-ingress`, `traefik`, `ingress-canary` и любые шаги после storage smoke получают `deny`.

### Reviewed ingress/router recovery exception

Отдельное исключение существует только для recovery `twc-wise-finch` по annotated tag `twc-wise-finch-argocd-recovery-2026-08-20.2` (tag object `37c2ee42cb542d30ca200c06e1430d151428a70c`, peeled commit `6247abd4aec30e6a75aeba70123676019762f1a6`). Exact runner использует Argo core-mode, отбрасывает только server-owned Kubernetes metadata и проверяет published live scope: stage-1 previous state, completed predecessors, pending target и future Applications с точной revision/operation absence semantics. Только stage 1 выполняет `app set` root Application на tag и bounded read-only polls до spec-tag/raw-tag-object convergence; каждая из семи стадий выполняет один `app sync --timeout 600` без `--revision`/`--prune`, затем `app wait --sync --health --operation --timeout 600`, причём outer process timeout имеет безопасный запас больше 600 секунд. До и после каждой стадии runner in-process подтверждает exact GitHub tag-ref object type `tag`, tag object и peeled commit через два exact API URL без redirects. Только documented metadata keys допустимы; identity URL/type/SHA и отсутствие конфликтующего identity остаются exact. Root:wheel `0600` token читается один раз из stable `O_NOFOLLOW` FD с exact pre/post identity/size/length и ACL user `FFFFEEEE-DDDD-CCCC-BBBB-AAAA000001F5`, существует только в Authorization header и редактируется из любого failure/output/log; `git ls-remote` не используется. Bounded HTTP adapter принимает только approved JSON media types, ограничивает body 64 KiB и использует deterministic timeout. Полный Application/source graph, raw Argo revision lineage и все state gates остаются обязательными. Последовательность заканчивается на `argocd-public`; bundles `controllers`, `vault-restore`, `eso-ready`, `data`, `apps` и `full` не входят в исключение.

Router hook допускает только distinct materialized `/usr/local/libexec/wget-cloud-ingress-recovery/router-manifest.json`; digest source `approvalTemplate` всегда блокируется. Runtime approval должен быть материализован человеком из свежего (не старше 300 секунд) уникального router snapshot, опубликованных foundation shapes и сгенерированного exact `TimewebRouterRecoveryPlan`. Production entrypoint читает manifest одним stable FD, заново проверяет все published digests и выполняет ordered plan без динамического расширения действий. Router ID открывается динамически, token читается один раз через stable FD из root:wheel `0600` файла с точным read-only ACL пользователя `FFFFEEEE-DDDD-CCCC-BBBB-AAAA000001F5` и никогда не попадает в Git, argv, env или log. После fresh final GET runner выдаёт exact `TimewebRouterRecoveryPoststate`; только attested `routerPlan`/`routerPoststate` и promotion final-digest lineage может стать stage-7 router gate.

Изменение source plugin, cachebuster и reinstall допустимы только как явно одобренная работа текущей задачи. Уже активная задача продолжает использовать ранее загруженный hook; smoke обновлённого bundle выполняется только в новой задаче после reinstall. Reinstall сам по себе не разрешает materialization, cluster/router mutation или deployment.

Staged-sync exception, как и bootstrap, использует top-level event cwd и trusted session k8s root, игнорируя supplied tool `workdir`. Marker фиксирует уже полученное человеческое разрешение, но не создаёт его.

Stable Bash hook contract передаёт только `tool_input.command`, а top-level `cwd` остаётся cwd задачи; при таком payload обычная policy использует cwd события. Если расширенный payload содержит `workdir`, значение должно быть непустой строкой, разрешаться в существующий каталог внутри активного WGC workspace и используется как cwd только для обычных non-bootstrap checks. Некорректное, несуществующее, файловое либо внешнее значение блокируется без раскрытия пути.

Bootstrap exception никогда не получает supplied `workdir`: он использует отдельный top-level event cwd, а repository выбирает исключительно из доверенного session context как `<coordinator>/k8s` либо exact `repo_root` standalone `k8s`. Canonical k8s path обязан сам быть точным Git root; event cwd допускается только в корне coordinator или этого repository. Values, root Application, SSH key и kubeconfig принимаются только как абсолютные существующие file paths и канонизируются до сравнения; относительные paths и вложенный, подставной либо поглощённый parent Git repository `k8s` получают `deny`. Repo-owned makefile, values и root дополнительно обязаны совпадать с blob из immutable SHA/датированного tag.

При внутренней ошибке `PreToolUse` работает fail-closed и блокирует call до исправления hook. Остальные информационные handlers работают fail-open, чтобы ошибка bookkeeping не ломала рабочую сессию.

## State и производительность

State хранится только в `${PLUGIN_DATA}/hook-state/<session-id>.json`. В product repositories не создаются lock, cache или ledger files. Исходный prompt, текст shell-команд и runtime output не сохраняются — только SHA-256, безопасное имя runner, exit code, профиль, route flags и verification tags.

`PostToolUse` выполняется синхронно с timeout 10 секунд и делает только ограниченное bookkeeping без запуска tests или других длительных команд. JSON updates защищены platform-specific lock и atomic replace. Ledger ограничивает количество commands, paths и guard events.

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
