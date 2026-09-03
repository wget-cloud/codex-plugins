# Evaluation and release

## Corpus

Use `evals/corpus.json` as the versioned sanitized baseline. Add a scenario only when it contains no raw prompt, production log, credential, cookie, token, or customer data. Each scenario defines intent, expected routing, approval boundary, invariant outcomes, and compatibility platforms rather than exact generated wording.

## Shadow evaluation

For a new or materially changed skill, role, hook, model route, or public contract, execute the corpus against the baseline and candidate in isolated temporary workspaces. Record task success, approval/security/path violations, latency, and token/cost proxy.

Acceptance requires zero approval, security, privacy, and path-isolation regressions and task success no worse than baseline. A cost or latency regression is accepted only when the proposal and Gate 2 show a material quality benefit.

Run `scripts/run_shadow_eval.py` with a sanitized corpus, distinct clean Git worktrees at distinct bound revisions, and one adapter command for each root. Each adapter receives `{"scenario": ...}` on standard input and returns exactly `success`, `actual_route`, `latency_ms`, `token_cost_proxy`, and `invariants`. `invariants` must have exactly the scenario's required-invariant keys and boolean values; the candidate route must equal `expected_route` and every candidate invariant must be true. The runner rejects malformed or oversized output, timeouts, raw prompt/log/credential-like fields, dirty/shared roots, same or missing revisions, and missing or extra fields. Its report contains only hashes, revisions, metrics, uncertainty, and failure labels. Use `make shadow-eval` to verify the CLI contract and `make eval-test` for corpus/runner tests.

This skill begins and remains with `allow_implicit_invocation: false`. A later separately approved maintenance proposal may enable implicit selection only after shadow evaluation and a passing new-task smoke.

External evidence is sanitized and verified separately from shadow evaluation. Use `scripts/verify_external_evidence.py` and `evidence.schema.json` to accept only exact-key, bounded CI/runtime/smoke records: fresh successful GitHub `validate` CI bound to the subject commit; an installed and enabled runtime (never cache-only, absent, or version-mismatched); and, when supplied, a successful distinct Codex smoke for that runtime's exact plugin version and commit. Unknown fields, nested extras, sensitive keys or credentialed URLs are rejected. The verifier returns only acceptance, bounded errors, hashes, and opaque identifiers; do not store raw external output in artifacts or hook state.

Candidate CI belongs after the push and is not a pre-Gate-2 assertion. Record its sanitized evidence against the release ledger before installing the exact approved plugin version. Installation must be followed by installed/enabled runtime inventory and a distinct new-task smoke before tag creation; GitHub Release creation follows only the approved tag. Any failure is recovery evidence, not authority to retry or skip a phase.

## Release profile

- macOS: validate and smoke the installed plugin on the active host;
- Ubuntu: require the repository GitHub Actions run for the pushed commit to pass;
- Windows: run protocol fixtures that validate `commandWindows`, path normalization, and approval parsing.

After green CI, reinstall exact changed plugins and create a separate Codex smoke task. Only a passing smoke permits tags and GitHub Releases. Release notes contain item IDs, commits, SemVer rationale, checks, compatibility results, smoke verdict, known limitations, and no raw evidence payloads.

Use patch for compatible repair, minor for a compatible capability such as a skill or role, and major for incompatible routing, contract, removal, or behavior. Versions are plain SemVer without build metadata.

The unpublished maintainer bundle is versioned `0.2.0`: it introduces additive evidence/semantic-validation capabilities and changes the pre-1.0 delivery and routing contract. Marketplace metadata remains unchanged until an approved delivery.
