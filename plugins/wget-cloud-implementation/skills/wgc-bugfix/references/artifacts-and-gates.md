# Артефакты и gates

## Общий envelope субагента

Каждый субагент завершает ответ JSON-блоком на одной строке:

```text
WGC_AGENT_RESULT: {"role":"bug-triage","verdict":"triaged","phase":"","input_revision":"<workspace-revision>","scope":["backend"],"evidence":["artifact:triage-1"],"findings":[],"checks":[],"blocked_by":[]}
```

Требования:

- `role` — точное имя роли;
- `verdict` — только разрешённое для роли значение;
- `phase` — `evidence|rca` для bug-investigator, `plan|diff` для architecture-guardian, иначе пустая строка;
- `input_revision` — exact revision из `SubagentStart`; для review/QA она должна совпадать с текущей workspace revision;
- `scope` — только реально просмотренные repositories/paths;
- `evidence` — безопасные handles, команды или redacted summaries;
- `findings` — blocking/non-blocking findings с severity и location;
- `checks` — команда/сценарий, exit/status и результат;
- `blocked_by` — конкретное отсутствующее разрешение, доступ или вход.

Hooks распознают envelope как вспомогательный ledger. Оркестратор всё равно проверяет артефакт и актуальность revision.

## Обязательные артефакты

### BugCase

`id`, `reported_comment_redacted_summary`, `observed`, `expected`, `environment`, `release_identity`, `actor_tenant`, `actor_role`, `resource_owner_tenant`, `data_classification`, `security_incident_owner`, `time_window`, `frequency`, `preconditions`, `impact`, `evidence_handles`, `unknowns`, `reproduction_waiver`, `deployment_requested`, `deployment_authorized`.

Не копируй секреты или полный чувствительный комментарий в persistent state; сохраняй redacted summary.

### TriageReport

`severity`, `blast_radius`, `affected_boundaries`, `primary_route`, `route_flags`, `initial_hypotheses`, `safe_next_actions`, `missing_inputs`, `verdict`.

### EvidenceBundle

`phase=evidence`, `timeline`, `items[{handle,source,time_range,release,relation,redaction,limitations}]`, `environment_deltas`, `observability_gaps`, `verdict`.

### ReproductionReport

`revision`, `environment`, `preconditions`, `steps_or_command`, `observed`, `expected`, `frequency`, `negative_control`, `evidence`, `verdict`.

### RootCauseAnalysis

`phase=rca`, `broken_invariant`, `first_fault_location`, `execution_path`, `trigger`, `supporting_evidence`, `rejected_hypotheses`, `escape_reason`, `fix_boundary`, `confidence`, `verdict`.

### RootCauseReviewReport

`reviewed_rca`, `evidence_sufficiency`, `execution_path_fit`, `rejected_hypotheses_assessment`, `confidence_assessment`, `fix_boundary_assessment`, `findings`, `verdict`.

### FixPlan

`repositories`, `atomic_steps`, `allowed_paths`, `forbidden_paths`, `contracts`, `compatibility`, `test_strategy`, `documentation`, `rollback`, `delivery_order`, `risks`.

`CharacterizationPlan` — отдельный pre-RCA артефакт waiver-маршрута: `localized_branch`, `evidence`, `task_owned_test_scope`, `expected_failing_observable`, `forbidden_production_changes`, `waiver_owner`. Он не заменяет `FixPlan`.

### TestPlan

`regression_scenario`, `baseline_result`, `test_files`, `protected_files[{path,sha256}]`, `coverage_targets`, `conditional_suites`, `limitations`, `verdict`.

`CharacterizationTest` waiver-маршрута должен падать на исходной revision и создаётся до RCA только в task-owned test scope. После RCA test-maker заново подтверждает его как regression contract либо создаёт финальный `TestPlan`; ранний verdict не закрывает финальный test-maker gate.

### ImplementationReport

`revision`, `files_changed`, `root_cause_mapping`, `behavior_change`, `checks`, `coverage`, `protected_hash_check`, `docs`, `remaining_risks`, `verdict`.

### ReviewReport

`revision`, `scope`, `findings[{severity,location,reason,required_action}]`, `root_cause_fit`, `test_assessment`, `verdict`.

### QAReport

`revision`, `original_reproduction`, `scenarios`, `environments`, `evidence`, `defects`, `limitations`, `verdict`.

### BugfixReport

`symptom`, `root_cause`, `fix`, `regression_proof`, `repositories_files`, `checks`, `gate_ledger`, `git_status`, `deployment_status`, `known_risks`, `human_actions`.

## Gate ledger

Оркестратор ведёт таблицу с `gate`, `owner`, `verdict`, `revision`, `evidence`, `timestamp`. Approval без revision или для старой revision не закрывает gate.

Core gates:

1. `bug-triage: triaged`
2. `bug-investigator phase=evidence: evidence_ready`
3. `reproducer: reproduced`, либо `characterized` с документированным human `reproduction_waiver`
4. `bug-investigator phase=rca: root_cause_supported`
5. `root-cause-reviewer: approved`
6. `architect: planned`
7. `architecture-guardian phase=plan: approved`
8. `test-maker: tests_ready`
9. `implementor: implemented`
10. `reviewer: approved`
11. `architecture-guardian phase=diff: approved`
12. `qa: pass`

Conditional gates добавляются по route flags: `browser-qa: pass`, `security-reviewer: approved`, `contract-qa: pass`, `devops: prepared`, `infrastructure-reviewer: approved`, `deployment-agent: deployed_healthy`.

## Severity

Triage использует единую шкалу impact: `critical` — активная cross-tenant/data-loss/security компрометация или массовая недоступность; `high` — основная функция недоступна без приемлемого обхода; `medium` — функция нарушена, но есть безопасный обход/ограниченный blast radius; `low` — локальный дефект без потери данных и критического процесса; `unknown` — evidence недостаточно. Findings ниже используют отдельную review-шкалу.

- `blocking`: исправление неверно/опасно, invariant не доказан, security/tenant/data loss risk, broken build/test/contract или deployment health.
- `major`: вероятная регрессия, непокрытая критичная ветка, несовместимость или существенная operability проблема.
- `minor`: локальная maintainability/clarity проблема без риска текущего исправления.
- `note`: рекомендация вне blocking scope.

Reviewer/guardian/QA не должны превращать unrelated notes в расширение bugfix. Такие пункты выносятся отдельно.

## Revision invalidation

После изменения source diff пересчитай workspace revision. Инвалидируй implementor result и все code-based approvals: reviewer, architecture-diff, QA, browser, security, contract. Test-maker остаётся валиден только если protected tests и test assumptions не изменились. Изменение теста, контракта, plan или infra diff инвалидирует зависящие gates согласно workflow.
