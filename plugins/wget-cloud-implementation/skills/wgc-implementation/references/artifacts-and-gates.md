# Артефакты и quality gates

## Содержание

- Правила артефактов
- WorkItem
- EvidenceReport
- ArchitecturePlan
- TestPlan
- ImplementationReport
- ReviewReport
- QAReport
- InfrastructureChangeReport
- DeploymentReport
- Gate ledger
- Repo-specific checks

## Правила артефактов

Артефакт может существовать в рабочем контексте, task note или файле только если пользователь просит сохранить его. Не засоряй product repositories служебными файлами оркестрации.

Каждый артефакт обязан содержать:

- `work_item_id`;
- `role` и `task_slice`;
- `input_revision`: Git HEAD каждого repo и идентификатор предыдущего артефакта;
- `scope`: repositories/paths;
- `evidence`: file:line, commands и результаты;
- `risks` и `unknowns`;
- один verdict из разрешённого enum.

Каждый субагент также завершает ответ строкой `WGC_AGENT_RESULT` из [agents.md](agents.md). Lifecycle ledger принимает только разрешённый verdict и revision, назначенный при старте агента. Для `reviewer`, post-implementation `architecture-guardian`, `QA` и `infrastructure-reviewer` approval перестаёт действовать после изменения reviewed tree.

Артефакт устаревает, если изменился относящийся к нему diff, plan, acceptance criteria, protected test или release identity.

## WorkItem

```yaml
work_item_id: WC-<local-id>
objective: <observable outcome>
acceptance_criteria:
  - id: AC-1
    scenario: <given/when/then or precise statement>
exclusions:
  - <not in scope>
repositories:
  - name: backend
    head: <sha>
    branch: <branch or detached>
    dirty_paths: []
constraints:
  compatibility: <requirements>
  security: <RBAC/tenant/secrets>
  performance: <if applicable>
deployment:
  requested: false
  environment: null
  approval: null
risk_level: low | medium | high | critical
process_depth: small | standard | cross-repo | deployment
```

Gate `intake_complete` проходит, если outcome тестируем, exclusions ясны, Git state зафиксирован и существенный выбор не скрыт предположением.

## EvidenceReport

```yaml
verdict: mapped | needs_input
execution_path:
  - file:line: <entry point>
    role: <transport/application/domain/adapter/UI/etc>
contracts:
  - owner: <repo/path>
    consumers: []
tests:
  existing: []
  coverage_commands: []
delivery:
  ci: []
  gitops: []
observations:
  production: []
  legacy: []
  mock_or_unwired: []
unknowns: []
```

Gate проходит только при доказанной end-to-end цепочке или явно ограниченном scope. Перечень совпадений поиска без анализа не является evidence map.

## ArchitecturePlan

```yaml
verdict: proposed | needs_input
invariants:
  - id: INV-1
    statement: <must remain true>
owners:
  - concern: <domain/contract/UI/runtime>
    repository: <repo>
    path: <path>
contracts:
  - name: <contract>
    source_of_truth: <path>
    compatibility: <additive/versioned/migration>
    consumers: []
dag:
  - id: STEP-1
    repository: <repo>
    allow_paths: []
    depends_on: []
    change: <one logical invariant>
    tests: []
    docs: []
    completion_evidence: []
delivery_order: []
rollback: <strategy>
rejected_alternatives: []
unresolved_decisions: []
```

Architecture guardian возвращает отдельный report:

```yaml
verdict: approved | changes_requested | needs_input
phase: plan | diff
blocking_findings:
  - severity: critical | high | medium
    location: <file:line or DAG node>
    invariant: <violated rule>
    impact: <consequence>
    direction: <required direction, no patch>
advisories: []
```

Gate требует `approved`, ноль blocking findings и ноль unresolved decisions, влияющих на реализацию.

## TestPlan

```yaml
verdict: baseline_ready | changes_requested | blocked
acceptance_mapping:
  AC-1:
    tests: [<test name/path>]
protected_files:
  - path: <repo-relative path>
    sha256: <hash>
baseline:
  expected: pass | fail
  actual: pass | fail | not_run
  reason: <why this is valid>
commands:
  - command: <exact command>
    exit_code: <code>
    coverage: <changed branches/lines or report>
gaps: []
```

Protected files должны включать все test-maker files, а также существующие regression tests, специально назначенные оркестратором. После implementor оркестратор пересчитывает hashes. Несовпадение автоматически отклоняет implementation gate.

Valid failing baseline падает по ожидаемой отсутствующей семантике, а не из-за syntax/config/unrelated environment failure. Если test-first невозможно до появления interface, plan фиксирует двухшаговый handshake: implementor создаёт минимальный contract, test-maker завершает tests, затем implementor продолжает behavior.

## ImplementationReport

```yaml
verdict: implemented | needs_input | blocked
dag_node: STEP-1
changed_files:
  - path: <path>
    reason: <relation to invariant>
protected_test_check: unchanged
behavior_evidence:
  - acceptance_id: AC-1
    evidence: <test/inspection>
commands:
  - command: <exact>
    exit_code: <code>
    result: <short factual result>
coverage:
  changed_branches: <evidence>
documentation: []
known_gaps: []
```

