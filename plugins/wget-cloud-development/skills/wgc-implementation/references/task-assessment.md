# TaskAssessment и адаптивная команда

TaskAssessment обязателен как артефакт, но не как отдельный агент. Для очевидного Light/Standard route его выпускает Orchestrator; отдельный Task Assessor нужен только при неоднозначном, Full, cross-module/cross-repo или расширившемся scope. Несколько траншей одного service migration остаются одним WorkItem, пока route, acceptance и frozen risk surface не изменились. Новое evidence сначала обрабатывается как delta; повторный полный assessment нужен только при изменении route-affecting полей из [coordination contract](coordination-efficiency.md).

## Решение

Сложность `small|medium|large` и риск `low|standard|critical` независимы. Размер diff не определяет риск.

| Mode | Критерий | Роли реализации после оценщика |
|---|---|---|
| light | small + low, обратимая правка без изменения поведения/данных/контрактов | Implementor; targeted проверка Orchestrator |
| standard | bounded изменение, включая локальный critical invariant без architecture/ownership/cross-repo изменения | Implementor; Reviewer только для нетривиального risk/diff |
| full | large/multi-slice, архитектура, ownership/compatibility или cross-repo | Architect только если Orchestrator не может заморозить решение; затем Implementor и максимум один Reviewer/specialist на транш |

Security/auth/RBAC/tenant, money, destructive data migration и public compatibility требуют точечной critical проверки, но не набора specialist gates. Для bounded contract/concurrency/reliability работы достаточно `RiskMatrix`, targeted test и одного подходящего Reviewer. Full определяет планирование, а не автоматический состав команды.

В bugfix Full сам по себе не включает отдельную цепочку triage/investigator/reproducer/RCA reviewer: для incident или неоднозначной причины выбери один наиболее полезный root-cause concern в пределах бюджета. В light/standard исходную репродукцию и причину независимо проверяет Orchestrator перед правкой и после неё. Неподтверждённая причина требует rescope/усиления, не догадки.

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

Для Light/Standard TestAssessment выпускает тот же assessment owner. Обычные implementor-owned `add/update` tests не требуют отдельного Test-maker; он нужен только для protected critical invariants. Full использует отдельного Test-maker только когда independence действительно требуется.

## Граница Architect

Назначай Architect только при выборе service/module boundaries, ownership, public contracts, package/file map, invariants, compatibility, migration/cutover/rollback либо межмодульного DAG. Large/Full/долгая задача без такого решения не достаточна. Architect выпускает один `ArchitecturePacket` на `architecture_revision` и переиспользуется до изменения boundary. Он не пишет production code, не выполняет RCA/security verdict и не задаёт function-level design. При material alternative верни root `DECISION_REQUIRED`.

## Специалисты

Выбирай максимум одного специалиста по наиболее высокому риску; не превращай несколько risk signals в fanout ролей. Исключение — явно разрешённый GitOps delivery, где независимость DevOps и Infrastructure Reviewer обязательна.

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
