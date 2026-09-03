# Wget Cloud Engineering Plugin

Bundle содержит четыре самостоятельных skill и общие lifecycle hooks.

| Skill | Назначение |
|---|---|
| `wgc-task-creation` | audit/specification → dependency backlog → GitHub Project |
| `wgc-epic-implementation` | Project scope → waves → implementation/review/QA → reconciliation |
| `wgc-implementation` | planned change → TestAssessment → implementation → review/QA → optional delivery |
| `wgc-bugfix` | reproduction/RCA → TestAssessment → minimal fix → review/QA → optional rollout |

В каждом skill `references/agents/index.md` хранит assignment envelope, model routing и ссылки на отдельные role contracts. Role file загружается только перед назначением. `agents/openai.yaml` содержит UI metadata, не role prompts.

## Runtime policy

WGC skills работают только при `service_tier = "default"` и `[features].fast_mode = false`. Hooks fail-closed отклоняют Fast/priority/ultrafast и непроверяемую конфигурацию до активации workflow. Model lane `economy` использует `gpt-5.6-luna/low` и не связана с Codex Fast mode; `balanced` использует Terra/medium, `frontier` — Sol/high. Одновременно допускается максимум три субагента, `FORK_TURNS` по умолчанию `none`.

## Hooks

`hooks/wgc_hooks.py` выбирает профиль, фиксирует privacy-safe state, добавляет границы субагентам, блокирует destructive Git/direct cluster mutations и проверяет completion gates. Hook не заменяет role verdict, human approval, read-after-write и проверку diff оркестратором.

State version 3 хранит bounded structured gates и SHA-256 protected tests, но не raw prompt, command output, logs или credentials. Повреждённый state требует нового repository audit. Kubernetes меняется только через GitOps; deployment authority всегда привязана к exact revision/environment/image.

## Проверка и установка

```bash
make -C ../.. validate
codex plugin add wget-cloud-implementation@wget-cloud
```

После публикации smoke выполняется в новой задаче: активная задача продолжает использовать загруженную cache-версию. Проверяются manifest version и lifecycle hooks без warning/error; cache активной задачи не удаляется.
