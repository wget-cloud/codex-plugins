---
name: wgc-plugin-maintenance
description: Audit, repair, and evolve the wget-cloud/codex-plugins marketplace through item-level user approvals, independent test/review/QA roles, runtime evidence, and release gates. Activate only when the user explicitly invokes `$wgc-plugin-maintenance`. Do not use for Wget Cloud application code, generic Codex questions, or explanation-only requests outside this repository.
---

# WGC Plugin Maintenance

Maintain only the `wget-cloud/codex-plugins` repository. Initial activation is explicit-only: require `$wgc-plugin-maintenance`; an ordinary request about plugins, hooks, skills, or maintenance does not activate this workflow. A later implicit-routing promotion requires separate approval, shadow evaluation, and a passing new-task smoke.

## Load context

1. Read repository `AGENTS.md`, root `README.md`, and the manifest/README/SKILL.md of every affected bundle and skill.
2. Read [workflow.md](references/workflow.md), [agent registry](references/agents/index.md), and [approval-and-delivery.md](references/approval-and-delivery.md).
3. Read [audit-and-capabilities.md](references/audit-and-capabilities.md) for every run because a full audit and `Capability gaps` result are mandatory.
4. Read [evaluation-and-release.md](references/evaluation-and-release.md) when a skill, role, model route, hook, public contract, install behavior, or release is in scope.
5. Treat current code, tests, manifest, hook protocol, installed runtime, and GitHub CI as evidence. Do not infer availability from documentation alone.

## Invariants

- Before Gate 1, perform only read-only inspection and planning. End the proposed change set with the exact proposal marker defined in the approval contract; the hook registers it and returns the approval ID.
- Implement only item IDs selected by the user. Any new path, changed baseline, protected-test edit, or overlapping user change invalidates the approval and requires a revised proposal.
- Always use separate Auditor, Architect, Test-maker, Implementor, Reviewer, and QA assignments. Never combine roles whose independence is part of the evidence.
- Test-maker owns protected tests. Implementor may not change them. Reviewer and QA are repository read-only.
- Evaluate the full repository on every run, but do not turn unrelated findings into unapproved edits.
- Every audit reports `Capability gaps`. A new skill, role, model route, or plugin requires evidence that extending an existing component is insufficient.
- This skill remains explicit-only. Implicit activation is a later separately approved capability change after shadow eval and new-task smoke.
- Do not commit, push, tag, create a GitHub Release, reinstall, or create a smoke task before Gate 2.
- Preserve user work. Never stash, reset, checkout, rebase, merge, clean, force-push, or rewrite history automatically.
- Store no raw prompts, tool output, logs, credentials, cookies, tokens, or customer data in repository or hook state.

## Execute

1. **Audit.** Record Git identity/dirty baseline; inspect every bundle, skill, hook, validator, CI, latest CI state, installed plugin versions, and lifecycle smoke evidence. Validate only sanitized CI/runtime/smoke records through the external-evidence verifier; cache-only inventory is not installed-runtime evidence. If GitHub or runtime evidence is unavailable, note it and disable delivery.
2. **Findings.** Auditor returns every evidence-backed finding with severity, benefit, effort, compatibility risk, and reproduction or source.
3. **Design.** Architect turns findings into independent items with severity, benefit, effort, evidence, dependencies, exact paths, acceptance criteria, tests, shadow-eval plan, risks, compatibility, SemVer impact, and `self_change`.
4. **Gate 1.** Present all items without a count limit. Emit `WGC_MAINTENANCE_PROPOSAL` exactly as specified in [approval-and-delivery.md](references/approval-and-delivery.md), then repeat the registered approval token supplied by the hook. Stop until the user approves selected item IDs.
5. **Test baseline.** Test-maker writes executable regression/contract tests inside approved paths and returns protected paths plus SHA-256 hashes.
6. **Implementation.** Implementor changes one approved dependency slice at a time, preserves protected tests, updates relevant docs, and runs immediate focused coverage/checks.
7. **Review and QA.** Reviewer inspects the exact diff; QA runs adversarial approval, path, privacy, compatibility, install, and regression scenarios. Findings re-enter the same role sequence. Scope expansion returns to Gate 1.
8. **Integration.** Run official skill/plugin validators, `make validate`, `git diff --check`, corpus validation, shadow eval, macOS runtime checks, Ubuntu CI evidence, and Windows command-contract fixtures.
9. **Gate 2.** When all evidence is available, emit the exact delivery marker. After the hook registers it, show the exact commit/version/push/install/smoke/release plan and stop for approval.
10. **Delivery.** Verify `origin/main` did not move; create only approved atomic commits; push non-force to `origin/main`; verify the remote candidate SHA with fresh CI evidence; reinstall the exact listed plugin only after that verification; verify installed/enabled runtime plus a distinct new-task smoke; then create per-bundle `<plugin>-v<version>` tags and GitHub Releases. A command, CI, runtime, or smoke failure freezes delivery for a new recovery proposal and never auto-reverts.

## Ready condition

Finish only when selected items meet acceptance criteria, protected tests are unchanged by Implementor, all role verdicts and required checks pass, dirty-path isolation is preserved, documentation and SemVer are correct, and delivery either completed with new-task smoke or is explicitly reported as locally ready but blocked before Gate 2.
