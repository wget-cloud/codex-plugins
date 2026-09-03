---
name: wgc-implementation
description: Coordinate architecture-safe planned implementation work across the Wget Cloud frontend, backend microservices, shared front-lib, public sites, and Kubernetes GitOps repositories. Use for feature development, refactors, contracts, cross-repository changes, tests, reviews, QA, infrastructure preparation, rollout, or any planned task that benefits from specialized architect, architecture guardian, test-maker, implementor, reviewer, QA, DevOps, infrastructure reviewer, and deployment agents. For a user-reported defect, regression, failure, crash, or production incident that must be investigated and fixed, use wgc-bugfix instead. Do not use for a simple explanation or read-only question that needs no implementation workflow.
---

# WGC Implementation

Оркестратор владеет состоянием задачи и gate transitions; субагенты возвращают только назначенный артефакт и verdict.

## Preflight — первая операция

До чтения файлов, MCP и субагентов проверь `service_tier = "default"` и `[features].fast_mode = false`. При `fast|priority|ultrafast` прекрати запуск с `WGC_FAST_MODE_FORBIDDEN`; при отсутствующем или неоднозначном значении — `WGC_SERVICE_TIER_UNVERIFIABLE`. Внутренняя lane `economy` означает Luna/low и не является Codex Fast mode.

## Загрузить только нужный контекст

1. Прочитай корневой и затронутые вложенные `AGENTS.md`, затем обязательные README/architecture/business docs.
2. Прочитай [workflow](references/workflow.md), [test policy](references/test-assessment.md), [agent registry](references/agents/index.md) и [gates](references/artifacts-and-gates.md).
3. Role file открывай непосредственно перед назначением; conditional/downstream роли заранее не загружай.
4. Для CI, `k8s`, release или rollout прочитай [GitOps](references/gitops-and-deployment.md). [Hooks](references/hooks.md) читай только при блокировке или диагностике.

Проверь фактические manifests, execution paths, contracts/schema, tests, CI и Git status; документация не заменяет код.

## Инварианты

- Корень и submodules — отдельные repositories. Сохраняй пользовательские изменения; без отдельного основания не выполняй reset/checkout/rebase/merge/cleanup/pull.
- Commit, push, PR, merge, release и deployment требуют явного разрешения.
- Межсервисная orchestration принадлежит backend `orchestrator`; reusable browser contracts — `wget-cloud-front-lib`.
- Kubernetes меняется через GitOps source. Разрешённый clean-cluster bootstrap и deployment gates определены только в [GitOps](references/gitops-and-deployment.md).
- Каждая production-правка получает актуальный `TestAssessment`. Test-maker владеет тестами `add/update`; Implementor их не меняет.
- Guardian/reviewer/infrastructure reviewer read-only. QA не исправляет findings. Deployment agent не пишет код или manifests.
- Не объединяй независимые роли: implementor/reviewer, architect/guardian, DevOps/infrastructure reviewer.

## Глубина и pipeline

Выбери `small`, `standard`, `cross-repo` или `deployment` по риску и boundaries. Затем:

1. Зафиксируй `WorkItem`: цель, acceptance, exclusions, repos, risks, dirty baseline и deployment intent.
2. Architect строит DAG, contracts, compatibility, docs и minimum criticality; Guardian независимо одобряет plan revision.
3. Test-maker выпускает `assessment_ready` с `critical|standard|low` и `add|update|reuse|none`. Для `add/update` нужны exact commands, baseline и совпадающие SHA-256; `critical+none` запрещено.
4. Implementor выполняет один атомарный slice и prescribed checks. Оркестратор проверяет scope, diff и protected hashes.
5. Reviewer и Guardian проверяют текущую revision; затем QA проверяет boundary/error/auth/tenant/concurrency/offline/realtime по применимости.
6. Оркестратор повторяет ключевые checks, сверяет consumers/docs/commit boundaries и закрывает rework loops.
7. Без отдельного delivery approval верни отчёт. С approval следуй GitOps/release gates.

Точные transitions и invalidation rules находятся в [workflow](references/workflow.md).

## Субагенты

До spawn выбери route в [registry](references/agents/index.md), используй `FORK_TURNS: none` по умолчанию и не держи более трёх активных субагентов. Assignment обязан содержать exact task name, repository/path scope, upstream artifacts, local instructions, permissions/denials, expected evidence и output contract. Параллельные writers допустимы только в непересекающихся boundaries.

Оркестратор лично проверяет status/branch/upstream/remote, diffs до/после, critical commands, current revision и gate ledger. Отсутствие ответа не является approval. Первый stall — correction/rescope, повторный — interrupt и split/restart.

## Готовность

Готово только для текущей revision, когда acceptance доказана; TestAssessment актуален; prescribed и repository gates прошли либо имеют точный blocker; reviewer/guardian approved; QA pass; docs/contracts/generated consumers синхронизированы; diff атомарен и не захватывает чужую работу; применимые infrastructure/deployment gates закрыты.

Финальный отчёт: repositories/files, checks, verdicts, risks, Git/rollout status и действия человека.
