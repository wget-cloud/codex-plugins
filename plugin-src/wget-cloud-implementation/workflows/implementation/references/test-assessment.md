# Адаптивная политика тестирования

Test-maker обязателен для Full и add/update; Light/Standard none/reuse оценивает отдельный Task Assessor. Новый тест не является обязательным результатом. До production implementation он выпускает `TestAssessment`, выбирая `add | update | reuse | none`; после изменения scope, плана, acceptance, тестов, contract/migration surface или production path вне `assessed_paths` assessment повторяется.

## Критичность

| Уровень | Критерий | Ожидание |
|---|---|---|
| `critical` | business rules; money; auth/RBAC/tenant/security; persisted data/migrations; public REST/gRPC/proto/export/event/WebSocket contracts; concurrency/retry/idempotency; Temporal/cron/queue/outbox/background work; серьёзная regression/incident; неизвестный или неоднозначный риск | Максимально доказать изменённые positive/negative/boundary/security branches. `none` запрещён. |
| `standard` | Наблюдаемое поведение без critical-сигналов | Обычно `add`, `update` или `reuse`; `none` — только формальное исключение. |
| `low` | Только copy, spacing, theme, docs или механическая правка без control flow, accessibility, responsive visibility, данных и contracts | Допустим `none` с browser/visual/static evidence. |

Любой critical-сигнал побеждает остальные признаки; неопределённость требует limited evidence; до прояснения Light запрещён. Accessibility, focus/keyboard, responsive visibility, API, realtime и offline behavior не являются косметикой автоматически. Публичный export/type/runtime protocol `wget-cloud-front-lib` всегда `critical` и требует consumer evidence.

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

`none` не отменяет CI suites, repository coverage thresholds, typecheck, lint, build, proto/Prisma generation, consumer/contract/security/GitOps checks, применимые по TaskAssessment Reviewer, Architecture Guardian или QA. Backend сохраняет текущие 90%+ thresholds; около 80% — лишь необязательный ориентир для измеримого noncritical code, не новый CI floor.

## Машинный marker Test-maker

Поля assessment передаются плоско в одной последней строке:

```text
WGC_AGENT_RESULT: {"role":"test-maker","verdict":"assessment_ready","phase":"","input_revision":"<exact-input-revision>","plan_revision":"<revision>","acceptance_revision":"<revision>","test_criticality":"<critical|standard|low>","test_disposition":"<add|update|reuse|none>","scope_fingerprint":"<fingerprint>","assessed_paths":["<exact path>"],"tested_invariants":["<invariant>"],"existing_tests":["<test id/path>"],"coverage_mode":"<mode>","alternative_evidence":["<evidence>"],"residual_risks":["<risk>"]}
```

Добавь disposition-specific `reuse_proof` либо поля `rationale`, `disproportionate_cost`, `stronger_alternative_evidence`, `follow_up`. Hooks принимают nested `assessment` только для совместимости; role contract использует flat marker.

## State v4 и invalidation

V2/v3 мигрируются в v4 с сохранением безопасного baseline и сбросом прежних approvals/verification: нужна новая TaskAssessment. Повреждённый state требует repository audit. Scope expansion отменяет маршрут. In-scope write сохраняет маршрут, но отменяет затронутые проверки и approvals. Contract/migration/test изменения сохраняют прежние строгие TestAssessment invalidation rules.

## Владелец в v7

В Light/Standard none/reuse TestAssessment выпускает Task Assessor вместе с TaskAssessment, используя те же evidence fields. Он задаёт plan/acceptance revision и floor для компактного маршрута. Full floor принадлежит Architect. Add/update всегда принадлежат Test-maker. В task-creation политика provisional. [Команда](task-assessment.md), [повторное использование проверок](verification.md).
