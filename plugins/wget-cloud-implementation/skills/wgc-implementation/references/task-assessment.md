# TaskAssessment и адаптивная команда

TaskAssessment обязателен как артефакт. В task-creation и epic отдельный Task Assessor остаётся обязательным; в implementation/bugfix очевидный Light/Standard assessment выпускает Orchestrator, а отдельный агент нужен только для неоднозначного, Full, cross-repo или расширившегося scope. Несколько slices одной задачи/item переиспользуют assessment, пока route, acceptance, risk surface и path boundaries не изменились.

## Решение

Сложность `small|medium|large` и риск `low|standard|critical` независимы. Размер diff не определяет риск.

| Mode | Критерий | Роли реализации после оценщика |
|---|---|---|
| light | small + low, обратимая правка без изменения поведения/данных/контрактов | Implementor; финальная проверка Orchestrator |
| standard | bounded изменение, включая локальный critical invariant без architecture/ownership/cross-repo изменения | Implementor + Reviewer; Test-maker/QA/specialist только по точечному signal |
| full | large/multi-slice, архитектура, ownership/compatibility или cross-repo | Architect + Guardian plan; Implementor + Reviewer; остальные gates только по изменённым concerns |

Security/auth/RBAC/tenant, money, data, migration, contract, concurrency, incident, GitOps и reliability требуют critical testing/concern gates, но не Full автоматически. Architecture, ownership/compatibility, cross-repo и large multi-slice scope требуют Full. Plan и незатронутые specialist approvals переиспользуются по selective invalidation. Неизвестный риск → `needs_evidence`; нерешённая семантика → `needs_input`. Light при неопределённости запрещён.

В task-creation все режимы требуют Task Assessor, Product/Project/Auditor, отдельного Effort Estimator (SP), независимого Backlog Reviewer и Orchestrator; full добавляет Architect. Малый объём не отменяет продуктовую проработку. Operator нужен только для явно разрешённой записи. В epic Project scope/reconcile и truthful sync общие, остальная команда выбирается для каждого item; Product outcome остаётся per-item. В bugfix full сохраняет triage/investigator/reproducer/RCA reviewer; light/standard исходную репродукцию и причину независимо проверяет Orchestrator перед правкой и после неё. Неподтверждённая причина требует rescope/усиления, не догадки.

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

Для light/standard оценщик добавляет sibling `assessment` с полноценным TestAssessment по [test policy](test-assessment.md). Его paths, risk и disposition совпадают с TaskAssessment. При implementation/epic standard `add/update` он задаёт `test_ownership=implementor`, exact invariants/paths/commands, но не пишет тесты. Bugfix сохраняет независимый Test-maker для `add/update`; Full critical/protected assessment также выпускает отдельный Test-maker. В task-creation testing только provisional, execution assessment не нужен.

## Специалисты

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
