# GitOps и deployment

## Содержание

- Неподвижные ограничения
- Актуальная k8s модель
- Подготовка desired state
- Infrastructure review
- Human approval
- Публикация и наблюдение
- Failure и rollback
- Checklist

## Неподвижные ограничения

Wget Cloud управляет Kubernetes через GitOps. Git repository содержит желаемое состояние, Argo CD применяет его. Ни один агент этого workflow не исправляет cluster state вручную. Для нового пустого кластера допускается только минимальный fixed-point bootstrap ниже; после создания root все изменения снова выполняются исключительно через GitOps.

Запрещены write operations, включая:

- `kubectl apply`, `edit`, `patch`, `delete`, `scale`, `rollout restart`, `set image`;
- `helm install/upgrade/uninstall` против управляемого кластера;
- ручное создание/изменение Secret, ConfigMap, Deployment, Job или Argo Application;
- изменение live state «временно», даже если обещан последующий commit;
- plaintext secret/token/key в Git, diff, logs или отчёте;
- mutable release identity вроде floating `latest`.

### Единственное bootstrap-исключение

Bootstrap разрешён только когда read-only preflight подтвердил отсутствие управляющего Argo root, опубликованный `k8s` revision immutable, infrastructure review относится к этой revision и человек одобрил exact kubeconfig/context/actions. Root, Argo makefile и values должны байт-в-байт совпадать с blobs этой revision. Каждый mutating command начинается с `WGC_GITOPS_BOOTSTRAP_APPROVED=1` и содержит explicit kubeconfig/context; shell expansion/redirection запрещены.

Разрешён ровно такой порядок:

1. Установить repo-defined Argo CD release/chart/version/values в namespace `argocd` с `--wait` и repository timeout.
2. Создать exact `wget-cloud-k8s-repository` Secret pipeline: manifest генерируется client-side, SSH private key читается только из file path, local label равен `argocd.argoproj.io/secret-type=repository`, затем единственный stdin применяется в `argocd`. Key нельзя выводить или передавать inline.
3. Применить exact `infrastructure/k8s/bootstrap/roots/<context>.yaml`, если Application name/path/context согласованы, а `targetRevision` — immutable SHA или датированный release tag.

Другие values/flags, второй root, `argocd app sync`, workload apply, secret edit, repair и DNAT этим исключением не разрешены. После bootstrap агент только read-only наблюдает Argo; sync/rollout выполняется отдельным одобренным GitOps этапом. Временный key file удаляется после подтверждения repository access.

### Семантическая авторизация kubectl

Для любой будущей mutating `kubectl` операции вне clean-cluster bootstrap необходим структурированный `KUBECTL_AUTHORIZATION` с exact `task`, `environment`, `context`, `expires_at`, `action_mode` и отдельным явным human approval. Текущие runtime role/authorization данные не являются авторитетными, поэтому такой mutating `kubectl` сегодня недоступен. Role name, actor metadata, `WGC_AGENT_RESULT`, marker и token сами по себе ничего не разрешают. Поддержка возможна только отдельным reviewed изменением hook, role contracts и tests; до него используется GitOps.

Read-only команды `kubectl get/describe/logs/events`, Argo status/history, CI/registry/metrics/health queries допустимы deployment agent только в утверждённом environment.

## Актуальная k8s модель

Перед работой прочитай текущие `k8s/README.md`, `infrastructure/k8s/docs/ARCHITECTURE.md`, profiles, component README/values, local chart и validation scripts.

Проверенная 2026-08-13 структура:

```text
infrastructure/k8s/
  bootstrap/                    # root/bootstrap Argo resources
  profiles/                     # lifecycle + enabled bundles
  gitops/clusters/              # generated/committed Argo composition
  components/                   # environment/application desired state
  charts/                       # local Helm charts
  docs/
  scripts/                      # renderer/validators/runtime checks
  tests/
  legacy/                       # archive only
```

`profiles/dev.yaml` активен. Production profile в исследованной версии в основном planned/disabled; его наличие не означает production readiness. Renderer генерирует cluster root composition, включая `gitops/clusters/dev/root/profile.generated.yaml`. Source и требуемый generated output должны оставаться синхронными.

