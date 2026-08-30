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

В каждом скилле его локальный `references/agents/index.md` — единственный источник assignment envelope, model routing и registry. Каждая рабочая роль лежит в отдельном файле `references/agents/<role>.md`. Это позволяет оркестратору загружать только применимые роли и не смешивать permissions/verdicts двух профилей.

Каталог `skills/<name>/agents/` зарезервирован для Codex UI metadata (`openai.yaml`) и не содержит role prompts.

## Общие hooks

Hooks автоматически выбирают профиль `implementation` или `bugfix`, но role/verdict contract проверяется отдельно для активного профиля. State не хранит исходный prompt, command text или tool output. Direct Kubernetes/Helm/Argo mutations и destructive Git operations блокируются. Единственное mutating cluster-исключение — точный clean-cluster bootstrap; остальные approval markers блокируются fail-closed.

Hooks не валидируют model или reasoning effort: поля lifecycle events для этого ещё не установлены. Эти решения принадлежат локальному agent registry до запуска субагента.

Role, result marker или token не предоставляют cluster permissions. Будущая mutating `kubectl` авторизация потребует exact task/environment/context/expiry/action contract, отдельного human approval и reviewed поддержки в hook; текущий runtime такой авторитетной семантики не предоставляет. После явно одобренного reinstall обновлённый hook проверяется только в новой задаче: уже активная задача продолжает старый hook runtime.

## Проверка bundle

```bash
make -C ../.. validate
```
