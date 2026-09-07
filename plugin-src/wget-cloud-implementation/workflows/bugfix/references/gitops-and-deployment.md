# GitOps и deployment bugfix

## Разделение полномочий

- Implementor исправляет application source.
- DevOps изменяет только Git-источник desired state в `k8s`/CI scope.
- Infrastructure reviewer независимо проверяет infra diff.
- Человек разрешает commit/push/PR/merge/release/deployment в требуемой гранулярности.
- Deployment agent публикует только явно разрешённую revision и наблюдает доставку; код и manifests он не пишет.

Ни одна из ролей не выполняет `kubectl apply/edit/patch/delete/scale`, ручной `helm upgrade`, прямое изменение Argo Application или secret в кластере. Единственное исключение — fixed-point bootstrap пустого кластера: после exact human approval marker `WGC_GITOPS_BOOTSTRAP_APPROVED=1` разрешает только repo-defined Argo chart/version/values, file-backed `wget-cloud-k8s-repository` credential pipeline и exact immutable `bootstrap/roots/<context>.yaml` с explicit kubeconfig/context. Это исключение нельзя использовать для bugfix, incident repair, Argo sync или workload mutation. Read-only диагностика допустима при наличии доступа и узкого scope.

Для любой будущей mutating `kubectl` операции вне clean-cluster bootstrap необходим структурированный `KUBECTL_AUTHORIZATION` с exact `task`, `environment`, `context`, `expires_at`, `action_mode` и отдельным явным human approval. Текущие runtime role/authorization данные не являются авторитетными, поэтому такой mutating `kubectl` сегодня недоступен. Role name, actor metadata, `WGC_AGENT_RESULT`, marker и token сами по себе ничего не разрешают. Поддержка возможна только отдельным reviewed изменением hook, role contracts и tests; до него применяется GitOps.

## DevOps plan

До изменения `k8s` DevOps устанавливает:

- owning Argo Application/Helm chart/values/overlay;
- target environment/namespace/workload;
- immutable image digest или однозначный tag policy;
- config/secret ownership и External Secrets/Vault path без чтения secret value;
- rollout strategy, probes, resources, migration/job ordering;
- observability queries, smoke и rollback/forward-fix plan.

Manifest diff должен быть минимальным. Не добавлять plaintext secret, `latest`, environment-specific ручные исключения или drift, который Git не воспроизводит.

## Infrastructure review

Проверить:

- Helm render/schema/lint и Argo composition;
- namespace, labels/selectors, service/ingress и dependency ordering;
- ExternalSecret references без secret material;
- probes, disruption, resource requests/limits и rollout safety;
- database migration compatibility и rollback limitations;
- observability и smoke критерии;
- соответствие существующему style и ownership `k8s` repo.

## Human approval contract

Перед deployment оркестратор показывает:

- repositories и commits/PRs;
- target environment;
- immutable application image identity и infra revision;
- миграции/необратимые действия;
- ожидаемый blast radius и downtime;
- smoke, observation window и rollback plan.

Approval «делай задачу» или «исправь баг» не является deployment approval. Approval должен относиться к показанным revision/environment; изменение diff требует нового approval.

## Deployment sequence

1. Проверить clean/expected Git state и что разрешённая revision доступна remote.
2. Выполнить только разрешённый push/PR/merge/release шаг.
3. Зафиксировать CI/build result и immutable image identity.
4. Наблюдать Argo sync/health и Kubernetes rollout read-only.
5. Проверить pods/restarts/events/probes и scoped error-rate/log evidence.
6. Выполнить regression smoke, включая исходный bug scenario, tenant/RBAC checks при необходимости.
7. Наблюдать согласованное окно; security/tenant smoke выполнять только на synthetic canary tenants и обезличенных fixtures; не объявлять успех сразу после `Ready`.
8. Выпустить `DeploymentReport` с `deployed_healthy | failed | rolled_back | blocked`.

## Failure

Не чинить drift вручную. При failure:

- зафиксировать failing release identity, время и redacted evidence;
- остановить дальнейшее продвижение;
- оценить rollback safety и запросить разрешение, если оно не было заранее выдано;
- выполнить Git revert или forward fix через обычные review gates;
- после любого изменения повторить infra review, deployment approval, rollout и smoke.

Rollback не равен успешному bugfix: итоговый статус должен отражать, что исправление не доставлено.