Bundle order использует Argo sync waves. В исследованной dev profile последовательность шла от core (`-50`) и data (`-30/-25`) к apps (`-10`), monitoring (`-5`), observability (`0`), analytics (`5`), delivery (`10`) и dev-tools (`20`). Не копируй номера вслепую: сверяй текущий profile. Особенно проверяй, что prune policy для stateful/data ownership может быть отключена.

Application values обычно находятся под environment components:

```text
components/environments/dev/apps/backend/services/<service>/values.yaml
components/environments/dev/apps/backend/services/<service>/worker.yaml
components/environments/dev/apps/frontend/dev/values.yaml
components/environments/dev/apps/sites/<site>/dev/values.yaml
```

Локальные charts `nest-service`, `nest-worker-service`, `next-js-service` определяют naming, runtime secret contract, probes, resources, telemetry и container args. Backend workers — отдельные workloads. External Secrets/Vault references являются secret boundary.

## Подготовка desired state

DevOps получает approved application plan и формирует `DeploymentPlan`:

1. **Release identity.** Repository, exact commit, image repository, immutable tag и по возможности digest. Не угадывать image, если CI ещё не создал его.
2. **Environment lifecycle.** Убедиться, что target profile active и component owner существует. Planned/disabled profile требует отдельной архитектурной задачи.
3. **Ownership.** Найти текущий Argo Application/component/chart/values owner. Не создавать второй owner того же Kubernetes resource.
4. **Dependencies/sync.** Зафиксировать namespaces, data/secrets/controllers, migrations, service/worker order и sync waves/hooks.
5. **Runtime contract.** Ports, container args, environment name, runtime Secret/ExternalSecret, service discovery, ingress/TLS/DNS и config keys.
6. **Health/safety.** Startup/readiness/liveness probes, rolling strategy, replicas/autoscaling, PDB, resources, disruption/capacity constraints.
7. **Observability.** OTEL metadata, metrics/service monitors, logs, alerts/dashboards и release correlation.
8. **Migration.** Backward-compatible expand/contract, idempotent job, retry/timeout, ordering и rollback limitations. Destructive migration не прячется в обычный rollout.
9. **Rollback.** Previous immutable image/config revision, Git revert path и data compatibility.

DevOps изменяет только необходимый Git source и generated output. Он запускает штатные команды, обычно:

```bash
make gitops-render
make validate
```

Добавляй более узкие `gitops-validate`, `resource-validate`, `gitops-test`, telemetry/runtime checks или Helm rendering в зависимости от diff. Всегда сверяй текущий Makefile.

DevOps не push-ит. Его terminal artifact — `InfrastructureChangeReport(prepared)`.

## Infrastructure review

Infrastructure reviewer получает immutable k8s diff и validation output. Он независимо проверяет:

- source/generated consistency и determinism renderer;
- отсутствие правок `legacy/` как runtime source;
- один Argo owner на resource и корректный destination/namespace/project;
- sync wave/dependency и отсутствие циклов;
- prune/self-heal последствия, особенно для data/stateful resources;
- immutable image и связь с application commit;
- ExternalSecret/Vault references без plaintext secret;
- ports, Service, ingress, TLS, DNS и NetworkPolicy;
- probes, graceful termination, rolling strategy, resources, PDB/autoscaling;
- migration ordering, idempotency и rollback/data compatibility;
- metrics/logs/traces/alerts и доступность smoke endpoint;
- честное соответствие environment lifecycle.

Review не ограничивается YAML syntax. Он обязан оценить runtime semantics. `make validate` с exit code 0 не заменяет review.

При `changes_requested` diff возвращается DevOps, затем renderer/validation и весь infrastructure review повторяются.

## Human approval

Deployment agent можно активировать только если пользователь:

- изначально явно запросил deployment в конкретное environment, либо
- после готовности задачи дал отдельный approval.

Перед запросом approval оркестратор показывает:

```yaml
repository: <application and/or k8s repo>
branch: <branch>
commit: <exact sha>
environment: <dev/stage/prod>
image: <immutable tag and digest if available>
delivery_action: <push/merge/trigger>
infrastructure_review: approved
checks: <summary>
rollback: <Git-based strategy>
known_risks: []
```

