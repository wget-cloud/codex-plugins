# Wget Cloud Engineering Plugin

Один plugin bundle предоставляет четыре самостоятельных скилла и общий набор lifecycle hooks.

## Компоненты

| Компонент | Ответственность |
|---|---|
| `skills/wgc-task-creation` | product audit → business specification → dependency backlog → GitHub Project publication |
| `skills/wgc-epic-implementation` | Project scope → dependency waves → implementation/review/QA → status reconciliation |
| `skills/wgc-implementation` | planned architecture → adaptive TestAssessment → implementation → review → QA → optional GitOps/deployment |
| `skills/wgc-bugfix` | triage → evidence → reproduction → RCA → adaptive TestAssessment → minimal fix → review/QA → optional rollout |
| `hooks/hooks.json` | lifecycle event registration |
| `hooks/wgc_hooks.py` | workspace context, safety policy, privacy-safe state и profile-specific completion gates |
| `hooks/tests/` | end-to-end hook protocol tests через subprocess |

## Role contracts

В каждом скилле его локальный `references/agents/index.md` — единственный источник assignment envelope, model routing и registry. Каждая рабочая роль лежит в отдельном файле `references/agents/<role>.md`. Это позволяет оркестратору загружать только применимые роли и не смешивать permissions/verdicts четырёх профилей.

Каталог `skills/<name>/agents/` зарезервирован для Codex UI metadata (`openai.yaml`) и не содержит role prompts.

## Общие hooks

Hooks автоматически выбирают профиль `task-creation`, `epic-implementation`, `implementation` или `bugfix`, но role/verdict contract проверяется отдельно для активного профиля. State не хранит исходный prompt, GitHub Project URL, command text или tool output. Для Project-backed профилей hook требует структурированные product/project/operator gates, но фактические внешние изменения подтверждаются отдельным read-after-write. Direct Kubernetes/Helm/Argo mutations и destructive Git operations блокируются. Единственное mutating cluster-исключение — точный clean-cluster bootstrap; остальные approval markers блокируются fail-closed.

Hooks не валидируют model или reasoning effort: поля lifecycle events для этого ещё не установлены. Эти решения принадлежат локальному agent registry до запуска субагента.

Начиная с bundle `6.0.0`, hook-state имеет version `3`. Для implementation, bugfix и epic профилей Test-maker всегда возвращает `assessment_ready` и плоские поля `plan_revision`, `acceptance_revision`, `test_criticality`, `test_disposition` и `scope_fingerprint`. Disposition может быть `add`, `update`, `reuse` или `none`; `none` снимает только task-specific автоматический тест, но не repository/CI, typecheck, lint, build, generation, consumer, contract, security, GitOps, review или QA gates. Для `add/update` `TestPlan` обязан содержать непустые bounded exact runnable `commands`, `expected_baseline`, `actual_baseline`; exact canonical keyset `tests` совпадает с `protected_hashes`, каждый test file уже существует, а объявленный SHA-256 равен фактическому. Boolean/string handshake не заменяет hashes. Guardian `phase=plan` всегда связывает approval с exact текущим `plan_revision`; в epic marker также обязательны frozen `item_id`/`item_revision`. Result ledger ограничен 1000 записями, заменяет retry того же role/phase/item/input revision и никогда не выталкивает активные upstream gates. V2-state мигрируется с сохранением только совместимого privacy-safe non-test verification evidence; legacy `test`/`coverage` evidence и несовместимые test/review/QA gates сбрасываются. Повреждённый или переполненный state блокирует завершение до нового repository audit.

Epic-профиль дополнительно замораживает bounded максимум до 100 записей `selected_items` ledger из Project Manager marker. Каждый item содержит `item_id`, SHA-256 `item_revision`, `plan_revision`, `acceptance_revision` и `minimum_test_criticality`. Project Manager может передать три последних поля сразу либо ledger обогащается matching per-item Architect/Product markers до TestAssessment. Test-maker, Implementor, Reviewer, Architecture Guardian `phase=diff`, QA и Product Manager `phase=outcome` повторяют exact `item_id`/`item_revision`; aggregate verdict не закрывает другой item. Понижение criticality при прежнем `plan_revision` блокируется; новая plan revision инвалидирует assessment и прежний Guardian plan approval, а новый assessment разрешён только после повторного per-item approval. Неатрибутируемая docs/YAML/GitOps правка консервативно сбрасывает downstream gates всех items.

Role, result marker или token не предоставляют cluster permissions. Будущая mutating `kubectl` авторизация потребует exact task/environment/context/expiry/action contract, отдельного human approval и reviewed поддержки в hook; текущий runtime такой авторитетной семантики не предоставляет. После явно одобренного reinstall обновлённый hook проверяется только в новой задаче: уже активная задача продолжает старый hook runtime.

## Проверка bundle

```bash
make -C ../.. validate
```
