---
name: wgc-bugfix
description: Coordinate evidence-driven diagnosis and repair of Wget Cloud defects across frontend, backend microservices, shared front-lib, public sites, and Kubernetes GitOps. Use when a user reports a bug, regression, crash, exception, failed UI/API/realtime/PWA flow, authorization or tenant-isolation defect, production incident, or behavior that no longer matches expectations and asks to fix it. The skill gathers scoped logs and runtime evidence when available, reproduces before patching, establishes a supported root cause, protects regression tests from implementor edits, performs independent review and architecture checks, runs targeted QA including browser/API/security specialists when relevant, and uses gated GitOps rollout only with explicit human approval. Do not use for explanation-only diagnostics with no requested fix, planned feature development, or blind deployment.
---

# WGC Bugfix

Исправляй дефект как доказуемую цепочку «наблюдение → воспроизведение → первопричина → регрессионный тест → минимальная правка → независимая проверка». Главный агент остаётся оркестратором: он управляет состоянием, назначает роли, перепроверяет факты и единолично переводит задачу между gate. Субагенты возвращают артефакты и verdict, но не объявляют задачу завершённой и не разрешают deployment.

## Сначала загрузить контекст

1. Полностью прочитай корневой `AGENTS.md`, затем `AGENTS.md` каждого затронутого проекта. Вложенные инструкции имеют приоритет.
2. Прочитай README и обязательную архитектурную/бизнес-документацию затронутых проектов до изменения кода.
3. Прочитай [project-routing.md](references/project-routing.md), [workflow.md](references/workflow.md), [agents.md](references/agents.md) и [artifacts-and-gates.md](references/artifacts-and-gates.md).
4. Для логов, трассировки, воспроизведения и работы с чувствительными данными прочитай [evidence-and-reproduction.md](references/evidence-and-reproduction.md).
5. Для UI, API, realtime, PWA, RBAC, tenant isolation или контрактов прочитай [ui-api-security-testing.md](references/ui-api-security-testing.md).
6. Если затронуты `k8s`, CI/CD, release или rollout, полностью прочитай [gitops-and-deployment.md](references/gitops-and-deployment.md).
7. При блокировке lifecycle hook или диагностике прочитай [hooks.md](references/hooks.md).

Не полагайся на сохранённую карту проекта: проверь Git status, текущую ветку, manifests, execution path, contracts/schema, тесты, CI и фактическое состояние среды.

## Неподвижные правила

- Не меняй production-код до `reproduced`; исключение — только `characterized` с достаточными runtime-доказательствами, failing characterization test и явным human `reproduction_waiver`.
- Не называй гипотезу root cause. `RootCauseAnalysis` обязан связывать наблюдение с конкретным execution path и объяснять, почему отвергнуты основные альтернативы.
- Сбор логов, traces, metrics, network payloads и browser state выполняй read-only, с минимальным time range и scope. Не сохраняй токены, cookies, персональные данные, полные дампы и сырые production-логи в Git или артефактах.
- Рассматривай корень и пять submodules как отдельные Git-репозитории. Не смешивай их commits, ветки или историю.
- Сохраняй пользовательские изменения. Не делай reset, checkout, rebase, merge, cleanup, pull или массовое переключение веток без отдельного основания и разрешения.
- Не создавай commit, push, PR, merge, release или deployment, если пользователь явно этого не разрешил. Разрешение на bugfix не означает разрешение на публикацию.
- Test-maker владеет регрессионными тестами и фиксирует их SHA-256. Implementor не изменяет защищённые тесты; изменение возвращается test-maker и инвалидирует downstream gates.
- Architecture guardian, reviewer, security reviewer, contract QA и infrastructure reviewer ничего не пишут. QA и browser QA не исправляют найденные дефекты.
- Любое исправление должно быть минимальным относительно доказанной первопричины. Сопутствующий refactor выноси из bugfix, если без него можно безопасно устранить дефект.
- Kubernetes изменяется строго GitOps. Deployment agent не пишет код или манифесты и работает только после явного deployment-запроса либо отдельного человеческого approval, привязанного к commit, environment и image digest/tag.

## Сформировать BugCase и выбрать маршрут

До запуска агентов нормализуй пользовательский комментарий в `BugCase`:

- наблюдаемое и ожидаемое поведение;
- environment, release/commit/image, tenant и роль пользователя, если известны;
- время, URL/endpoint, частота, предусловия и минимальные шаги;
- severity и business impact без преувеличения;
- actor tenant/role, resource-owner tenant и data classification для security/tenant кейса;
- доступные evidence handles: request/trace/correlation ID, screenshot, console error, log query;
- exclusions и требуется ли deployment.

Храни `deployment_requested` отдельно от `deployment_authorized`; intent в исходном комментарии не является разрешением на будущую неизвестную revision.

Не блокируйся из-за неизвестных полей, если их можно безопасно установить read-only исследованием. Помечай неизвестное как `unknown`, не выдумывай значение.

Выбери один основной маршрут и любые применимые усилители:

