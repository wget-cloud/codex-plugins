# Предварительная test policy в backlog

Task-creation не принимает окончательное решение о тестах и не запускает Test-maker. Для каждого исполнимого item в managed body добавляется только предварительный блок `test_policy`, помогающий реализации начать assessment:

```text
test_policy:
  provisional_criticality: critical | standard | low
  critical_signals: [<business/money/security/data/contract/concurrency/background/regression/unknown>]
  candidate_invariants: [<что важно доказать>]
  existing_test_leads: [<известные test IDs/paths или unknown>]
  likely_disposition: add | update | reuse | none | assess_during_implementation
  alternative_evidence: [<browser/visual/static/contract evidence>]
  residual_risks: [<risk>]
```

Классификация предварительная:

- `critical`: business/money, auth/RBAC/tenant/security, data/migrations, public REST/gRPC/proto/export/event/WebSocket contracts, concurrency/retry/idempotency, Temporal/cron/queue/outbox, серьёзная regression/incident или неизвестный риск;
- `standard`: наблюдаемое поведение без critical-сигналов;
- `low`: только copy/spacing/theme/docs/mechanical change без control flow, accessibility, responsive visibility, data/contracts.

Любой critical-сигнал побеждает; неоднозначность предварительно `critical`. Accessibility, focus/keyboard, responsive visibility, API, realtime/offline не являются косметикой автоматически. Публичные `wget-cloud-front-lib` contracts/exports предварительно `critical`.

`likely_disposition` не является gate и не связывает Test-maker. Окончательный `TestAssessment`, criticality и `add | update | reuse | none` выбирает Test-maker только при implementation по актуальным plan/acceptance revisions и repository evidence. `critical + none` будет запрещён; `standard + none` потребует доказанной непропорциональной стоимости и более сильной альтернативы.

Не создавай новые GitHub Project fields для test policy. Блок хранится только в managed task body и отражается в acceptance criteria: выполнить окончательный TestAssessment и сохранить все обязательные repository/CI, typecheck, lint, build, coverage-threshold, proto/Prisma, consumer/contract/security/GitOps, review и QA gates независимо от disposition.
