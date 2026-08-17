# Wget Cloud Engineering Plugin

Один plugin bundle предоставляет два самостоятельных скилла и общий набор lifecycle hooks.

## Компоненты

| Компонент | Ответственность |
|---|---|
| `skills/wgc-implementation` | planned architecture → tests → implementation → review → QA → optional GitOps/deployment |
| `skills/wgc-bugfix` | triage → evidence → reproduction → RCA → regression → minimal fix → review/QA → optional rollout |
| `hooks/hooks.json` | lifecycle event registration |
| `hooks/wgc_hooks.py` | workspace context, safety policy, privacy-safe state и profile-specific completion gates |
| `hooks/tests/` | end-to-end hook protocol tests через subprocess |

## Role contracts

В каждом скилле `references/agents/index.md` содержит assignment envelope и registry. Каждая рабочая роль лежит в отдельном файле `references/agents/<role>.md`. Это позволяет оркестратору загружать только применимые роли и не смешивать permissions/verdicts двух профилей.

Каталог `skills/<name>/agents/` зарезервирован для Codex UI metadata (`openai.yaml`) и не содержит role prompts.

## Общие hooks

Hooks автоматически выбирают профиль `implementation` или `bugfix`, но role/verdict contract проверяется отдельно для активного профиля. State не хранит исходный prompt, command text или tool output. Direct Kubernetes/Helm/Argo mutations и destructive Git operations блокируются. Fail-closed исключения существуют только для точного clean-cluster bootstrap, отдельно одобренной storage-only последовательности и самостоятельного семистадийного ingress-recovery контракта `twc-wise-finch`.

Ingress recovery привязан к annotated tag `twc-wise-finch-argocd-recovery-2026-08-17.1`, tag object `344a7e5f87e6c9212dd1ac22256336faad0eb002` и peeled commit `925f7a2949c6ff50b76e55ccec80abdfff59178b`. Семь стадий работают только в Argo core-mode, одним stable FD читают promotion manifest, нормализуют известные mechanical metadata и проверяют полный exact pre/post scope, включая future pending Applications и terminal historical operations как неактивные. Stage 1 выполняет time-bounded read-only convergence перед sync. Последовательность заканчивается на `argocd-public` и не разрешает поздние bundles `controllers`, `vault-restore`, `eso-ready`, `data`, `apps`, `full`. Promotion и router runners используют разные root-owned manifests (`promotion-manifest.json` и `router-manifest.json`). Source router manifest содержит только неисполняемый `approvalTemplate`: человек материализует fresh approval не старше 300 секунд с опубликованными foundation shapes, динамическими live identities и exact `TimewebRouterRecoveryPlan`. Production entrypoint читает manifest одним stable FD, исполняет все ordered adopt/create combinations и после final GET выдаёт `TimewebRouterRecoveryPoststate` в порядке HTTP/80, HTTPS/443 с новым `observedAt`; только published router/promotion digest lineage допускается в root-owned `router-gate.json`. Credential не попадает в Git/argv/env/log; kubeconfig и token доступны runner только через точный read-only ACL Darwin user `FFFFEEEE-DDDD-CCCC-BBBB-AAAA000001F5`. Publication, materialization, router/cluster mutation и deployment требуют отдельных human approvals. После явно одобренного reinstall обновлённый hook проверяется только в новой задаче: уже активная задача продолжает старый hook runtime.

## Проверка bundle

```bash
make -C ../.. validate
```
