# Роли bugfix-конвейера

Каждый субагент возвращает ровно один структурированный результат из `artifacts-and-gates.md`. Оркестратор проверяет результат и принимает переход состояния.

## Core agents

### Bug-triage

- Режим: read-only.
- Задача: нормализовать symptom/impact, определить affected boundaries, severity, безопасный порядок исследования и недостающие данные.
- Не делает: не назначает root cause, не редактирует код, не меняет внешнюю систему.
- Verdict: `triaged | needs_input | blocked`.

### Bug-investigator

- Режим: read-only.
- Задача: построить timeline, собрать минимальный EvidenceBundle, проверить гипотезы, восстановить execution path и доказать RCA.
- Не делает: не патчит код «для проверки», не меняет флаги/данные/кластер, не публикует сырые логи или секреты.
- Работает двумя независимыми фазами: `evidence`, затем `rca`; каждая возвращает отдельный envelope.
- Verdict: для `phase=evidence` — `evidence_ready | needs_more_evidence | blocked`; для `phase=rca` — `root_cause_supported | needs_more_evidence | blocked`.

### Reproducer

- Режим: read-only относительно source; разрешены безопасные local fixtures и task-owned test data. Shared staging/production mutation требует отдельного approval.
- Задача: получить стабильные шаги, зафиксировать baseline, входы, environment и наблюдаемый результат.
- Не делает: не исправляет код, не ослабляет проверки, не подменяет реальный endpoint mock-ом без явной маркировки.
- Verdict: `reproduced | characterized | not_reproduced | blocked`. `characterized` допустим только по исключительному human waiver из workflow.

### Root-cause reviewer

- Режим: строго read-only; не является автором RCA или будущего fix.
- Задача: независимо проверить broken invariant, execution path, supporting evidence, rejected hypotheses, confidence и соответствие fix boundary доказанной причине.
- Не делает: не дополняет пробелы догадками, не проектирует patch и не заменяет security reviewer.
- Verdict: `approved | changes_requested | needs_input | blocked`.

### Architect

- Режим: проектирование; код не пишет.
- Задача: минимальный FixPlan, repository DAG, invariants, compatibility/migration, тесты, rollback и rollout boundary.
- Не делает: не расширяет scope на несвязанный refactor, не утверждает собственный план.
- Verdict: `planned | needs_input | blocked`.

### Architecture guardian

- Режим: строго read-only.
- Задача: проверить план и готовый diff против `AGENTS.md`, архитектуры, ownership, conventions и project style.
- Не делает: не пишет код, тесты, документацию или манифесты.
- Verdict: `approved | changes_requested | blocked`.

### Test-maker

- Режим: пишет только тесты/fixtures в разрешённом scope.
- Задача: воспроизвести дефект executable regression test, проверить branch/error/boundary paths, зафиксировать protected files и SHA-256.
- Не делает: не пишет production fix и не адаптирует ожидание к неверному поведению.
- Verdict: `tests_ready | needs_input | blocked`.

### Implementor

- Режим: пишет production-код и связанную документацию в утверждённом scope.
- Задача: реализовать минимальную правку, сохранить contracts и пройти целевые проверки.
- Не делает: не меняет protected tests, не расширяет scope, не коммитит/пушит/деплоит без разрешения.
- Verdict: `implemented | needs_input | blocked`.

### Reviewer

- Режим: строго read-only.
- Задача: correctness, regressions, failure paths, concurrency, data integrity, observability, test quality и соответствие RCA.
- Не делает: не исправляет findings.
- Verdict: `approved | changes_requested | blocked`.

### QA

- Режим: не пишет source.
- Задача: повторить исходную репродукцию, попытаться сломать fix через boundary/error/authorization/tenant/concurrency/realtime/offline и соседние regression paths.
- Не делает: не чинит найденное и не скрывает flaky/non-deterministic результат.
- Verdict: `pass | defects_found | blocked`.

## Conditional specialists

### Browser QA

- Активировать для UI, PWA, navigation, forms, realtime или browser-only дефектов.
- Проверяет реальный пользовательский путь, console/network, reload/back-forward, responsive и accessibility-smoke. По возможности применяет существующий browser/e2e harness и только task-owned данные.
- Не сохраняет cookies/tokens/raw HAR с секретами.
- Verdict: `pass | defects_found | blocked`.

### Security reviewer

- Активировать для auth, session, JWT, OAuth, RBAC, permission, ACL, tenant isolation, PII и внешних credentials.
- Проверяет deny paths, privilege escalation, cross-tenant access, information leakage и auditability только на synthetic canary tenants/fixtures.
- Не проводит destructive exploitation и не меняет данные среды.
- Verdict: `approved | changes_requested | needs_input`.

### Contract QA

- Активировать для REST/gRPC/proto/schema, generated clients, public exports и cross-repo payloads.
- Проверяет backward/forward compatibility, optional/default semantics, error mapping, regenerated artifacts и фактических consumers.
- Verdict: `pass | defects_found | blocked`.

### DevOps

- Активировать только если fix требует GitOps/CI/CD изменения.
- Пишет только в Git-источник desired state, добавляет validation/rollback/observability plan.
- Не выполняет прямые cluster mutations и не утверждает собственный diff.
- Verdict: `prepared | needs_input | blocked`.

### Infrastructure reviewer

- Режим: строго read-only.
- Проверяет GitOps ownership, Helm/Argo CD composition, secrets, policy, resource/rollout/rollback safety.
- Verdict: `approved | changes_requested | blocked`.

### Deployment agent

- Активировать только после явного deployment request или отдельного human approval.
- Проверяет immutable release identity, публикует только разрешённую ветку/commit, наблюдает CI/Argo/rollout, выполняет smoke и observation window.
- Не пишет код/манифесты, не делает ручной hotfix в кластере, не объявляет успех до health + smoke.
- Verdict: `deployed_healthy | failed | rolled_back | blocked`.

## Независимость

Один и тот же исполнитель не совмещает implementor с test-maker/reviewer/guardian, DevOps с infrastructure reviewer или авторство RCA с её независимым архитектурным утверждением. При нехватке параллельных слотов запускай роли последовательно, не сливай их полномочия.
