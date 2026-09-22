# TaskAssessment и адаптивная команда

TaskAssessment обязателен как компактный первый assignment и переиспользуется всеми slices, пока route, acceptance, risk surface и path boundaries не изменились. Он заменяет отдельные assessment/architect/test-planning роли для обычной работы и входит в общий лимит трёх назначений.

## Решение

Сложность `small|medium|large` и риск `low|standard|critical` независимы. Размер diff не определяет риск.

| Mode | Критерий | Роли реализации после оценщика |
|---|---|---|
| light | small + low, обратимая правка без изменения поведения/данных/контрактов | Implementor; targeted проверка Orchestrator |
| standard | bounded изменение, включая локальный critical invariant без architecture/ownership/cross-repo изменения | Implementor; Reviewer только для нетривиального risk/diff |
| full | large/multi-slice, архитектура, ownership/compatibility или cross-repo | один предварительный Architect только если Orchestrator не может заморозить решение; затем Implementor и максимум один Reviewer/specialist на slice |

Security/auth/RBAC/tenant, money, destructive data migration и public compatibility требуют точечной critical проверки, но не набора specialist gates и не Full автоматически. Для bounded contract/concurrency/reliability работы достаточно `RiskMatrix`, targeted test и одного подходящего Reviewer. Architecture, ownership/compatibility, cross-repo и large multi-slice scope требуют Full, но Full определяет планирование, а не автоматический состав команды. Plan и незатронутые approvals переиспользуются по selective invalidation.

В task-creation все режимы требуют Task Assessor, Product/Project/Auditor, отдельного Effort Estimator (SP), независимого Backlog Reviewer и Orchestrator; full добавляет Architect. Малый объём не отменяет продуктовую проработку. Operator нужен только для явно разрешённой записи. В epic Project scope/reconcile и truthful sync общие, остальная команда выбирается для каждого item; Product outcome остаётся per-item. В bugfix Full сам по себе не включает отдельную цепочку triage/investigator/reproducer/RCA reviewer: для incident или неоднозначной причины выбери один наиболее полезный root-cause concern в пределах бюджета. В light/standard исходную репродукцию и причину независимо проверяет Orchestrator перед правкой и после неё. Неподтверждённая причина требует rescope/усиления, не догадки.

## Формат

Последняя строка оценщика:

```text
WGC_AGENT_RESULT: {"role":"task-assessor","verdict":"assessed","phase":"","input_revision":"<SubagentStart revision>","task_assessment":{...}}
```

`task_assessment` содержит только поля:

- `mode`, `complexity`, `risk`, `test_disposition` (`add|update|reuse|none`);
- `domains`: sorted unique subset backend/frontend/site/front-lib/gitops;
- `risk_signals`: sorted unique subset security/money/data/migration/contract/concurrency/incident/gitops/architecture/cross-repo/browser/behavior/reliability;
- `checks`: sorted unique tags test/coverage/typecheck/lint/build/consumer/proto-gen/prisma/gitops-render/validate/browser/smoke/pack; это минимум вместе с repository requirements;
- `assessed_paths`: 1–100 canonical exact `repository:relative/path`, без glob;
- `plan_revision`, `acceptance_revision`: bounded IDs исходного задания;
- `rationale`: до 500 символов; `evidence_refs`: 1–100 redacted IDs/путей до 200 символов, без raw logs/prompts;
- `assessment_revision`: SHA-256 от UTF-8 JSON остальных полей с `ensure_ascii=False, sort_keys=True, separators=(',', ':')`;
- только epic: `item_id` и SHA-256 `item_revision` из frozen ledger.

Все downstream markers повторяют `assessment_revision`, epic — также item identity. Поля времени/планов в assignment — supervision, не разрешение объявить незавершённую задачу готовой.

Для implementation, epic и bugfix во всех modes оценщик добавляет sibling `assessment` с компактным TestAssessment по [test policy](test-assessment.md). Обычные `add/update` tests принадлежат Implementor. Отдельный Test-maker разрешён только когда assessment явно выбирает `test_ownership=protected_test_maker` для protected critical invariant; сам факт Full или bugfix не создаёт эту роль. В task-creation testing только provisional, execution assessment не нужен.

## Граница Architect

Назначай Architect только при реальном выборе service/module boundaries, ownership, public contracts, package/file map, invariants, compatibility, migration/cutover/rollback либо межмодульного slice DAG. Large/Full/долгая задача без такого решения не достаточна. Architect выпускает один компактный `ArchitecturePacket` на `architecture_revision`; все slices переиспользуют его, пока boundary не изменился. Architect не пишет production code, не исследует root cause, не выносит security verdict и не задаёт детальный function-level design.

Если несколько допустимых вариантов зависят от product semantics, стоимости миграции или предпочтения пользователя, Architect возвращает `DECISION_REQUIRED`, а не расходует medium на угадывание.

## Специалисты

Выбирай максимум одного специалиста по наиболее высокому риску; не превращай несколько risk signals в fanout ролей. Приоритет: security/money, data/migration, contract, concurrency/reliability, browser, incident, architecture/cross-repo. Исключение — явно разрешённый GitOps delivery, где независимость DevOps и Infrastructure Reviewer обязательна.

- security → Security Reviewer; contract → Contract QA;
- data/migration → Data & Migration Reviewer;
- concurrency/reliability → Reliability Reviewer;
- browser при standard/full → Browser QA;
- gitops → DevOps и независимый Infrastructure Reviewer; доставка отдельно по exact approval.

Scope expansion, изменение acceptance/плана или новый риск требуют новой оценки. In-scope реализация сохраняет маршрут, но отменяет затронутые approvals/checks. Оценщик не может отменить safety floor. Старые verdicts не переходят в новую assessment revision. Независимость исполнения и review, тестов, architecture и infrastructure gates сохраняется.

## Проверка оркестратором

Light требует лично проверенного diff и alternative evidence. В финале на последней отдельной строке:

```text
WGC_ORCHESTRATOR_RESULT: {"assessment_revision":"<current>","input_revision":"<current workspace revision>","acceptance_verified":true,"evidence_refs":["<redacted evidence id>"]}
```

Для bugfix light/standard также `reproduced_before:true`, `reproduced_after:true`, `root_cause_reviewed:true`. Эти поля отражают реально проверенные артефакты; marker не заменяет доказательства или human approval. В epic Light проверку приёмки дополнительно фиксирует per-item Product outcome; общий root marker не заменяет item gates.
