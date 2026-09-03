# Evaluation and release

## Corpus

Use [evals/corpus.json](evals/corpus.json) as the versioned sanitized baseline. Add a scenario only when it contains no raw prompt, production log, credential, cookie, token, or customer data. Each scenario defines intent, expected routing, approval boundary, invariant outcomes, and compatibility platforms rather than exact generated wording.

## Shadow evaluation

For a new or materially changed skill, role, hook, model route, or public contract, execute the corpus against the baseline and candidate in isolated temporary workspaces. Record task success, approval/security/path violations, latency, and token/cost proxy.

Acceptance requires zero approval, security, privacy, and path-isolation regressions and task success no worse than baseline. A cost or latency regression is accepted only when the proposal and Gate 2 show a material quality benefit.

Run `scripts/run_shadow_eval.py` with a sanitized corpus, distinct revision-bound `--baseline-root` and `--candidate-root`, and one adapter command for each root. Each adapter receives `{"scenario": ...}` on standard input and returns only `success`, optional `latency_ms`, optional `token_cost_proxy`, and violation booleans as JSON. The runner rejects malformed results, timeouts, raw prompt/log/credential-like fields, shared roots, and missing Git revisions; its report contains only hashes, revisions, metrics, and failure labels. Use `make shadow-eval` to verify the CLI contract and `make eval-test` for corpus/runner tests.

This skill begins and remains with `allow_implicit_invocation: false`. A later separately approved maintenance proposal may enable implicit selection only after shadow evaluation and a passing new-task smoke.

External evidence is sanitized and verified separately from shadow evaluation. Use `scripts/verify_external_evidence.py` and `evidence.schema.json` to bind successful, fresh CI to the exact commit and to distinguish an installed/enabled runtime from a cache-only, absent, or version-mismatched bundle. Do not store raw external output in artifacts or hook state.

Candidate CI belongs after the push and is not a pre-Gate-2 assertion. Record its sanitized evidence against the release ledger before installing the exact approved plugin version. Installation must be followed by installed/enabled runtime inventory and a distinct new-task smoke before tag creation; GitHub Release creation follows only the approved tag. Any failure is recovery evidence, not authority to retry or skip a phase.

## Release profile

- macOS: validate and smoke the installed plugin on the active host;
- Ubuntu: require the repository GitHub Actions run for the pushed commit to pass;
- Windows: run protocol fixtures that validate `commandWindows`, path normalization, and approval parsing.

After green CI, reinstall exact changed plugins and create a separate Codex smoke task. Only a passing smoke permits tags and GitHub Releases. Release notes contain item IDs, commits, SemVer rationale, checks, compatibility results, smoke verdict, known limitations, and no raw evidence payloads.

Use patch for compatible repair, minor for a compatible capability such as a skill or role, and major for incompatible routing, contract, removal, or behavior. Versions are plain SemVer without build metadata.

Bundle `0.3.0` adds fail-closed standard-tier preflight and the `economy` Luna/low route while preserving explicit-only activation and approval gates.