Оркестратор независимо проверяет changed files и hashes. `implemented` не означает review approval.

## ReviewReport

```yaml
verdict: approved | changes_requested | needs_input
review_type: code | architecture | infrastructure
input_diff: <repo/head + diff identity>
findings:
  - severity: critical | high | medium | low
    location: <file:line>
    scenario: <how it fails>
    impact: <why it matters>
    required_behavior: <what must become true>
non_blocking_notes: []
commands: []
```

Critical/high/medium correctness, security, data-loss, compatibility и architecture violations блокируют. Low style note блокирует только при явном project rule или реальном maintainability impact. `approved` невозможен при недоступном критичном evidence — используй `needs_input`.

## QAReport

```yaml
verdict: pass | defects_found | blocked
environment: <local/test/staging identity>
release_identity: <commit/image if applicable>
scenario_matrix:
  - id: QA-1
    risk: <risk>
    result: pass | fail | not_run
    evidence: <request/screenshot/log/test>
defects:
  - severity: critical | high | medium | low
    preconditions: []
    steps: []
    expected: <expected>
    actual: <actual>
    evidence: []
coverage_gaps: []
```

QA `pass` означает «выполненные сценарии прошли в указанном environment», а не отсутствие всех багов.

## InfrastructureChangeReport

```yaml
verdict: prepared | needs_input | blocked
environment: <dev/stage/prod>
application: <Argo/Application or component>
image:
  repository: <registry path>
  tag: <immutable tag>
  digest: <if known>
changed_sources: []
generated_outputs: []
sync_order: <wave/dependencies>
secrets: <ExternalSecret/Vault references only>
health:
  probes: <summary>
  resources: <summary>
  pdb_autoscaling: <summary>
migration: <none or controlled strategy>
rollback: <Git revert/previous immutable image>
commands: []
```

Infrastructure reviewer даёт `ReviewReport(review_type=infra)`. Gate требует reproducible render, passed validations, immutable image, safe secrets/migration/prune и `approved`.

## DeploymentReport

```yaml
verdict: deployed_healthy | failed | blocked | approval_invalid
approval_identity:
  repository: <repo>
  branch: <branch>
  commit: <sha>
  environment: <environment>
  image: <tag/digest>
publish:
  action: <push/merge trigger explicitly allowed>
  result: <factual>
ci:
  run: <id/url>
  result: <status>
gitops:
  revision: <sha>
  sync: <status>
  health: <status>
rollout:
  workloads: []
  events: []
  errors: []
smoke: []
observation_window:
  started_at: <timestamp>
  ended_at: <timestamp>
  signals: []
rollback:
  needed: false
  proposal: null
residual_risks: []
```

Успешный push не равен deployment. Argo `Synced` не равен `Healthy`; healthy workload не заменяет smoke; короткий smoke не доказывает отсутствие delayed failures.

## Gate ledger

Оркестратор ведёт компактную таблицу:

| Gate | Input identity | Owner | Verdict | Evidence | Still valid |
| --- | --- | --- | --- | --- | --- |
| Intake | WorkItem v1 | orchestrator | pass | Git audit | yes |
| Architecture plan | Plan v2 | guardian | approved | report | yes |
| Tests | TestPlan v1 | test-maker | baseline_ready | hashes | yes |
| Implementation | diff X | orchestrator | pass | diff + commands | yes |
| Code review | diff X | reviewer | approved | ReviewReport | yes |
| Architecture diff | diff X | guardian | approved | ReviewReport | yes |
| QA | diff X/env Y | QA | pass | QAReport | yes |
| Infrastructure | k8s diff Z | infra reviewer | approved | report | n/a |
| Deploy approval | commit/image/env | human | approved | explicit message | n/a |
| Rollout | release identity | deployment agent | deployed_healthy | DeploymentReport | n/a |

Любой новый diff меняет identity и инвалидирует зависимые approvals. Не переносить approval между branches/environments/images.

## Repo-specific checks

Команды всегда сверяй с текущим `package.json`, Makefile и local docs. Базовая матрица:

| Repository | Минимум для production change | Дополнительно по риску |
| --- | --- | --- |
| `frontend` | targeted Vitest с coverage, `npm run type-check`, `npm run lint` | `npm run build`, Playwright/route/PWA/i18n checks |
| `backend` | service-targeted Jest с coverage изменённых веток | service build, proto generation diff, Prisma validation/generate, wider integration tests |
| `wget-cloud-front-lib` | `npm run typecheck`, `npm run build`, inspect exports/dist | pack dry-run и build/typecheck обоих consumers |
| `wget-cloud-site` | guard scripts, targeted tests, lint, type-check | build обоих data modes, BFF/auth/PWA smoke, browser checks |
| `k8s` | renderer + `make validate` или актуальные эквиваленты | focused GitOps/resource/telemetry tests, Helm render, environment smoke after rollout |

Правила доказательств:

- unrelated passing tests не заменяют coverage затронутой области;
- общий процент не заменяет changed condition/error/security branches;
- build не заменяет behavioral tests;
- mocked unit test не заменяет integration boundary при contract change;
- недоступный command фиксируется с exact reason и closest alternative;
- предупреждения и skipped tests перечисляются, а не скрываются под exit code 0.
