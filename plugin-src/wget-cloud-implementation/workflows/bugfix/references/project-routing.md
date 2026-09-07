# Маршрутизация по Wget Cloud

Карта помогает выбрать owner, но текущий код, `AGENTS.md`, contracts и tests остаются source of truth.

| Симптом | Начальный owner | Обязательные проверки границы |
|---|---|---|
| Back-office page/form/table/state | `frontend` | RTK Query/SWR/Axios/fetch path, auth, shared front-lib, API response |
| Public storefront/PWA/SEO/offline | `wget-cloud-site` | Next.js server/client boundary, Serwist cache, storefront API, front-lib version |
| Общий тип/component/site block/widget | `wget-cloud-front-lib` | public exports, backward compatibility, оба consumer проекта |
| HTTP/WebSocket 4xx/5xx/mapping | `backend` gateway | guards, transport mapping, downstream gRPC status, request IDs |
| Доменный invariant/data mutation | соответствующий backend service | application/domain/infrastructure, tenant/RBAC, Prisma transaction, events |
| Межсервисный долгий процесс | backend `orchestrator` + activities owner | Temporal workflow/activity versioning, retries, idempotency, compensation |
| Deploy/config/secret wiring/rollout | `k8s` | Helm values, Argo Application, External Secrets, immutable image identity |

## Repository boundary

Корень `/Users/estev/wc/wgetcloud` координирует пять самостоятельных Git submodules: `frontend`, `backend`, `wget-cloud-front-lib`, `wget-cloud-site`, `k8s`. Для каждого затронутого проекта отдельно проверь:

```bash
git -C <project> status -sb
git -C <project> remote -v
git -C <project> branch -vv
```

Не считай изменение gitlink production fix. Сначала исправляется и при разрешении публикуется submodule commit, затем отдельным commit обновляется parent gitlink. Detached HEAD, dirty tree, divergence или локальные commits должны быть явно отражены в BugCase/Report.

## Backend

- Найди ingress point в gateway, фактический gRPC contract, application handler и infrastructure adapter.
- Доменные сервисы владеют своими данными и invariants; межсервисная координация принадлежит `orchestrator`.
- Для proto/schema изменений включай generated artifacts и проверяй producers/consumers.
- Для Prisma/data bug проверь tenant predicate, transaction boundary, uniqueness, migrations и rollback/compatibility.
- Для Temporal bug проверь deterministic workflow rules, activity idempotency, retry policy, timeout и versioning.

## Frontend

- Не предполагай чистую FSD: проверь legacy imports и реальную data-fetch цепочку.
- Раздели server truth, RTK Query/SWR cache, local component state и realtime update.
- Для auth/RBAC дефекта backend enforcement обязателен; скрытие UI не является исправлением доступа.
- Для race/stale state проверь request cancellation, optimistic update, tag invalidation, WebSocket ordering и remount.

## Front-lib и site

- Общий браузерный контракт исправляй в `wget-cloud-front-lib`, application-specific поведение — в consumer.
- Публичный export или runtime protocol требует compatibility check и согласования версий consumers.
- В site проверь Next.js server/client rendering, cache/revalidation, PWA service worker и environment-specific base URL.

## Kubernetes/GitOps

- Desired state находится в `k8s`; application repos не выполняют ручные cluster mutations.
- Сначала найди Argo/Helm ownership и overlays/values конкретного environment.
- Секреты задаются через Vault/External Secrets; plaintext secret не добавлять.
- Runtime drift может объяснить symptom, но исправляется Git change после review и approval.
