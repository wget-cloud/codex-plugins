# Адаптивная политика тестирования epic

Для каждого frozen epic item TestAssessment выбирает `add | update | reuse | none` и `test_ownership: implementor | protected_test_maker | n/a`. Light/Standard assessment выпускает Task Assessor; обычные item-local tests пишет Implementor. Full critical/protected assessment выпускает отдельный Test-maker. Aggregate assessment или verdict одного item не переносится на другой.

## Критичность

| Уровень | Критерий | Ожидание |
|---|---|---|
| `critical` | business/money; auth/RBAC/tenant/security; data/migrations; public REST/gRPC/proto/export/event/WebSocket contracts; concurrency/retry/idempotency; Temporal/cron/queue/outbox; серьёзная regression/incident; неизвестный риск | Максимальное доказательство изменённых positive/negative/boundary/security branches; `none` запрещён. |
| `standard` | Наблюдаемое поведение без critical-сигналов | Обычно `add/update/reuse`; `none` — строгое исключение. |
| `low` | Только copy/spacing/theme/docs/mechanical change без control flow, accessibility, responsive visibility, данных и contracts | Возможен `none` с visual/browser/static evidence. |

Critical-сигнал побеждает, неопределённость требует limited evidence; до прояснения Light запрещён. Accessibility, keyboard/focus, responsive visibility, API, realtime/offline не косметика автоматически. Публичный `wget-cloud-front-lib` export/contract всегда `critical` и требует consumer proof.

Architect задаёт минимум для каждого item. Test-maker может повысить его; criticality floor разрешено повысить при прежнем `plan_revision`, но понижение требует нового evidence и новой per-item plan revision. Новая plan revision инвалидирует assessment и прежний Guardian plan approval; следующий TestAssessment разрешён только после повторного per-item Architecture Guardian approval.

## Disposition и schema

- `reuse`: `reuse_proof` с exact `test_id`, `test_path`, `invariant_mapping`, `successful_run: true`, текущим `file_sha256`; для critical — `critical_branch_evidence` и coverage evidence.
- `update`: critical/protected test меняет Test-maker; обычный test — Implementor.
- `add`: critical/protected regression/acceptance test создаёт Test-maker; обычный test — Implementor.
- `none`: нет task-specific автоматического теста. `critical + none` запрещён. `standard + none` требует `rationale`, `disproportionate_cost: true`, непустые `stronger_alternative_evidence`, `residual_risks`, `follow_up`.

Каждый `TestAssessment` содержит `item_id`, SHA-256 `item_revision`, `plan_revision`, `acceptance_revision`, `scope_fingerprint`, bounded exact `assessed_paths`, criticality/disposition/ownership, invariants/scenarios, existing tests, `coverage_mode`, alternative evidence, residual risks и disposition-specific proof. `TestPlan` при `add/update` содержит matching action, commands, expected/actual baseline и exact paths; `protected_test_maker` требует existing files и matching hashes, `implementor` — отсутствие protected hashes. `reuse/none` используют `test_ownership=n/a`.

`none` не отменяет CI/repository thresholds, typecheck, lint, build, proto/Prisma, consumer/contract/security/GitOps, review или QA. Около 80% — только необязательный ориентир для noncritical measurable code, не CI floor.

## Frozen item ledger и markers

Project Manager `phase=scope` замораживает bounded список до 100 entries:

```text
WGC_AGENT_RESULT: {"role":"project-manager","verdict":"planned","phase":"scope","input_revision":"<exact-input-revision>","selected_items":[{"item_id":"<id>","item_revision":"<sha256>","plan_revision":"<plan-revision>","acceptance_revision":"<acceptance-revision>","minimum_test_criticality":"<critical|standard|low>"}]}
```

Test-maker marker плоский:

```text
WGC_AGENT_RESULT: {"role":"test-maker","verdict":"assessment_ready","phase":"","input_revision":"<exact-input-revision>","item_id":"<id>","item_revision":"<sha256>","plan_revision":"<revision>","acceptance_revision":"<revision>","test_criticality":"<critical|standard|low>","test_disposition":"<add|update|reuse|none>","test_ownership":"<implementor|protected_test_maker|n/a>","scope_fingerprint":"<fingerprint>","assessed_paths":["<exact path>"],"tested_invariants":["<invariant>"],"existing_tests":["<test id/path>"],"coverage_mode":"<mode>","alternative_evidence":["<evidence>"],"residual_risks":["<risk>"]}
```

Если Project Manager ещё не знает все три revision/floor значения, matching per-item Architect marker добавляет `plan_revision`/`minimum_test_criticality`, а Product Manager `phase=scope` — `acceptance_revision`; TestAssessment запрещён, пока item не содержит все три поля. Global revision/floor не используется как fallback. Implementor, Reviewer и применимые Guardian diff/QA/Product outcome повторяют exact item identity. Hooks требуют только risk-applicable gates для каждого item.

## State v4 и invalidation

V2/v3 мигрируются в v4 с сохранением безопасного baseline и сбросом прежних approvals/verification: нужна новая TaskAssessment. Повреждённый state требует repository audit. Scope expansion отменяет маршрут. In-scope write сохраняет маршрут, но отменяет затронутые проверки и approvals. Contract/migration/test изменения сохраняют прежние строгие TestAssessment invalidation rules.

## Владелец в v7

В Light/Standard TestAssessment выпускает Task Assessor вместе с TaskAssessment; add/update используют `test_ownership=implementor`. Full floor принадлежит Architect, а critical/protected add/update — Test-maker. В task-creation политика provisional. [Команда](task-assessment.md), [повторное использование проверок](verification.md).
