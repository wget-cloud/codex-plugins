# TaskAssessment и адаптивная команда

Отдельный Task Assessor обязателен для нового WorkItem. Несколько траншей одного service migration остаются одним WorkItem, пока route, acceptance и frozen risk surface не изменились: не запускай нового оценщика на каждый RPC family. Оркестратор передаёт цель, acceptance, Git baseline и минимальный scoped context. Оценщик read-only; он не становится исполнителем или reviewer собственной работы. Новое evidence в том же WorkItem сначала обрабатывается как delta: повторный полный assessment нужен только при изменении route-affecting полей, перечисленных в [coordination contract](coordination-efficiency.md).

## Решение

Сложность `small|medium|large` и риск `low|standard|critical` независимы. Размер diff не определяет риск.

| Mode | Критерий | Роли реализации после оценщика |
|---|---|---|
| light | small + low, обратимая правка без изменения поведения/данных/контрактов | Implementor; финальная проверка Orchestrator |
| standard | ограниченное изменение поведения без critical/architecture/cross-repo | Implementor, Reviewer, QA; Test-maker только add/update |
| full | large, архитектура, cross-repo или critical | Service-level Architect + Guardian plan один раз; на транш Implementor + Reviewer; Test-maker, Guardian diff, QA и специалисты только по critical/изменённым concerns |

Security/auth/RBAC/tenant, money, data, migration, contract, concurrency, incident, GitOps и reliability требуют critical/full. Architecture и cross-repo требуют full. Full означает строгий набор применимых gates, а не обязательный новый агент на каждый файл или повтор всех gates после любого diff. Service-level plan и неизменившиеся specialist approvals переиспользуются по selective invalidation. Неизвестный риск → `needs_evidence`: одно ограниченное исследование; нерешённая семантика → `needs_input`. Не запускать полный штат автоматически из-за нехватки контекста. Light при неопределённости запрещён.

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

Все downstream markers повторяют `assessment_revision`. Поля времени/планов в assignment — supervision, не разрешение объявить незавершённую задачу готовой.

Для light/standard `none|reuse` оценщик добавляет sibling `assessment` с полноценным TestAssessment по [test policy](test-assessment.md). Его paths, risk и disposition совпадают с TaskAssessment. Для `add/update` и full оценщик не пишет тесты: отдельный Test-maker выпускает TestAssessment.

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