Approval действителен только для этого набора. Новый commit, force update, другой image или environment требуют нового approval. Общая фраза «можно деплоить» не разрешает force-push, merge в другую branch или production, если это не следует однозначно из контекста.

Commit/push application repositories и k8s repository также подчиняются локальным Git правилам. Не создавать root gitlink на неопубликованный submodule commit.

## Публикация и наблюдение

Deployment agent выполняет только явно разрешённый delivery action и строит evidence chain:

```text
approved commit
  → CI run
  → immutable image tag/digest
  → GitOps commit
  → Argo observed revision
  → Sync status
  → Health status
  → workload rollout
  → smoke checks
  → observation window
```

### Проверки до push

- branch/upstream/remote и exact HEAD совпадают с approval;
- worktree не содержит незакоммиченного scope, который может попасть в публикацию;
- protected branch/PR policy понятна;
- image/GitOps dependency order соблюдён;
- infrastructure review относится к тому же k8s diff.

### Наблюдение CI и registry

- дождаться required checks/build/security scan;
- подтвердить, что image создан из одобренного commit;
- зафиксировать immutable tag/digest;
- не подменять failed pipeline локальной ручной сборкой без нового плана/approval.

### Наблюдение Argo и Kubernetes

Read-only наблюдение должно различать:

- Argo operation phase;
- sync status и observed revision;
- application health;
- Deployment/StatefulSet/Job rollout;
- pod readiness/restarts;
- warning events;
- migration job status;
- logs/metrics/traces и error-rate/latency;
- ingress/public health и feature smoke.

Не считать `Synced` достаточным: revision может быть синхронизирован, но unhealthy. Не считать `Healthy` достаточным: функциональный smoke может падать. Не считать один HTTP 200 доказательством отсутствия delayed/backend errors.

### Ожидание

Если rollout/CI длится, агент ждёт в bounded intervals, сообщает пользователю изменения состояния и не создаёт шум одинаковыми snapshots. Observation window выбирается по риску: быстрый stateless dev rollout короче, migration/background/realtime change дольше. В отчёте всегда указываются фактические timestamps и signals.

## Failure и rollback

При failure deployment agent:

1. Прекращает продвижение следующих environments.
2. Фиксирует exact release/revision и первую наблюдаемую ошибку.
3. Собирает read-only evidence: CI, Argo, rollout, events, logs, metrics, health/smoke.
4. Классифицирует вероятную область без самовольного исправления: application, image/build, config/secret, migration, capacity, ingress/network, external dependency.
5. Сообщает impact, affected environment и residual uncertainty.
6. Предлагает Git-based rollback или forward fix.

Rollback — новая управляемая операция:

- создать revert/change в source repository;
- пройти tests/review и infrastructure review в применимой мере;
- получить approval для exact rollback commit/environment/image;
- дать Argo reconciler применить desired state;
- наблюдать rollback и выполнить smoke.

Прямой `kubectl rollout undo`, ручной image swap или secret edit запрещён. Если инцидент требует emergency procedure вне GitOps, агент останавливается и явно передаёт решение человеку; skill не расширяет полномочия автоматически.

## Checklist

### DevOps готовность

- [ ] Target profile действительно active.
- [ ] Owner Application/component/chart найден.
- [ ] Image immutable и связан с approved application commit.
- [ ] Secrets только через approved external references.
- [ ] Probes/ports/args/runtime config согласованы с app.
- [ ] Resources/replicas/autoscaling/PDB и capacity проверены.
- [ ] Sync wave/prune/migration безопасны.
- [ ] Observability и smoke endpoint определены.
- [ ] Renderer и validators прошли; generated output синхронен.
- [ ] Infrastructure reviewer approved exact diff.

### Deployment готовность

- [ ] Human approval содержит exact commit/branch/environment/image/action.
- [ ] Approval всё ещё соответствует HEAD и k8s diff.
- [ ] Required Git permissions/action явно разрешены.
- [ ] CI и image provenance подтверждены.
- [ ] Argo observed expected revision.
- [ ] Sync и health успешны.
- [ ] Workloads/migrations готовы, restarts/events приемлемы.
- [ ] Logs/metrics не показывают новую ошибку.
- [ ] Feature smoke прошёл.
- [ ] Observation window завершено.
- [ ] Rollback path и residual risks отражены в отчёте.