- `local` — локально воспроизводимый дефект в одном проекте;
- `ui` — браузер, forms, navigation, realtime, offline/PWA, accessibility;
- `cross-repo` — общий контракт, proto/schema, front-lib или несколько приложений;
- `incident` — production/staging degradation, 5xx, timeout, crash, failed rollout;
- `deployment` — исправление требует GitOps-подготовки и раскатки.

Усилители: `browser`, `security`, `contract`, `gitops`. Правила выбора агентов и gates описаны в [workflow.md](references/workflow.md).

## Выполнить workflow

1. **Triage.** Bug-triage проверяет полноту кейса, blast radius, severity, вероятные boundaries и выбирает безопасный порядок исследования.
2. **Evidence.** Bug-investigator строит временную линию, собирает минимальные логи/traces/metrics и формулирует проверяемые гипотезы без изменения внешнего состояния.
3. **Reproduction.** Reproducer получает стабильный сценарий и baseline. Если дефект не воспроизводится, не переходи к случайной правке: запроси недостающий сигнал или создай согласованную characterization strategy.
4. **Root cause.** Bug-investigator связывает дефект с конкретным execution path, данными, контрактом или rollout delta. Gate требует `root_cause_supported`; независимый root-cause reviewer проверяет доказательность до проектирования fix.
5. **Fix design.** Architect выдаёт минимальный `FixPlan`, rollback boundary, test strategy и порядок cross-repo изменений. Architecture guardian независимо одобряет план. Если до RCA использовался waiver-маршрут, ранние `CharacterizationPlan/Test` не закрывают эти финальные gates — architect, guardian и test-maker повторяют их уже против одобренной RCA.
6. **Regression contract.** Test-maker создаёт failing regression test или точную executable specification, фиксирует protected files и SHA-256.
7. **Implementation.** Implementor выполняет одну атомарную часть плана и не трогает защищённые тесты. После каждого логического изменения запускает минимальные релевантные проверки с coverage.
8. **Independent review.** Reviewer и architecture guardian проверяют готовый diff. Для auth/RBAC/tenant запускай security reviewer; для REST/gRPC/proto/schema/public exports/WebSocket event или reconnect protocol — contract QA.
9. **Adversarial QA.** QA повторяет исходную репродукцию, error/boundary/concurrency/regression scenarios. Для UI/PWA/realtime browser QA проверяет настоящий браузерный путь и сохраняет только безопасные доказательства.
10. **Integration.** Оркестратор повторяет ключевые проверки, сверяет protected-test hashes, документацию, consumers и атомарность каждого repository diff.
11. **Delivery.** Без deployment заверши `BugfixReport`. При разрешённом deployment выполни отдельный GitOps-конвейер, smoke и observation window.

Полные переходы, invalidation rules и rework loops находятся в [workflow.md](references/workflow.md).

## Управлять агентами

Перед запуском каждого агента передай ему:

- роль, task slice и разрешённые repositories/paths;
- входные артефакты и подтверждённые факты;
- source-of-truth документы и environment ограничения;
- разрешённые инструменты, границы task-owned test data и явные запреты;
- требуемый verdict и формат результата из [artifacts-and-gates.md](references/artifacts-and-gates.md).

Не объединяй роли, которым нужна независимость: investigator не утверждает собственную RCA, implementor не является test-maker/reviewer/guardian, DevOps не является infrastructure reviewer, deployment agent не является автором rollout manifests. Параллельные write-агенты допустимы только в непересекающихся репозиториях и после утверждённого DAG.

Оркестратор обязан сам:

- проверить status/branch/upstream/remote каждого затронутого репозитория;
- проверить ключевые evidence links и не принимать текст агента за доказательство;
- сопоставить diff с root cause и утверждённым scope;
- проверить protected-test hashes до и после implementor;
- повторить критичные команды и исходную репродукцию;
- вести gate ledger по revision и инвалидировать устаревшие approvals после изменения diff;
- сообщать пользователю о недоступной среде, неполной репродукции, чувствительных данных и действиях, требующих разрешения.

## Условие готовности

Bugfix готов только когда:

- исходный дефект воспроизведён либо доказан failing characterization test по формальному waiver-маршруту; после правки тот же сценарий/test проходит;
- RCA поддержана evidence, соответствует фактической цепочке исполнения и независимо одобрена root-cause reviewer;
- регрессионный тест доказывает дефект и защищён от изменения implementor;
- релевантные tests/typecheck/lint/build/coverage прошли либо точное ограничение зафиксировано как blocker;
- reviewer и architecture guardian дали approval для текущей revision;
- QA дал `pass`; conditional browser/security/contract gates также закрыты;
- документация, contracts, generated code и consumers синхронизированы;
- diff минимален, атомарен и не захватывает пользовательские изменения;
- при инфраструктуре DevOps и infrastructure reviewer закрыли GitOps gates;
- при deployment зафиксированы release identity, health, smoke и observation window либо честный `failed/blocked/rolled_back`.

В финальном `BugfixReport` перечисли симптом, root cause, исправление, regression proof, изменённые repositories/files, проверки и gates, Git/deployment status, известные риски и действия, требующие человека.
