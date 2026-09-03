# Адаптивная политика тестирования

Test-maker обязателен для каждой implementation-задачи, но новый тест не является обязательным результатом. До production implementation он выпускает `TestAssessment`, выбирая `add | update | reuse | none`; после изменения scope, плана, acceptance, тестов, contract/migration surface или production path вне `assessed_paths` assessment повторяется.

## Критичность

| Уровень | Критерий | Ожидание |
|---|---|---|
| `critical` | business rules; money; auth/RBAC/tenant/security; persisted data/migrations; public REST/gRPC/proto/export/event/WebSocket contracts; concurrency/retry/idempotency; Temporal/cron/queue/outbox/background work; серьёзная regression/incident; неизвестный или неоднозначный риск | Максимально доказать изменённые positive/negative/boundary/security branches. `none` запрещён. |
| `standard` | Наблюдаемое поведение без critical-сигналов | Обычно `add`, `update` или `reuse`; `none` — только формальное исключение. |
| `low` | Только copy, spacing, theme, docs или механическая правка без control flow, accessibility, responsive visibility, данных и contracts | Допустим `none` с browser/visual/static evidence. |

Любой critical-сигнал побеждает остальные признаки; сомнение означает `critical`. Accessibility, focus/keyboard, responsive visibility, API, realtime и offline behavior не являются косметикой автоматически. Публичный export/type/runtime protocol `wget-cloud-front-lib` всегда `critical` и требует consumer evidence.

Architect указывает `minimum_test_criticality` и `plan_revision`. Test-maker может повысить уровень, и Architect может повысить floor при прежней revision. Понижение при той же `plan_revision` блокируется: нужен новый evidence и новая plan revision; она инвалидирует TestAssessment и прежний Guardian plan approval, а следующий assessment разрешён только после повторного approval.

## Disposition

- `reuse`: существующий тест прямо доказывает изменяемый invariant. `reuse_proof` обязан содержать exact `test_id`, `test_path`, `invariant_mapping`, `successful_run: true`, актуальный `file_sha256`; для `critical` также `critical_branch_evidence` и успешный coverage evidence.
- `update`: существующий полезный тест должен отражать новую семантику. Test-maker обновляет его и защищает SHA-256.
- `add`: новый устойчивый тест даёт реальную regression value. Test-maker создаёт его и защищает SHA-256.
- `none`: task-specific автоматический тест не создаётся. `critical + none` запрещён. `standard + none` требует одновременно `rationale`, `disproportionate_cost: true`, непустые `stronger_alternative_evidence`, `residual_risks` и `follow_up`.

Для сдвига логотипа на 5 px типичный результат — `low/none`: заданный viewport, browser/visual smoke, screenshot и дешёвые static checks. Это не разрешает пропускать обязательные repository suites.

## TestAssessment

Артефакт содержит:

- `plan_revision`, `acceptance_revision`, `scope_fingerprint` и bounded exact `assessed_paths` без glob;
- `test_criticality`, `test_disposition`, tested invariants и mapping acceptance scenarios;
- найденные существующие tests и их релевантность;
- `coverage_mode` и требуемые branch/security/consumer checks;
- alternative evidence, residual risks и follow-up;
- для `reuse` — полный `reuse_proof`;
- для `add/update` — `TestPlan` с matching action, непустыми bounded exact runnable `commands`, `expected_baseline`, `actual_baseline`, exact test paths и `protected_hashes`: canonical keysets обязаны точно совпадать, каждый файл уже существует, а объявленный SHA-256 равен фактическому; для feature/refactor baseline описывает отсутствующий или падающий до implementation invariant и наблюдённый результат;
- для `none` — только evidence plan; искусственный `TestPlan` и test commit не создаются.

`none` не отменяет CI suites, repository coverage thresholds, typecheck, lint, build, proto/Prisma generation, consumer/contract/security/GitOps checks, Reviewer, Architecture Guardian или QA. Backend сохраняет текущие 90%+ thresholds; около 80% — лишь необязательный ориентир для измеримого noncritical code, не новый CI floor.

## Машинный marker Test-maker

Поля assessment передаются плоско в одной последней строке:

```text
WGC_AGENT_RESULT: {"role":"test-maker","verdict":"assessment_ready","phase":"","input_revision":"<exact-input-revision>","plan_revision":"<revision>","acceptance_revision":"<revision>","test_criticality":"<critical|standard|low>","test_disposition":"<add|update|reuse|none>","scope_fingerprint":"<fingerprint>","assessed_paths":["<exact path>"],"tested_invariants":["<invariant>"],"existing_tests":["<test id/path>"],"coverage_mode":"<mode>","alternative_evidence":["<evidence>"],"residual_risks":["<risk>"]}
```

Добавь disposition-specific `reuse_proof` либо поля `rationale`, `disproportionate_cost`, `stronger_alternative_evidence`, `follow_up`. Hooks принимают nested `assessment` только для совместимости; role contract использует flat marker.

## State v3 и invalidation

V2 безопасно мигрируется в v3: сохраняется только совместимое privacy-safe non-test verification evidence; legacy `test`/`coverage` evidence, test-maker и downstream review/QA gates сбрасываются. Malformed/unsupported state fail-closed блокирует completion до нового repository audit и reactivation.

Production write внутри exact `assessed_paths` сохраняет TestAssessment/test-maker gate, но инвалидирует diff-facing approvals и старые test/coverage results. Write вне scope инвалидирует assessment и downstream. Contract/migration path всегда инвалидирует assessment. Изменение protected reuse test сохраняет assessment только если path явно fingerprinted и фактический SHA-256 всё ещё совпадает; иначе требуется новый assessment.
