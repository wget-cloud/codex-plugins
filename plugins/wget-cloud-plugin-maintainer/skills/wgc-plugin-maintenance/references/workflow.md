# Maintenance workflow

State progresses as:

`discovered → audited → proposed → change_approved → tested → implemented → reviewed → verified → delivery_proposed → delivery_approved → pushed → smoke_passed → released`

After Gate 2, delivery uses an evidence-bound ledger: `approved → staged/committed → push-pending-remote-verification → candidate-ci-verified → installed → smoke-passed → tagged → released`. A successful local push exit code is not remote verification; only fresh sanitized CI evidence for the exact pushed SHA may advance it. A failed command or rejected/stale/replayed evidence freezes the ledger for recovery.

## Full audit

Every run examines the whole repository even when the user reports one defect. Audit is read-only and includes repository structure, manifests, skill routing, role registries, hooks, validators, CI configuration/status, installed versions, lifecycle smoke evidence, documentation drift, security/privacy boundaries, duplicated capability, and obsolete components.

Unrelated findings remain report-only until selected in Gate 1. Missing GitHub or installed-runtime evidence does not block local work, but prevents Gate 2. Verify sanitized records against `evidence.schema.json`: CI must be fresh, successful, and bound to the exact subject commit; runtime must be installed and enabled rather than cache-only, absent, or version-mismatched; smoke evidence, when required, must come from a distinct Codex task.

## Role order

Auditor and Architect run before Gate 1. Test-maker and Implementor run after approval and never share write ownership. Reviewer and QA run after implementation and are read-only. Blocking findings return to their author; every changed diff invalidates previous Reviewer and QA verdicts.

The required independent sequence is `auditor → architect → test-maker → implementor → reviewer → QA`; a role result is valid only after its bound start event, assigned revision, identity, and predecessor verdict.

Use the exact assignment envelope and model lanes from the [agent registry](agents/index.md). Two write roles never run concurrently. The Orchestrator independently verifies revision, diff, commands, protected-test hashes, role output, and user authority.

## Dirty state

Fingerprint every pre-existing dirty path. Audit may continue, but an item may not include a path that overlaps that baseline. Do not stash or clean. If a user changes an approved path during execution, stop and create a revised proposal.

## Recovery

CI, push, install, or smoke failure produces evidence and a new recovery item. Do not auto-revert. A recovery mutation requires a fresh change approval, and its delivery requires a fresh delivery approval.
