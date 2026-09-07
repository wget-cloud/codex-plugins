# Wget Cloud Engineering Plugin

Версия 7.0.0 содержит четыре самостоятельных skill, адаптивные команды и общие lifecycle hooks.

| Skill | Назначение |
|---|---|
| `wgc-task-creation` | audit/specification → dependency backlog → GitHub Project |
| `wgc-epic-implementation` | Project scope → waves → implementation/review/QA → reconciliation |
| `wgc-implementation` | planned change → TestAssessment → implementation → review/QA → optional delivery |
| `wgc-bugfix` | reproduction/RCA → TestAssessment → minimal fix → review/QA → optional rollout |

В каждом skill `references/agents/index.md` хранит assignment envelope, model routing и ссылки на отдельные role contracts. Role file загружается только перед назначением. `agents/openai.yaml` содержит UI metadata, не role prompts.

## Runtime policy

WGC skills работают только при `service_tier = "default"` и `[features].fast_mode = false`. Hooks отклоняют Fast/priority/ultrafast и непроверяемую конфигурацию. Все агенты наследуют модель и reasoning effort чата; overrides при spawn опускаются. GPT-6 не требует отдельной ветки конвейера. Priority-only инструмент означает blocker, настройки пользователя не меняются. Одновременно допускается максимум три субагента, `FORK_TURNS` по умолчанию `none`.

## Команды и профили

Отдельный Task Assessor выбирает сложность, риск, domains, tests и required gates. Light использует одного Implementor и проверку Orchestrator; Standard — Implementor/Reviewer/QA и Test-maker при add/update; Full — архитектурные и test gates плюс специалисты по сигналам. Security, данные, миграции, контракты, concurrency, incident и GitOps не допускают Light. В epic оценка и gates принадлежат каждому item; Product outcome и Project reconciliation сохраняются.

Backend, Frontend, Site, Front-lib и GitOps — профили знаний внутри процессов, не новые skills. Data & Migration Reviewer и Reliability Reviewer дополняют существующие Browser QA, Security Reviewer и Contract QA. Domain profile не расширяет permissions роли. Новые тесты защищают конкретный invariant; existing evidence переиспользуется до релевантного изменения.

## Исходники и сборка

Редактируй `../../plugin-src/wget-cloud-implementation`, затем запускай `make -C ../.. skills-build`. Общие roles/policies/domains и workflow-specific части собираются по explicit `composition.json`. Каждый published skill автономен. `build_wgc_skills.py --check` ничего не пишет, отклоняет drift, неожиданные файлы, коллизии и выход за разрешённые пути. CI проверяет сборку и standalone links.

## Hooks

`hooks/wgc_hooks.py` выбирает профиль, фиксирует privacy-safe state, добавляет границы субагентам, блокирует destructive Git/direct cluster mutations и проверяет completion gates. Hook не заменяет role verdict, human approval, read-after-write и проверку diff оркестратором.

State version 4 хранит bounded TaskAssessment, structured gates, SHA-256 protected tests и metadata проверок, но не raw prompt, command output, logs или credentials. V2/v3 baseline сохраняется, старые approvals/verification сбрасываются; нужна новая оценка. Повреждённый state требует нового repository audit. Scope expansion, changed acceptance/plan и новые риски требуют переоценки. Kubernetes меняется только через GitOps; deployment authority всегда привязана к exact revision/environment/image.

`hooks/runtime/` разделяет verdict contracts, task/team policy, migration state и evidence metadata; `wgc_hooks.py` остаётся lifecycle adapter и владельцем существующих destructive-command checks. Проверка фактической семантики, неизвестных зависимостей и внешнего окружения остаётся обязанностью Orchestrator/Reviewer: hooks не являются полноценным sandbox для агентов и не доказывают качество по одному marker.

## Проверка и установка

```bash
make -C ../.. validate
codex plugin add wget-cloud-implementation@wget-cloud
```

После публикации smoke выполняется в новой задаче: активная задача продолжает использовать загруженную cache-версию. Проверяются manifest version и lifecycle hooks без warning/error; cache активной задачи не удаляется.
