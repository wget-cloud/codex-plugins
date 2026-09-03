# Audit and capability evolution

## Finding contract

Each finding contains a stable item ID, evidence, severity, benefit, effort, compatibility risk, affected components, reproduction or source, and the consequence of leaving it unchanged. Separate observed defects from optional improvements.

Finding prose is user-facing audit material, not hook state. Gate registration retains only the minimal enforcement structure and hashes that bind the full canonical proposal; never place raw prompts, evidence, reproduction output, credentials, or secret-like values in persisted state.

## Capability gaps

Every audit ends with this section, including when the result is `none`.

A capability proposal must prove:

1. a reusable gap exists in representative requests;
2. an existing skill/role/plugin cannot absorb it without weakening discovery, cohesion, independence, or permission boundaries;
3. trigger and exclusion rules do not steal unrelated requests;
4. ownership, maintenance cost, compatibility, SemVer, staged activation, tests, and migration are defined.

Choose the smallest viable boundary:

- improve an existing role when responsibility and verdict remain the same;
- create a role only for a distinct responsibility, permission boundary, or independent verdict;
- improve an existing skill when the workflow remains cohesive;
- create a skill for a separate reusable workflow;
- create a plugin only for a distinct lifecycle, dependency, trust, or installation boundary.

Merge, deprecation, and removal proposals identify all callers and consumers, provide a compatibility period and migration plan, and use breaking SemVer when public behavior becomes incompatible.

## Model routes

Change a role's model lane or reasoning effort only with a benchmark over the versioned eval corpus. Report task success, safety violations, latency, token/cost proxy, and uncertainty. Safety and scope non-regression are hard gates; a weighted score cannot compensate for an approval or isolation regression.
