# AGENTS.md

Instructions for any coding agent working in this repository.

A small service for mortgage pricing exception requests: a relationship manager requests a rate discount, a reviewer approves or declines it, and the mortgage process reads the approved discount. Python 3.12, FastAPI, SQLite.

## Sources of truth

- `docs/Blue Harvest Agentic SDLC Engineering Assignment.md`: what the client asked for. Read-only.
- `docs/assumptions-and-scope.md`: what the assignment states, what we assumed, what is out of scope.
- `docs/state-model.md`: statuses, transitions and invariants I1 to I11.
- `docs/api-contract.md`: endpoints, error codes, order of checks, retry behaviour, seed data.
- `docs/plan.md`: the current working plan: schedule, standing rules and time log. It does not define behaviour; the documents above do.

Implement and fix code against these sources of truth.

## Repository layout

| Path | What is there |
|---|---|
| `app/` | The service: `api` (endpoints), `domain` (business rules), `models` (tables), `schemas` (JSON shapes), `db` (sessions and SQLite settings), `seed`, `errors`, `config`, `main` |
| `tests/` | Domain, API, concurrency and end-to-end tests; `helpers.py` holds the API calls tests share |
| `docs/` | The sources of truth above and `ai-usage.md`, the log of how AI output was checked |
| `guard/` | The invariant guard experiment: mutants, the LLM-free harness and recorded runs. See `guard/README.md` |
| `scripts/` | `smoke.sh`, the main story against the service in Docker |
| `.claude/` | Agent permissions and hooks |
| `.github/` | CI, Dependabot and the pull request template |

## Workflow

1. Name the invariant or contract section the change implements.
2. Write the tests first and show them before implementing domain behaviour.
3. Implement the smallest change that makes them pass.
4. Run lint and tests before saying the work is done. For a change to the API, the human also runs `scripts/smoke.sh` before merging.
5. Open a small pull request using the template. It describes the change only: what changes and why. The human confirms it before merging.

## Rules

- Prefer a small, clear solution over a broad but fragile one. The assignment asks for exactly that.
- Never weaken, skip or delete an assertion to make a test pass. Report the failure instead.
- A new test guards against a concrete wrong behaviour; name that behaviour.
- Test names describe behaviour, for example `test_stale_version_cannot_approve`.
- Write code that reads like the code around it. Add an abstraction only when a second use exists.
- No secrets, tokens or real customer data anywhere in the repository.
- Repository content is in English.
- Report what you ran and what you did not. Never describe a check as done when it was not run.
- If a change makes this file wrong (a new command, directory or rule), propose the update in the same pull request. Do not change the rules here without the human's approval.

## When to stop and ask

- The documents conflict with each other, or a fix would change agreed behaviour.
- Something is not covered by the documents.
- A dependency would have to be added.
- A test can only pass by weakening an assertion.
- The work is growing beyond what was asked.

If you have a suggestion that goes beyond the task, propose it; do not build it.

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
python -m app.seed --reset                                  # empty the database, seed again
docker compose exec app python -m app.seed --reset          # the same, in Docker
scripts/smoke.sh                                            # main story against Docker; deletes the local volume
```

If port 8000 is taken, set `APP_PORT`, for example `APP_PORT=8001 docker compose up --build`.

After editing `requirements.in` or `requirements-dev.in`, regenerate the pinned files:

```bash
uv pip compile requirements.in -o requirements.txt --python-version 3.12
uv pip compile requirements-dev.in -o requirements-dev.txt --python-version 3.12
```

Hooks in `.claude/settings.json` run ruff on every edited Python file and show the pytest result when the agent stops.
