---
name: wgc-implementation
description: Coordinate architecture-safe planned implementation work across the Wget Cloud frontend, backend microservices, shared front-lib, public sites, and Kubernetes GitOps repositories. Use for feature development, refactors, contracts, cross-repository changes, tests, reviews, QA, infrastructure preparation, rollout, or any planned task that benefits from specialized architect, architecture guardian, test-maker, implementor, reviewer, QA, DevOps, infrastructure reviewer, and deployment agents. For a user-reported defect, regression, failure, crash, or production incident that must be investigated and fixed, use wgc-bugfix instead. Do not use for a simple explanation or read-only question that needs no implementation workflow.
---

# WGC Implementation

Организуй задачу как управляемый конвейер специализированных агентов. Главный агент остаётся оркестратором: он владеет состоянием задачи, назначает работу, проверяет границы изменений и единолично переводит задачу между этапами. Субагенты выдают артефакты и verdict, но не принимают решение о завершении или деплое.

## Сначала загрузить контекст

1. Полностью прочитай корневой `AGENTS.md`, затем `AGENTS.md` каждого затронутого проекта. Вложенные инструкции имеют приоритет.
2. Прочитай README и обязательную архитектурную/бизнес-документацию затронутых проектов до планирования изменений.
3. Прочитай [project-map.md](references/project-map.md). Это карта, проверенная 2026-08-13, а не замена текущему коду и локальным инструкциям.
4. Прочитай [workflow.md](references/workflow.md), [agent registry](references/agents/index.md) и [artifacts-and-gates.md](references/artifacts-and-gates.md). Файл роли открывай непосредственно перед её назначением; downstream-роли не загружай заранее.
5. Если затронуты `k8s`, CI/CD, release или rollout, дополнительно полностью прочитай [gitops-and-deployment.md](references/gitops-and-deployment.md).
6. Lifecycle hooks плагина автоматически добавляют workspace-контекст, safety checks и completion reminders. При блокировке или диагностике прочитай [hooks.md](references/hooks.md).

Не полагайся на запомненную структуру: проверь фактические package manifests, точки входа, contracts/schema, тесты, CI и текущий Git status.

## Неподвижные правила

- Рассматривай корень и пять submodules как отдельные Git-репозитории. Не смешивай их commits, ветки или историю.
- Сохраняй пользовательские изменения. Не делай reset, checkout, rebase, merge, cleanup, pull или массовое переключение веток без отдельного основания и разрешения.
- Не создавай commit, push, PR, merge, release или deployment, если пользователь явно этого не разрешил. Разрешение на реализацию не означает разрешение на публикацию.
- Вся межсервисная orchestration принадлежит backend-сервису `orchestrator`; доменные сервисы предоставляют activities и собственные инварианты.
- Переиспользуемый браузерный код и публичные TypeScript-контракты принадлежат `wget-cloud-front-lib`; application-specific код остаётся в потребителе.
- Kubernetes изменяется строго GitOps: DevOps правит только Git-источник желаемого состояния. Никаких `kubectl apply/edit/patch/delete/scale`, прямого Helm upgrade или ручного исправления кластера.
- Production-код нельзя считать законченным без немедленной проверки актуальности тестов и покрытия изменённых веток.
- Implementor не изменяет тесты, созданные или защищённые test-maker. Любое изменение такого теста возвращается test-maker и заново проходит gate.
- Architecture guardian, reviewer и infrastructure reviewer ничего не пишут. QA не исправляет найденные дефекты.
- Deployment agent не пишет код или манифесты. Он активируется только при явном запросе на deployment либо после отдельного человеческого approval, привязанного к commit, environment и image digest/tag.

## Выбрать глубину процесса

Используй минимальный процесс, сохраняющий независимость проверок:

- `small`: один проект, локальная правка, низкий риск. Architect и test-maker могут быть короткими отдельными проходами; обязательны implementor, reviewer и architecture guardian. QA выполняет целевой smoke/exploratory check.
- `standard`: feature, refactor или contract change. Используй полный основной конвейер. Для дефекта с неизвестной причиной переключись на `$wgc-bugfix`.
- `cross-repo`: несколько репозиториев, публичный контракт, schema/proto, shared library или rollout dependency. Architect строит DAG и delivery order; каждый репозиторий имеет отдельные gates и commit boundary.
- `deployment`: добавь DevOps, infrastructure reviewer, human gate, deployment agent и наблюдение rollout.

Не создавай субагента ради формальности. Но не объединяй роли, которым нужна независимость: implementor не может быть reviewer, architect не может быть architecture guardian, DevOps не может быть infrastructure reviewer.

## Выполнить workflow

