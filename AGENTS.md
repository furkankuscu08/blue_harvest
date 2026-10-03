# AGENTS.md

Instructions for any coding agent working in this repository.

A small service for mortgage pricing exception requests: a relationship manager requests a rate discount, a reviewer approves or declines it, and the mortgage process reads the approved discount. Python 3.12, FastAPI, SQLite.

## Sources of truth

- `docs/state-model.md`: statuses, transitions and invariants I1 to I11.
- `docs/api-contract.md`: endpoints, error codes, order of checks, retry behaviour, seed data.
- `docs/assumptions-and-scope.md`: what the assignment states, what we assumed, what is out of scope.
- `docs/plan.md`: the frozen working plan. Where it disagrees with the documents above, they win (for example, `NOT_PENDING` is now `INVALID_STATE`).

Implement and fix code against these sources of truth. If the documents conflict with each other, or a fix would require changing the agreed behaviour, stop and ask.

## Workflow

1. Name the invariant or contract section the change implements.
2. Write the tests first and show them before implementing domain behaviour.
3. Implement the smallest change that makes them pass.
4. Run lint and tests.
5. Open a small pull request using the template. Fill in all three sections. "How I verified it" lists only what the human actually did in this change (read, ran, tried, rejected); never invent checks. The human confirms it before merging.

## Rules

- Never weaken, skip or delete an assertion to make a test pass. Report the failure instead.
- Do not add a dependency without asking.
- No secrets, tokens or real customer data anywhere in the repository.
- Repository content is in English.
- If something is not covered by the documents, ask before adding it.
- Test names describe behaviour, for example `test_stale_version_cannot_approve`.

## Database access

- An endpoint that changes data uses only the write session; its checks and its writes run in that one transaction.
- Build the response before commit and return it only after the commit succeeds. Do not read ORM objects after commit: with `expire_on_commit` they are reloaded and may show someone else's later change.

## Commands

```bash
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -r requirements-dev.txt                      # set up
pytest                                                      # tests
ruff check . && ruff format --check .                       # lint
pip-audit -r requirements-dev.txt --no-deps --disable-pip   # dependency audit
uvicorn app.main:create_app --factory --reload              # run locally on :8000
docker compose up --build                                   # run in Docker
```

After editing `requirements.in` or `requirements-dev.in`, regenerate the pinned files:

```bash
uv pip compile requirements.in -o requirements.txt --python-version 3.12
uv pip compile requirements-dev.in -o requirements-dev.txt --python-version 3.12
```

Hooks in `.claude/settings.json` run ruff on every edited Python file and show the pytest result when the agent stops.
