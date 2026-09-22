# Адаптивная политика тестирования bugfix

В обычном Light/Standard/Full bugfix Implementor пишет минимальный regression test вместе с fix и сам выполняет targeted проверку. Отдельный Test-maker выпускает `TestAssessment` и protected failing baseline только для заранее обозначенного critical invariant, когда независимость materially снижает риск. None/reuse assessment выпускает Orchestrator либо Task Assessor после проверенной причины. После изменения scope, RCA/FixPlan, acceptance, protected tests, contract/migration surface или production path вне `assessed_paths` assessment повторяется.

## Критичность

| Уровень | Критерий | Ожидание |
|---|---|---|
| `critical` | business rules; money; auth/RBAC/tenant/security; persisted data/migrations; public REST/gRPC/proto/export/event/WebSocket contracts; concurrency/retry/idempotency; Temporal/cron/queue/outbox/background work; серьёзная regression/incident; неизвестный риск | Максимально доказать original regression и изменённые positive/negative/boundary/security branches. `none` запрещён. |
| `standard` | Наблюдаемый дефект без critical-сигналов | Обычно `add`, `update` или `reuse`; `none` требует строгого исключения. |
| `low` | Только copy, spacing, theme или механическая правка без control flow, accessibility, responsive visibility, данных и contracts | `none` допустим с browser/visual/static evidence. |

Любой critical-сигнал побеждает; неопределённость требует limited evidence; до прояснения Light запрещён. Accessibility, keyboard/focus, responsive visibility, API, realtime и offline regression не считаются косметикой автоматически. Публичный `wget-cloud-front-lib` contract/export всегда `critical` и требует consumer proof.

Architect задаёт `minimum_test_criticality` и `plan_revision`; Test-maker может повысить уровень, и Architect может повысить floor при прежней revision. Понижение при той же revision блокируется: нужен новый evidence и новая FixPlan revision; она инвалидирует TestAssessment и прежний Guardian plan approval, а следующий assessment разрешён только после повторного approval.

## Disposition

- `reuse`: exact существующий тест доказывает исходный defect/invariant. `reuse_proof` содержит `test_id`, `test_path`, `invariant_mapping`, `successful_run: true`, актуальный `file_sha256`; для `critical` также `critical_branch_evidence` и успешный coverage evidence.
- `update`: полезный существующий regression test меняется под правильную семантику и защищается SHA-256.
- `add`: создаётся устойчивый failing-before/passing-after regression test и защищается SHA-256.
- `none`: task-specific автоматический тест не создаётся. `critical + none` запрещён; `standard + none` требует `rationale`, `disproportionate_cost: true`, непустые `stronger_alternative_evidence`, `residual_risks` и `follow_up`.

Formal `reproduction_waiver` разрешает `characterized` только при достаточном runtime evidence и failing CharacterizationTest. Он не отменяет TestAssessment: после approved RCA Architect, Guardian и Test-maker повторяют финальные gates. CharacterizationTest может стать `reuse` или `update`; waiver сам по себе никогда не оправдывает `none` для production fix.

## TestAssessment

Артефакт содержит `plan_revision`, `acceptance_revision`, `scope_fingerprint`, bounded exact `assessed_paths`, criticality/disposition, original regression и tested invariants, existing tests, `coverage_mode`, alternative evidence, residual risks/follow-up и disposition-specific proof. `add/update` создают условный `TestPlan` с matching action, непустыми bounded exact runnable `commands`, `expected_baseline`, `actual_baseline`, exact test paths и `protected_hashes`: canonical keysets обязаны точно совпадать, каждый файл уже существует, а объявленный SHA-256 равен фактическому. Boolean/string handshake hashes не заменяет. `reuse` содержит полный `reuse_proof`. `none` содержит только evidence plan и не создаёт искусственный test commit.

`none` не отменяет фактические repository/CI gates и targeted reproduction. Однако Reviewer, Architecture Guardian, QA и conditional specialists не становятся обязательными только из-за bugfix: каждый требует конкретного risk signal. Coverage выше существующего repository threshold не наращивается ради этого workflow.

## Машинный marker Test-maker

```text
WGC_AGENT_RESULT: {"role":"test-maker","verdict":"assessment_ready","phase":"","input_revision":"<exact-input-revision>","plan_revision":"<revision>","acceptance_revision":"<revision>","test_criticality":"<critical|standard|low>","test_disposition":"<add|update|reuse|none>","scope_fingerprint":"<fingerprint>","assessed_paths":["<exact path>"],"tested_invariants":["<regression/invariant>"],"existing_tests":["<test id/path>"],"coverage_mode":"<mode>","alternative_evidence":["<evidence>"],"residual_risks":["<risk>"]}
```

Добавь `reuse_proof` либо `rationale`, `disproportionate_cost`, `stronger_alternative_evidence`, `follow_up`. Nested `assessment` поддерживается только для migration compatibility.

## State v4 и invalidation

V2/v3 мигрируются в v4 с сохранением безопасного baseline и сбросом прежних approvals/verification: нужна новая TaskAssessment. Повреждённый state требует repository audit. Scope expansion отменяет маршрут. In-scope write сохраняет маршрут, но отменяет затронутые проверки и approvals. Contract/migration/test изменения сохраняют прежние строгие TestAssessment invalidation rules.

## Владелец в v7

Во всех execution modes TestAssessment выпускает Task Assessor вместе с TaskAssessment. Обычные add/update принадлежат Implementor; `protected_test_maker` выбирается только для явно защищённого critical baseline. В task-creation политика provisional. [Команда](task-assessment.md), [повторное использование проверок](verification.md).
