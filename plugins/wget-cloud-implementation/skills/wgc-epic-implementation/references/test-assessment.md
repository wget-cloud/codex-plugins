# Адаптивная политика тестирования epic

Test-maker обязателен отдельно для каждого frozen epic item. Новый test не обязателен: Test-maker выпускает per-item `TestAssessment` и выбирает `add | update | reuse | none`. Aggregate assessment или verdict одного item не переносится на другой.

## Критичность

| Уровень | Критерий | Ожидание |
|---|---|---|
| `critical` | business/money; auth/RBAC/tenant/security; data/migrations; public REST/gRPC/proto/export/event/WebSocket contracts; concurrency/retry/idempotency; Temporal/cron/queue/outbox; серьёзная regression/incident; неизвестный риск | Максимальное доказательство изменённых positive/negative/boundary/security branches; `none` запрещён. |
| `standard` | Наблюдаемое поведение без critical-сигналов | Обычно `add/update/reuse`; `none` — строгое исключение. |
| `low` | Только copy/spacing/theme/docs/mechanical change без control flow, accessibility, responsive visibility, данных и contracts | Возможен `none` с visual/browser/static evidence. |

Critical-сигнал побеждает, сомнение означает `critical`. Accessibility, keyboard/focus, responsive visibility, API, realtime/offline не косметика автоматически. Публичный `wget-cloud-front-lib` export/contract всегда `critical` и требует consumer proof.

Architect задаёт минимум для каждого item. Test-maker может повысить его; criticality floor разрешено повысить при прежнем `plan_revision`, но понижение требует нового evidence и новой per-item plan revision. Новая plan revision инвалидирует assessment и прежний Guardian plan approval; следующий TestAssessment разрешён только после повторного per-item Architecture Guardian approval.

## Disposition и schema

- `reuse`: `reuse_proof` с exact `test_id`, `test_path`, `invariant_mapping`, `successful_run: true`, текущим `file_sha256`; для critical — `critical_branch_evidence` и coverage evidence.
- `update`: Test-maker меняет полезный существующий test и защищает его SHA-256.
- `add`: Test-maker создаёт устойчивый regression/acceptance test и защищает SHA-256.
- `none`: нет task-specific автоматического теста. `critical + none` запрещён. `standard + none` требует `rationale`, `disproportionate_cost: true`, непустые `stronger_alternative_evidence`, `residual_risks`, `follow_up`.

Каждый `TestAssessment` содержит `item_id`, SHA-256 `item_revision`, `plan_revision`, `acceptance_revision`, `scope_fingerprint`, bounded exact `assessed_paths`, criticality/disposition, invariants/scenarios, existing tests, `coverage_mode`, alternative evidence, residual risks и disposition-specific proof. `TestPlan` создаётся только при `add/update`: matching action, непустые bounded exact runnable `commands`, `expected_baseline`, `actual_baseline`, exact test paths и `protected_hashes` с идентичным canonical keyset, существующими файлами и фактически совпавшими SHA-256; для feature/refactor baseline описывает отсутствующий/падающий invariant и наблюдённый результат. Handshake hashes не заменяет. `reuse/none` не создают искусственный test commit.

`none` не отменяет CI/repository thresholds, typecheck, lint, build, proto/Prisma, consumer/contract/security/GitOps, review или QA. Около 80% — только необязательный ориентир для noncritical measurable code, не CI floor.

## Frozen item ledger и markers

Project Manager `phase=scope` замораживает bounded список до 100 entries:

```text
WGC_AGENT_RESULT: {"role":"project-manager","verdict":"planned","phase":"scope","input_revision":"<exact-input-revision>","selected_items":[{"item_id":"<id>","item_revision":"<sha256>","plan_revision":"<plan-revision>","acceptance_revision":"<acceptance-revision>","minimum_test_criticality":"<critical|standard|low>"}]}
```

Test-maker marker плоский:

```text
WGC_AGENT_RESULT: {"role":"test-maker","verdict":"assessment_ready","phase":"","input_revision":"<exact-input-revision>","item_id":"<id>","item_revision":"<sha256>","plan_revision":"<revision>","acceptance_revision":"<revision>","test_criticality":"<critical|standard|low>","test_disposition":"<add|update|reuse|none>","scope_fingerprint":"<fingerprint>","assessed_paths":["<exact path>"],"tested_invariants":["<invariant>"],"existing_tests":["<test id/path>"],"coverage_mode":"<mode>","alternative_evidence":["<evidence>"],"residual_risks":["<risk>"]}
```

Если Project Manager ещё не знает все три revision/floor значения, matching per-item Architect marker добавляет `plan_revision`/`minimum_test_criticality`, а Product Manager `phase=scope` — `acceptance_revision`; TestAssessment запрещён, пока item не содержит все три поля. Global revision/floor не используется как fallback. Implementor, Reviewer, Architecture Guardian `phase=diff`, QA и Product Manager `phase=outcome` также повторяют exact `item_id`/`item_revision`. Для каждого item hooks требуют отдельные `test-maker`, `implementor`, `reviewer`, `architecture`, `qa`, `product-outcome` gates.

## State v3 и invalidation

V2 migration сохраняет только совместимые privacy-safe non-test verification tags/hashes; legacy `test`/`coverage` evidence и несовместимые test/review/QA gates сбрасываются. Malformed state блокирует completion до repository audit/reactivation. In-scope production write сохраняет assessment/test-maker gate и инвалидирует diff approvals/старые test results. Out-of-scope, contract/migration и changed protected test инвалидируют affected assessment/downstream; fingerprinted reuse test сохраняется только при совпавшем SHA-256. Изменение frozen item revision требует нового Project Manager scope ledger и всех per-item gates.
