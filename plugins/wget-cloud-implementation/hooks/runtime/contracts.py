"""Executable profile verdicts; mirrored by generated role contracts."""
from typing import Dict, Set

PROFILE_ROLE_VERDICTS: Dict[str, Dict[str, Set[str]]] = {
    "implementation": {
        "explorer": {"mapped", "needs_input"},
        "architect": {"proposed", "needs_input"},
        "architecture-guardian": {"approved", "changes_requested", "needs_input"},
        "test-maker": {"assessment_ready", "changes_requested", "blocked"},
        "implementor": {"implemented", "needs_input", "blocked"},
        "reviewer": {"approved", "changes_requested", "needs_input"},
        "qa": {"pass", "defects_found", "blocked"},
        "devops": {"prepared", "needs_input", "blocked"},
        "infrastructure-reviewer": {"approved", "changes_requested", "needs_input"},
        "deployment-agent": {"deployed_healthy", "failed", "blocked", "approval_invalid"},
    },
    "bugfix": {
        "bug-triage": {"triaged", "needs_input", "blocked"},
        "bug-investigator": {"evidence_ready", "root_cause_supported", "needs_more_evidence", "blocked"},
        "reproducer": {"reproduced", "characterized", "not_reproduced", "blocked"},
        "root-cause-reviewer": {"approved", "changes_requested", "needs_input", "blocked"},
        "architect": {"planned", "needs_input", "blocked"},
        "architecture-guardian": {"approved", "changes_requested", "blocked"},
        "test-maker": {"assessment_ready", "needs_input", "blocked"},
        "implementor": {"implemented", "needs_input", "blocked"},
        "reviewer": {"approved", "changes_requested", "blocked"},
        "qa": {"pass", "defects_found", "blocked"},
        "browser-qa": {"pass", "defects_found", "blocked"},
        "security-reviewer": {"approved", "changes_requested", "needs_input"},
        "contract-qa": {"pass", "defects_found", "blocked"},
        "devops": {"prepared", "needs_input", "blocked"},
        "infrastructure-reviewer": {"approved", "changes_requested", "blocked"},
        "deployment-agent": {"deployed_healthy", "failed", "rolled_back", "blocked"},
    },
    "task-creation": {
        "product-manager": {"specified", "needs_input"},
        "project-manager": {"project_ready", "needs_input", "blocked"},
        "implementation-auditor": {"audited", "needs_input"},
        "architect": {"proposed", "needs_input"},
        "backlog-reviewer": {"approved", "changes_requested", "needs_input"},
    },
    "epic-implementation": {
        "product-manager": {"accepted", "changes_requested", "needs_input"},
        "project-manager": {"planned", "progress_updated", "blocked", "needs_input"},
        "explorer": {"mapped", "needs_input"},
        "architect": {"proposed", "needs_input"},
        "architecture-guardian": {"approved", "changes_requested", "needs_input"},
        "test-maker": {"assessment_ready", "changes_requested", "blocked"},
        "implementor": {"implemented", "needs_input", "blocked"},
        "reviewer": {"approved", "changes_requested", "needs_input"},
        "qa": {"pass", "defects_found", "blocked"},
        "devops": {"prepared", "needs_input", "blocked"},
        "infrastructure-reviewer": {"approved", "changes_requested", "needs_input"},
        "deployment-agent": {"deployed_healthy", "failed", "blocked", "approval_invalid"},
    },
}

STATE_VERSION = 4
TEST_CRITICALITIES = {"critical", "standard", "low"}
TEST_CRITICALITY_RANK = {"low": 0, "standard": 1, "critical": 2}
TEST_DISPOSITIONS = {"add", "update", "reuse", "none"}
ADAPTIVE_LEDGER_LIMIT = 100
RESULT_LEDGER_LIMIT = 1000
ADAPTIVE_TEXT_LIMIT = 500
COVERAGE_MODES = {
    "none",
    "targeted",
    "changed-lines",
    "branch",
    "critical-branches",
    "existing-suite",
    "full",
    "repository",
}
TEST_ASSESSMENT_FIELDS = {
    "plan_revision",
    "acceptance_revision",
    "test_criticality",
    "test_disposition",
    "scope_fingerprint",
    "assessed_paths",
    "tested_invariants",
    "existing_tests",
    "coverage_mode",
    "alternative_evidence",
    "residual_risks",
    "disproportionate_cost",
    "stronger_alternative_evidence",
    "rationale",
    "follow_up",
    "reuse_proof",
    "test_plan",
    "item_id",
    "item_revision",
}
TEST_DOWNSTREAM_ROLES = {
    "test-maker",
    "implementor",
    "reviewer",
    "qa",
    "browser-qa",
    "security-reviewer",
    "contract-qa",
    "deployment-agent",
    "youtrack-operator",
}
EPIC_ITEM_GATES = {"test-maker", "implementor", "reviewer", "architecture", "qa", "product-outcome"}

PROFILE_ROLE_PHASES: Dict[str, Dict[str, Set[str]]] = {
    "implementation": {"architecture-guardian": {"plan", "diff"}},
    "bugfix": {
        "architecture-guardian": {"plan", "diff"},
        "bug-investigator": {"evidence", "rca"},
    },
    "task-creation": {},
    "epic-implementation": {
        "architecture-guardian": {"plan", "diff"},
        "project-manager": {"scope", "reconcile"},
        "product-manager": {"scope", "outcome"},
    },
}


for profile in PROFILE_ROLE_VERDICTS:
    PROFILE_ROLE_VERDICTS[profile]['effort-estimator'] = {'estimated', 'needs_input', 'needs_research'}
    PROFILE_ROLE_VERDICTS[profile]['youtrack-operator'] = {
        'published', 'synced', 'partially_applied', 'no_changes', 'authorization_required', 'blocked'
    }
    PROFILE_ROLE_VERDICTS[profile]['task-assessor'] = {'assessed', 'needs_evidence', 'needs_input'}
    if profile != 'task-creation':
        PROFILE_ROLE_VERDICTS[profile].update({
            'data-migration-reviewer': {'approved', 'changes_requested', 'needs_input'},
            'reliability-reviewer': {'approved', 'changes_requested', 'needs_input'},
            'browser-qa': {'pass', 'defects_found', 'blocked'},
            'security-reviewer': {'approved', 'changes_requested', 'needs_input'},
            'contract-qa': {'pass', 'defects_found', 'blocked'},
        })
TEST_DOWNSTREAM_ROLES.update({'data-migration-reviewer', 'reliability-reviewer', 'effort-estimator', 'youtrack-operator'})
