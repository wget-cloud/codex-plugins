# Epic implementation workflow

## Состояния run

`discovered → scoped → product_ready → architecture_approved → executing → reviewing → testing → integrated → delivery_ready → reconciled`

Каждый item имеет собственную state machine и revision. Approval одного item не переносится на другой.

## Item loop

1. Verify issue/Project revision и dependencies.
2. Product acceptance gate.
3. Architecture slice и test contract.
4. Implementor diff.
5. Orchestrator integrity check.
6. Reviewer + Architecture Guardian diff gate.
7. QA.
8. Integration/delivery/status reconciliation.

## Invalidation

Изменение production diff инвалидирует reviewer, architecture diff и QA. Изменение contract/schema может инвалидировать downstream item readiness и требует Project Manager replan. Изменение product semantics инвалидирует Product Manager acceptance и Architecture plan.

## Stop conditions

Останови новую wave при shared contract failure, migration incompatibility, cross-tenant/security finding, dirty-state collision, rate limit, lost Project authorization или исчерпании согласованного scope. Уже начатые безопасные проверки можно завершить read-only.
