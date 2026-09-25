# Адаптивная политика тестирования

При `MVP_SKIP_TESTS: true` из `SKILL.md` все правила ниже о написании, изменении, запуске тестов, coverage, Test-maker и запрете `none` отключены. TestAssessment остаётся обязательным: `test_disposition: none`, `coverage_mode: skipped_by_mvp_flag`, без TestPlan и test paths; зафиксируй альтернативное evidence, непроверенные инварианты и residual risks даже для `critical`. Не проверяй покрытие. Требования репозитория/CI к тестам остаются незакрытыми, не выдавай их за успешные. При `false` действует обычная политика ниже.

TestAssessment обязателен, но отдельный Test-maker нужен только для protected critical invariants, где независимость от Implementor даёт реальную regression value. Light/Standard assessment выпускает Orchestrator либо назначенный Assessor; обычные `add/update` tests принадлежат Implementor и независимо читаются Reviewer. После изменения scope, плана, acceptance, protected tests, contract/migration surface или production path вне `assessed_paths` assessment повторяется.

## Критичность

| Уровень | Критерий | Ожидание |
|---|---|---|
| `critical` | business rules; money; auth/RBAC/tenant/security; persisted data/migrations; public gRPC/Protobuf/HTTP/event contracts; concurrency/retry/idempotency; Temporal/cron/queue/outbox/background work; platform public API; CI/release ownership; серьёзная regression/incident; неизвестный или неоднозначный риск | Максимально доказать изменённые positive/negative/boundary/security branches. `none` запрещён. |
| `standard` | Наблюдаемое поведение без critical-сигналов | Обычно `add`, `update` или `reuse`; `none` — только формальное исключение. |
| `low` | Только docs/comment, formatting или механическая metadata-правка без control flow, runtime behavior, данных и contracts | Допустим `none` со static validation и repository-required checks. |

Любой critical-сигнал побеждает остальные признаки; неопределённость требует limited evidence; до прояснения Light запрещён. Публичный Protobuf/HTTP/event contract и публичный API `platform` всегда `critical` и требуют consumer evidence.

Architect указывает `minimum_test_criticality` и `plan_revision`. Test-maker может повысить уровень, и Architect может повысить floor при прежней revision. Понижение при той же `plan_revision` блокируется: нужен новый evidence и новая plan revision; она инвалидирует TestAssessment и прежний Guardian plan approval, а следующий assessment разрешён только после повторного approval.

## Disposition

- `reuse`: существующий тест прямо доказывает изменяемый invariant. `reuse_proof` обязан содержать exact `test_id`, `test_path`, `invariant_mapping`, `successful_run: true`, актуальный `file_sha256`; для `critical` также `critical_branch_evidence` и успешный coverage evidence.
- `update`: существующий полезный тест должен отражать новую семантику. Для critical invariant Test-maker обновляет и защищает SHA-256; иначе assessment может назначить обычный тест Implementor’у.
- `add`: новый устойчивый тест даёт реальную regression value. Для critical invariant Test-maker создаёт protected test; иначе assessment задаёт invariant/commands, а обычный тест создаёт Implementor.
- `none`: task-specific автоматический тест не создаётся. `critical + none` запрещён. `standard + none` требует одновременно `rationale`, `disproportionate_cost: true`, непустые `stronger_alternative_evidence`, `residual_risks` и `follow_up`.

Для typo в service docs типичный результат — `low/none`: link/static validation и обязательные repository checks, если они применимы к затронутому пути.

## TestAssessment

Артефакт содержит:

- `plan_revision`, `acceptance_revision`, `scope_fingerprint` и bounded exact `assessed_paths` без glob;
- `test_criticality`, `test_disposition`, tested invariants и mapping acceptance scenarios;
- найденные существующие tests и их релевантность;
- `coverage_mode` и требуемые branch/security/consumer checks;
- alternative evidence, residual risks и follow-up;
- для `reuse` — полный `reuse_proof`;
- для `add/update` — `TestPlan` с matching action, `test_ownership`, непустыми bounded exact runnable `commands`, expected/actual baseline и exact test paths; при `protected_test_maker` обязательны фактически совпавшие `protected_hashes` с identical canonical keyset, а при `implementor` protected keyset пуст и Reviewer проверяет добавленный тест в общей `DIFF_IDENTITY`;
- для `none` — только evidence plan; искусственный `TestPlan` и test commit не создаются.

`none` не отменяет фактические repository/CI gates. Полные race/vet/lint/build/coverage и применимые Buf/consumer checks выполняются один раз на service boundary, когда этого требует repository policy; они не повторяются на каждом tranche.

## Машинный marker Test-maker

Поля assessment передаются плоско в одной последней строке:

```text
WGC_AGENT_RESULT: {"role":"test-maker","verdict":"assessment_ready","phase":"","input_revision":"<exact-input-revision>","plan_revision":"<revision>","acceptance_revision":"<revision>","test_criticality":"<critical|standard|low>","test_disposition":"<add|update|reuse|none>","test_ownership":"<implementor|protected_test_maker>","scope_fingerprint":"<fingerprint>","assessed_paths":["<exact path>"],"tested_invariants":["<invariant>"],"existing_tests":["<test id/path>"],"coverage_mode":"<mode>","alternative_evidence":["<evidence>"],"residual_risks":["<risk>"]}
```

Добавь disposition-specific `reuse_proof` либо поля `rationale`, `disproportionate_cost`, `stronger_alternative_evidence`, `follow_up`. Role contract использует flat marker.

## Invalidation и владелец

Scope expansion отменяет маршрут. In-scope write сохраняет assessment, но отменяет только затронутые проверки и approvals. Contract/migration/test изменения применяют selective invalidation.

В Light/Standard none/reuse TestAssessment выпускает Task Assessor вместе с TaskAssessment, используя те же evidence fields. Он задаёт plan/acceptance revision и floor для компактного маршрута. Full floor принадлежит Architect. Assessment для Full critical и protected add/update принадлежит Test-maker; обычные implementor-owned tests остаются частью одного implementation diff. [Команда](task-assessment.md), [повторное использование проверок](verification.md).
