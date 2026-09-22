# TaskAssessment и адаптивная команда

TaskAssessment обязателен как артефакт, но не как отдельный агент. Для очевидного Light/Standard route его выпускает Orchestrator; отдельный Task Assessor нужен только при неоднозначном, Full, cross-module/cross-repo или расширившемся scope. Несколько связанных fix-траншей остаются одним WorkItem, пока route, acceptance и frozen risk surface не изменились. Новое evidence сначала обрабатывается как delta; повторный полный assessment нужен только при изменении route-affecting полей из [coordination contract](coordination-efficiency.md).

## Решение

Сложность `small|medium|large` и риск `low|standard|critical` независимы. Размер diff не определяет риск.

| Mode | Критерий | Роли реализации после оценщика |
|---|---|---|
| light | small + low, обратимая правка без изменения поведения/данных/контрактов | Implementor; финальная проверка Orchestrator |
| standard | bounded дефект, включая локальный critical invariant без architecture/ownership/cross-repo изменения | Reproducer/Investigator по необходимости, Implementor, Reviewer; Test-maker, QA и specialist только по сигналу |
| full | large/multi-slice, неоднозначный RCA, архитектура, ownership/compatibility или cross-repo | Investigator, Reproducer, independent RCA review; Architect/Guardian и остальные gates только по изменённым concerns |

Security/auth/RBAC/tenant, money, data, migration, contract, concurrency, incident, GitOps и reliability требуют critical testing/concern gates, но не Full автоматически. Architecture, ownership/compatibility, cross-repo, large multi-slice scope или неоднозначный RCA требуют Full. Неизвестный риск → `needs_evidence`: одно ограниченное исследование; нерешённая семантика → `needs_input`. Light при неопределённости запрещён.

В bugfix full сохраняет triage/investigator/reproducer/RCA reviewer; light/standard исходную репродукцию и причину независимо проверяет Orchestrator перед правкой и после неё. Неподтверждённая причина требует rescope/усиления, не догадки.

## Формат

Последняя строка оценщика:

```text
WGC_AGENT_RESULT: {"role":"task-assessor","verdict":"assessed","phase":"","input_revision":"<SubagentStart revision>","task_assessment":{...}}
```

`task_assessment` содержит только поля:

- `mode`, `complexity`, `risk`, `test_disposition` (`add|update|reuse|none`);
- `domains`: sorted unique subset service/contracts/platform/ci/gitops;
- `risk_signals`: sorted unique subset security/money/data/migration/contract/concurrency/incident/gitops/architecture/cross-module/cross-repo/background-work/behavior/reliability;
- `checks`: sorted unique tags go-test-race/go-vet/golangci-lint/go-build/coverage/buf-lint/buf-breaking/buf-generate/work-sync/consumer/affected-matrix/image-build/vulnerability-scan/gitops-render/smoke; это минимум вместе с repository requirements;
- `assessed_paths`: 1–100 canonical exact `repository:relative/path`, без glob;
- `plan_revision`, `acceptance_revision`: bounded IDs исходного задания;
- `rationale`: до 500 символов; `evidence_refs`: 1–100 redacted IDs/путей до 200 символов, без raw logs/prompts;
- `assessment_revision`: SHA-256 от UTF-8 JSON остальных полей с `ensure_ascii=False, sort_keys=True, separators=(',', ':')`;

Downstream assignment фиксирует `assessment_revision` в ledger; marker привязывается через exact `input_revision` и `ASSIGNMENT_KEY`, поэтому не дублирует revision-поля без необходимости.

Для Light/Standard TestAssessment выпускает тот же assessment owner. Отдельный Test-maker сохраняется для regression `add/update` и protected critical invariants; Full использует его только после поддержанного RCA/FixPlan.

## Специалисты

- security → Security Reviewer; contract → Contract QA;
- data/migration → Data & Migration Reviewer;
- concurrency/reliability → Reliability Reviewer;
- gitops → DevOps и независимый Infrastructure Reviewer; доставка отдельно по exact approval.

Scope expansion, изменение acceptance/плана или новый риск требуют новой оценки только когда меняют route, domains, checks или boundaries. In-scope evidence и реализация сохраняют маршрут, но отменяют затронутые approvals/checks. Оценщик не может отменить safety floor. Старые verdicts не переходят в новую assessment revision. Независимость исполнения и review, тестов, architecture и infrastructure gates сохраняется.

## Проверка оркестратором

Light требует лично проверенного diff и alternative evidence. В финале на последней отдельной строке:

```text
WGC_ORCHESTRATOR_RESULT: {"assessment_revision":"<current>","input_revision":"<current workspace revision>","acceptance_verified":true,"evidence_refs":["<redacted evidence id>"]}
```

Для bugfix light/standard также `reproduced_before:true`, `reproduced_after:true`, `root_cause_reviewed:true`. Эти поля отражают реально проверенные артефакты; marker не заменяет доказательства или human approval.