1. **Intake.** Сформируй `WorkItem`: цель, критерии приёмки, exclusions, затронутые repositories, риски, требования к deployment и текущие dirty changes.
2. **Reconnaissance.** Параллельно исследуй независимые проекты read-only explorer-агентами. Оркестратор сам проверяет ключевые факты и объединяет отчёты.
3. **Design.** Architect выдаёт implementation DAG, contracts, migration/compatibility plan, test strategy, documentation и rollout order.
4. **Architecture gate.** Architecture guardian независимо проверяет план. При `changes_requested` верни его architect; не переходи к тестам или коду.
5. **Test baseline.** Test-maker фиксирует executable acceptance/regression tests там, где test-first применим, и список защищённых файлов с хешами. Если новый интерфейс ещё невозможно скомпилировать, он создаёт согласованную failing baseline или точную test specification и завершает тесты сразу после появления минимального контракта.
6. **Implementation.** Implementor выполняет одну атомарную часть DAG, не трогая защищённые тесты. После каждого логического изменения обновляет только разрешённую документацию и запускает минимальные релевантные проверки с coverage.
7. **Integrity check.** Оркестратор сравнивает фактический diff со scope, хеши защищённых тестов и отсутствие чужих изменений. Нарушение границ отклоняет результат независимо от passing tests.
8. **Independent review.** Reviewer и architecture guardian независимо проверяют готовый diff; для независимых областей запускай их параллельно. Все blocking findings возвращаются соответствующему автору, затем проверки повторяются полностью.
9. **QA.** После code review QA пытается сломать функцию через boundary, error, authorization, tenant, concurrency, offline/realtime и regression scenarios. QA сообщает воспроизводимые дефекты, но не исправляет их.
10. **Integration.** Оркестратор запускает расширенные проверки, сверяет contracts/consumers, документацию и атомарность репозиториев. Только после всех обязательных `approved/pass` состояние становится `ready`.
11. **Delivery.** Без deployment заверши отчётом и оставь публикацию пользователю. При deployment следуй отдельному GitOps-конвейеру и [gitops-and-deployment.md](references/gitops-and-deployment.md).

Подробные переходы, rework loops и разрешённая параллельность описаны в [workflow.md](references/workflow.md).

## Управлять агентами

Перед созданием каждого агента передай ему:

- конкретный task slice и разрешённые repositories/paths;
- прочитанные локальные инструкции и необходимые ссылки на source of truth;
- входные артефакты предыдущего gate;
- список разрешённых действий и явных запретов;
- обязательный формат результата из [artifacts-and-gates.md](references/artifacts-and-gates.md).

Используй отдельные role contracts из [agent registry](references/agents/index.md) без ослабления запретов. Параллельные write-агенты допустимы только на непересекающихся repository/path scopes. Никогда не разрешай двум агентам одновременно писать в один репозиторий или общий contract boundary.

Оркестратор обязан сам:

- проверить `git status -sb`, branch/upstream и remote каждого затронутого репозитория;
- проверить diff до и после работы write-агента;
- сопоставить каждый изменённый файл с утверждённым scope;
- повторить критичные команды, не доверяя только текстовому заявлению агента;
- вести gate ledger и не интерпретировать отсутствие ответа как approval;
- сообщать пользователю о существенной неопределённости, существующем dirty state, недоступной проверке или необходимом разрешении.

## Использовать lifecycle hooks

Hooks являются механическими guardrails, а не заменой ролей и gates:

- не обходи `PreToolUse` denial; выбери безопасный GitOps/Git путь или запроси изменение policy;
- учитывай дополнительный context от `SessionStart`, `SubagentStart` и `PostToolUse`, но самостоятельно сверяй факты;
- после одноразового продолжения от `Stop` закрой недостающие проверки либо явно зафиксируй точный blocker;
- не считай hook-tracker доказательством review или QA — verdicts остаются отдельными агентными артефактами;
- `PreToolUse` не получает надёжную роль субагента, поэтому защищённые тесты окончательно контролируются оркестратором по allowlist, diff и SHA-256, а hook только предупреждает об их изменении.

Подробное поведение, ограничения и команда self-test находятся в [hooks.md](references/hooks.md).

## Условие готовности

Задача готова только когда выполнены все применимые условия:

- критерии приёмки имеют доказательства;
- test-maker подтвердил тестовый контракт, защищённые тесты не изменены implementor;
- релевантные tests/typecheck/lint/build/coverage прошли либо конкретное ограничение явно зафиксировано;
- reviewer дал `approved` без blocking findings;
- architecture guardian подтвердил соответствие архитектуре и стилю каждого проекта;
- QA дал `pass` или все найденные дефекты прошли полный rework loop;
- документация, contracts, generated code и consumers синхронизированы;
- каждый repository diff атомарен и не захватывает пользовательские изменения;
- при инфраструктуре infrastructure reviewer дал `approved`;
- при deployment подтверждены rollout health, smoke и observation window; либо честно зафиксирован статус `failed/blocked/rolled_back`, а не «успешно».

В финальном отчёте перечисли изменённые repositories/files, выполненные проверки, gate verdicts, известные риски, Git/rollout status и действия, требующие человека.
