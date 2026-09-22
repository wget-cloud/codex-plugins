# Адаптивная политика тестирования

Test-maker допустим только для protected critical invariant, где независимый baseline materially снижает риск; Full сам по себе его не требует. Обычные slice-local tests пишет Implementor, а Orchestrator или назначенный Reviewer проверяет их вместе с diff. До production implementation владелец assessment выпускает компактный `TestAssessment`, выбирая `add | update | reuse | none` и `test_ownership: implementor | protected_test_maker | n/a`; после изменения scope, плана, acceptance, protected tests, contract/migration surface или production path вне `assessed_paths` assessment повторяется.

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
- `update`: существующий полезный test должен отражать новую семантику. Critical/protected test обновляет Test-maker; обычный — Implementor.
- `add`: новый устойчивый test даёт regression value. Critical/protected test создаёт Test-maker; обычный — Implementor вместе с slice.
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
- для `add/update` — `TestPlan` с matching action, непустыми bounded exact runnable `commands`, expected/actual baseline и exact test paths; при `protected_test_maker` обязательны существующие файлы и matching `protected_hashes`, при `implementor` protected hashes отсутствуют и test проверяется в общей `DIFF_IDENTITY`;
- для `none` — только evidence plan; искусственный `TestPlan` и test commit не создаются.

`none` не отменяет фактические repository/CI gates и targeted contract/security/GitOps checks. Reviewer, Architecture Guardian и QA не становятся обязательными без конкретного risk signal. Не повышай coverage сверх существующего repository threshold в рамках обычного slice.

## Машинный marker Test-maker

Поля assessment передаются плоско в одной последней строке:

```text
WGC_AGENT_RESULT: {"role":"test-maker","verdict":"assessment_ready","phase":"","input_revision":"<exact-input-revision>","plan_revision":"<revision>","acceptance_revision":"<revision>","test_criticality":"<critical|standard|low>","test_disposition":"<add|update|reuse|none>","test_ownership":"<implementor|protected_test_maker|n/a>","scope_fingerprint":"<fingerprint>","assessed_paths":["<exact path>"],"tested_invariants":["<invariant>"],"existing_tests":["<test id/path>"],"coverage_mode":"<mode>","alternative_evidence":["<evidence>"],"residual_risks":["<risk>"]}
```

Добавь disposition-specific `reuse_proof` либо поля `rationale`, `disproportionate_cost`, `stronger_alternative_evidence`, `follow_up`. Hooks принимают nested `assessment` только для совместимости; role contract использует flat marker.

## State v4 и invalidation

V2/v3 мигрируются в v4 с сохранением безопасного baseline и сбросом прежних approvals/verification: нужна новая TaskAssessment. Повреждённый state требует repository audit. Scope expansion отменяет маршрут. In-scope write сохраняет маршрут, но отменяет затронутые проверки и approvals. Contract/migration/test изменения сохраняют прежние строгие TestAssessment invalidation rules.

## Владелец в v7

Во всех execution modes TestAssessment выпускает Task Assessor вместе с TaskAssessment; обычные add/update используют `test_ownership=implementor`. `protected_test_maker` выбирается только для явно защищённого critical baseline. В task-creation политика provisional. [Команда](task-assessment.md), [повторное использование проверок](verification.md).
