# AGENTS.md

Instructions for any coding agent working in this repository.

A small service for mortgage pricing exception requests: a relationship manager requests a rate discount, a reviewer approves or declines it, and the mortgage process reads the approved discount. Python 3.12, FastAPI, SQLite.

## Sources of truth

- `docs/state-model.md`: statuses, transitions and invariants I1 to I11.
- `docs/api-contract.md`: endpoints, error codes, order of checks, retry behaviour, seed data.
- `docs/assumptions-and-scope.md`: what the assignment states, what we assumed, what is out of scope.
- `docs/plan.md`: the frozen working plan. Where it disagrees with the documents above, they win (for example, `NOT_PENDING` is now `INVALID_STATE`).

If code and these documents disagree, stop and ask. Do not silently pick one.

## Workflow

1. Name the invariant or contract section the change implements.
2. Write the tests first and show them before implementing domain behaviour.
3. Implement the smallest change that makes them pass.
4. Run lint and tests.
5. Open a small pull request using the template. Fill in both sections. "How I verified it" lists only what the human actually did in this change (read, ran, tried, rejected); never invent checks. The human confirms it before merging.

## Rules

- Never weaken, skip or delete an assertion to make a test pass. Report the failure instead.
- Do not add a dependency without asking.
- No secrets, tokens or real customer data anywhere in the repository.
- Repository content is in English.
- If something is not covered by the documents, ask before adding it.
- Test names describe behaviour, for example `test_stale_version_cannot_approve`.

## Commands

Added together with the project skeleton.
