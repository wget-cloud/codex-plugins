# Адаптивная политика тестирования bugfix

Test-maker обязателен для каждого bugfix и после approved RCA/FixPlan выпускает `TestAssessment` с disposition `add | update | reuse | none`. Новый regression test обычно наиболее полезен, но не создаётся формально, если уже существует точное доказательство или тест действительно непропорционален риску. После изменения scope, RCA/FixPlan, acceptance, tests, contract/migration surface или production path вне `assessed_paths` assessment повторяется.

## Критичность

| Уровень | Критерий | Ожидание |
|---|---|---|
| `critical` | business rules; money; auth/RBAC/tenant/security; persisted data/migrations; public REST/gRPC/proto/export/event/WebSocket contracts; concurrency/retry/idempotency; Temporal/cron/queue/outbox/background work; серьёзная regression/incident; неизвестный риск | Максимально доказать original regression и изменённые positive/negative/boundary/security branches. `none` запрещён. |
| `standard` | Наблюдаемый дефект без critical-сигналов | Обычно `add`, `update` или `reuse`; `none` требует строгого исключения. |
| `low` | Только copy, spacing, theme или механическая правка без control flow, accessibility, responsive visibility, данных и contracts | `none` допустим с browser/visual/static evidence. |

Любой critical-сигнал побеждает; сомнение означает `critical`. Accessibility, keyboard/focus, responsive visibility, API, realtime и offline regression не считаются косметикой автоматически. Публичный `wget-cloud-front-lib` contract/export всегда `critical` и требует consumer proof.

Architect задаёт `minimum_test_criticality` и `plan_revision`; Test-maker может повысить уровень, и Architect может повысить floor при прежней revision. Понижение при той же revision блокируется: нужен новый evidence и новая FixPlan revision; она инвалидирует TestAssessment и прежний Guardian plan approval, а следующий assessment разрешён только после повторного approval.

## Disposition

- `reuse`: exact существующий тест доказывает исходный defect/invariant. `reuse_proof` содержит `test_id`, `test_path`, `invariant_mapping`, `successful_run: true`, актуальный `file_sha256`; для `critical` также `critical_branch_evidence` и успешный coverage evidence.
- `update`: полезный существующий regression test меняется под правильную семантику и защищается SHA-256.
- `add`: создаётся устойчивый failing-before/passing-after regression test и защищается SHA-256.
- `none`: task-specific автоматический тест не создаётся. `critical + none` запрещён; `standard + none` требует `rationale`, `disproportionate_cost: true`, непустые `stronger_alternative_evidence`, `residual_risks` и `follow_up`.

Formal `reproduction_waiver` разрешает `characterized` только при достаточном runtime evidence и failing CharacterizationTest. Он не отменяет TestAssessment: после approved RCA Architect, Guardian и Test-maker повторяют финальные gates. CharacterizationTest может стать `reuse` или `update`; waiver сам по себе никогда не оправдывает `none` для production fix.

## TestAssessment

Артефакт содержит `plan_revision`, `acceptance_revision`, `scope_fingerprint`, bounded exact `assessed_paths`, criticality/disposition, original regression и tested invariants, existing tests, `coverage_mode`, alternative evidence, residual risks/follow-up и disposition-specific proof. `add/update` создают условный `TestPlan` с matching action, непустыми bounded exact runnable `commands`, `expected_baseline`, `actual_baseline`, exact test paths и `protected_hashes`: canonical keysets обязаны точно совпадать, каждый файл уже существует, а объявленный SHA-256 равен фактическому. Boolean/string handshake hashes не заменяет. `reuse` содержит полный `reuse_proof`. `none` содержит только evidence plan и не создаёт искусственный test commit.

`none` не отменяет repository/CI suites, coverage thresholds, typecheck, lint, build, proto/Prisma, consumer/contract/security/GitOps gates, reproduction, RCA review, Reviewer, Architecture Guardian, QA или conditional Browser/Security/Contract QA. Backend 90%+ thresholds сохраняются; около 80% не является новым floor.

## Машинный marker Test-maker

```text
WGC_AGENT_RESULT: {"role":"test-maker","verdict":"assessment_ready","phase":"","input_revision":"<exact-input-revision>","plan_revision":"<revision>","acceptance_revision":"<revision>","test_criticality":"<critical|standard|low>","test_disposition":"<add|update|reuse|none>","scope_fingerprint":"<fingerprint>","assessed_paths":["<exact path>"],"tested_invariants":["<regression/invariant>"],"existing_tests":["<test id/path>"],"coverage_mode":"<mode>","alternative_evidence":["<evidence>"],"residual_risks":["<risk>"]}
```

Добавь `reuse_proof` либо `rationale`, `disproportionate_cost`, `stronger_alternative_evidence`, `follow_up`. Nested `assessment` поддерживается только для migration compatibility.

## State v3 и invalidation

V2 migration сохраняет privacy-safe successful verification tags/hashes и сбрасывает legacy test/review/QA gates. Malformed state блокирует completion до нового repository audit/reactivation. In-scope production write сохраняет assessment/test-maker gate, но инвалидирует diff approvals и старые test/coverage results; out-of-scope, contract/migration или реально изменённый protected test инвалидируют assessment. Fingerprinted reuse test сохраняется только при прежнем SHA-256.
