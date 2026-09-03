# Approval and delivery contract

## Gate 1 marker

After read-only Auditor and Architect artifacts, end one attempted response with exactly one final line:

```text
WGC_MAINTENANCE_PROPOSAL: {"baseline_head":"<40-hex HEAD>","dirty_fingerprint":"<64-hex fingerprint from hook context>","items":[{"id":"M-001","summary":"<brief>","severity":"medium","benefit":"<expected benefit>","effort":"<estimate>","evidence":["<source or reproduction>"],"paths":["<exact file or directory/>"],"acceptance":["<criterion>"],"tests":["<command or scenario>"],"shadow_eval":["<baseline/candidate plan or reason not required>"],"risks":["<risk or explicit none>"],"compatibility":"<impact>","depends_on":[],"semver":"patch","self_change":false}]}
```

Paths are repository-relative, may name a file or a directory ending `/`, and may not contain glob syntax or `..`. IDs are unique, dependencies must exist and be acyclic, severity is `critical|high|medium|low|info`, and SemVer impact is `none|patch|minor|major`. The complete canonical proposal, including evidence, acceptance, test, shadow-eval, risk, compatibility, scope, and self-change declarations, is bound into the session-scoped proposal ID and a SHA-256 binding hash. The hook persists only enforcement fields: IDs, normalized paths, dependencies, `self_change`, baseline hashes, timestamps, and non-reversible sentinel hashes. It never persists proposal prose or raw secret-like text.

```text
APPROVE_WGC_PLUGIN_CHANGE=<proposal-id>:<comma-separated-item-ids>
```

Only a later user message can approve it. The initial request, agent text, tool output, a stale ID, unknown item, changed HEAD, changed baseline dirty path, or approval from another session grants nothing.

## Gate 2 marker

After implementation, independent review, QA, and all local/external evidence, end one attempted response with:

```text
WGC_MAINTENANCE_DELIVERY: {"proposal_id":"<id>","worktree_hash":"<64-hex live hash>","target":"origin/main","commits":[{"message":"<atomic subject>","paths":["<approved path>"]}],"versions":{"<plugin>":"<plain SemVer>"},"plugins":["<plugin>"],"ci_evidence":true,"runtime_evidence":true}
```

The hook verifies the live worktree, selected paths, role ledger, target, evidence flags, SemVer, and commit plan. It registers a delivery ID and requests:

```text
APPROVE_WGC_PLUGIN_DELIVERY=<delivery-id>
```

Only a later user message can approve delivery. The approval is invalid when diff, local/remote baseline, commit plan, target, plugin list, or versions change.

External CI, runtime inventory, and smoke records are validated with `references/evidence.schema.json` and `scripts/verify_external_evidence.py` before their boolean delivery evidence is asserted. The verifier accepts only a fresh successful `validate` CI result bound to the exact delivery commit, installed-and-enabled runtime inventory (never cache-only), and a successful distinct-task Codex smoke when smoke evidence is provided. Hook state retains only subject-bound SHA-256 evidence identifiers, never raw CI output, runtime output, logs, tokens, or credentials.

The marker's legacy `ci_evidence` and `runtime_evidence` booleans attest only that preflight evidence collection is planned and available; they never claim future candidate CI, installation, or smoke success. Gate 2 starts the release ledger at `approved` with no release transitions. It advances only in this order: `staged/committed` → `push-pending-remote-verification` → `candidate-ci-verified` for the exact pushed SHA → exact plugin installed and enabled → `smoke-passed` from a verified distinct task → tag → GitHub Release. A rejected evidence record, failed command, replay, or unexpected phase freezes delivery and requires a recovery proposal.

## Rolling delivery state

Gate 2 records a SHA-256 delivery chain over the exact `HEAD`, complete Git index, tracked and untracked worktree snapshot, `origin/main`, and previously completed delivery transitions. Before every approved delivery command, the hook recomputes and compares that state. A command becomes the next link only after a successful PostToolUse result and its action-specific postconditions are verified; failed commands and unexpected state changes never advance the chain. Any unrelated staged, unstaged, untracked, HEAD, or remote-baseline change invalidates delivery and requires a new delivery proposal.

If a PostToolUse event is lost, the hook may reconcile only a pending approved `git add` or `git commit` before a later delivery command, and only when the live local state independently satisfies that action's exact postcondition and the stored chain snapshot. It never reconciles pushes, installs, tags, or releases this way; those transitions require their normal post-tool and external-evidence gates.

## Delivery restrictions

- stage only approved paths and inspect the cached diff before each commit;
- use ordinary commits and `git push origin main`; never force;
- stop if local `origin/main` no longer equals the approved remote baseline;
- after push wait for green GitHub CI;
- reinstall only the listed `<plugin>@wget-cloud` packages;
- run smoke in a newly created Codex task and wait for its verdict;
- tag successful bundles `<plugin>-v<version>` and create one GitHub Release per tag;
- do not tag or release a CI/smoke failure; create a recovery proposal instead.
