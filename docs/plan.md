# Working plan

The current plan, last updated on 2026-10-04 after day 5. Earlier versions are in the git history of this file; the reasons for the larger changes are listed under [Changes and why](#changes-and-why).

The plan covers how the work is organised. What the service does is defined in [state-model.md](state-model.md), [api-contract.md](api-contract.md) and [assumptions-and-scope.md](assumptions-and-scope.md); those documents win over this one.

## Stack

| Area | Choice | Why / production note |
|---|---|---|
| Language | Python 3.12 | The language I know. Team knows Java/C#; the assignment allows any. |
| API | FastAPI + Pydantic v2 | OpenAPI and Swagger UI for free, which doubles as the "explore" instructions. |
| Persistence | SQLite (file) via SQLAlchemy 2.0 | Zero setup for reviewers. Constraints and transactions are real. Production: Postgres + Alembic, with the concurrency tests re-validated there; not just a connection string change. |
| Running it | `docker compose up` (Dockerfile + single-service compose, volume for the SQLite file) | The one run path shown to reviewers; same result on any machine. |
| Development | `uv venv` + `requirements.txt` / `requirements-dev.txt` | Fast test loop and editor support; also the fallback for running without Docker. Direct dependencies live in `requirements.in`; `uv pip compile` produces the fully pinned `requirements.txt`. |
| Tests | pytest + FastAPI TestClient | Domain tests, API tests against a real SQLite file, concurrency tests. |
| Quality | ruff, GitHub Actions CI (tests via the venv path, plus image build and health check) | Deterministic gates that agents cannot talk their way past; keeps both paths working. |
| UI | One static page (HTML, CSS, plain JavaScript) served by the same app | No frontend build; it uses the same public API. |

SQLite rules: `PRAGMA foreign_keys=ON` and `busy_timeout` on every connection, WAL mode, short write transactions opened with `BEGIN IMMEDIATE`. WAL does not give multiple concurrent writers; that limit is accepted.

## Schedule

Days 1 to 5 are done; the API is complete. Hours for days 6 to 10 are estimates.

| Day | Hours | Outcome | Done when |
|---|---|---|---|
| 1 | 4 | Assumptions and scope, state model, API contract | Done |
| 2 | 3 | Process scaffolding, skeleton, Docker, CI, proof that `BEGIN IMMEDIATE` works | Done |
| 3 | 3 | Domain core, test-first; invariant guard spike with the first recorded run | Done |
| 4 | 3 | Identity, errors, seed and reset, create with idempotency, get, decide, approved discount | Done |
| 5 | 3 | Revise, the full decline-revise-approve story, concurrency test at API level, list endpoints | Done |
| 6 | 3 | UI and a draft of the demo script | The main story can be completed on screen |
| 7 | 3 | Idempotent replay experiment | The result is recorded and can be verified without an LLM |
| 8 | 2 | Issue list and checklist | The list is closed and a clean Docker run is confirmed |
| 9 | 3 | README, contract clean-up, recorded demo | Someone else can follow the story from the README alone |
| 10 | 2 | Fresh-clone rehearsal, walkthrough rehearsal | The buffer is still there |

Spent so far, including 4 hours of planning: 20 hours. Remaining estimate: 13 hours. Projected total: about 33 hours.

### Day 6: UI

One page without a build step. It should be pleasant to use, not only functional.

- Choose who to act as; the acting user is always visible.
- List of applications and requests; request detail with every revision and decision.
- Create, revise, approve and decline.
- The discount shows its unit, a submit cannot be sent twice, and an error says what to do next.
- The UI sends the version the user sees. After `STALE_VERSION` the user looks at the request again; nothing is resubmitted automatically.
- One create submission is one idempotency key plus one payload; a retry resends exactly that pair. Changing the acting user discards an open create form and its key.

The demo script for the UI is drafted while the UI is built: create, decline, revise, act with a stale version in a second tab, approve, read the approved discount as the mortgage process. Automated browser tests are out of scope because of their setup and maintenance cost within this budget.

### Day 7: agent experiment

The invariant guard is described in [guard/README.md](../guard/README.md): an agent writes regression tests against a deliberately broken rule (a mutant), and an LLM-free harness checks whether those tests catch it. The first run, stale approval, is recorded.

- The second experiment is idempotent replay broken: the same key and content does not return the first response. The unique constraint still prevents a second row, so the visible failure is a `409`.
- One mutant, a neutral prompt and at most two generation runs. The result is recorded as it comes out; the prompt is not tuned until it succeeds.
- The harness gets no new features. It changes only for a defect that makes its result unreliable.
- Controls: the agent may only add files under `tests/`, never merges, and is advisory only. Its tests run in a container with no secrets, no network and a time limit. CI stays the merge gate.
- Residual risks, for the README: missed rules, false alarms, tests that pass for the wrong reason, prompt injection through diff content.
- It is a controlled experiment on deliberately created test gaps and is reported as such: two examples are evidence for two scenarios, not a general success rate.

### Day 8: checklist

Problems found on days 6 and 7 are written down as GitHub issues and fixed on day 8. Only what is on the list is fixed; new ideas go to the README as next steps.

1. A clean `docker compose up` followed by `scripts/smoke.sh`.
2. The written UI script from start to end, including the two-tab stale version.
3. Every error code from the contract produced once in the UI, with a message a user can act on.
4. A seed reset while the UI is open.
5. Small open items: the ruff hook that removes a just-added import, the ADR reference in `assumptions-and-scope.md`, and the transaction race experiment as a script in the repository.

### Day 9: README and documents

- "Try it in five minutes": a few commands and one address.
- Deliberate assumptions, labelled as ours; real time spent; a short "with more time" section; what changes in production, including PostgreSQL.
- A traceability table with one line per invariant: rule, test.
- How this way of working carries over to a regulated client.
- `api-contract.md` loses its repetitions, to about 200 lines. The order of checks and the retry rules stay.
- The demo script is run and the result recorded.

No new behaviour from day 9 on. Idempotent retry is proven at API level (an automated test and a step in the smoke script); a lost response cannot be produced reliably by hand in a browser, and the README lists this as a known limit.

## Standing rules

- Default answer to "should we add it" is no; record it under deliberate scope choices.
- I can explain every line of the backend and its tests in the walkthrough. For the UI I can explain what it does and why it is designed that way, not every line.
- Small, meaningful commits and pull requests; an agent reviews, I approve the merge.
- Review depth follows risk: transactions, idempotency, concurrency and the harness get a full review; UI layout and simple lists a short one.
- No new test or mutant without a concrete wrong behaviour it guards against.
- If time runs short, cut first: optional extra agent runs, then UI presentation detail.
- Never cut: run and test instructions, assumptions, time spent, both bonuses with meaningful verification evidence, isolation of agent-written tests.
- [ai-usage.md](ai-usage.md) is written as the work happens.
- Log time spent per day below.

## Changes and why

**Before day 1 (2026-10-03), three review rounds with other agents.**

- The mutant "duplicate create on retry" could not work, because the unique constraint already prevents a second row. It became "idempotent replay broken".
- A retry of a create must keep the original payload as well as the key.
- The agent spike moved from day 2 to day 3: on day 2 there was no domain code to break.

**After day 3 (2026-10-03), a scope review.**

- The API is built in vertical slices, and create and idempotency together, because they share one transaction.
- The authorisation mutant and a `.claude/agents/` subagent were dropped: the mutant repeated the first experiment's shape, and a subagent would let the session that writes the code also guard it.
- No ADRs: the revision decision is explained in `assumptions-and-scope.md`, section B, and the rest in the README.
- The estimate rose from about 28 to about 33 hours.

**After day 5 (2026-10-04), a look back at the first five days.**

- The backend, the tests and `guard/` stay as they are. The cost was in the process: review and mutant rounds are now limited to concrete risks.
- The smoke script moved into the repository as `scripts/smoke.sh`. It is the API demo and gets no new checks.
- Day 8 became a fixed checklist; "hardening" had no end.
- The UI is treated as a real deliverable, not as the first thing to cut.
- This file was rewritten to show only the current plan. Decisions about behaviour that it used to repeat, some of them outdated, now live only in the documents named at the top.

## Time log

| Date | Hours | What |
|---|---|---|
| 2026-10-02 to 03 | 4 | Planning and three review rounds |
| 2026-10-03 | 4 | Day 1: assumptions and scope, state model, API contract, review rounds |
| 2026-10-03 | 3 | Day 2: process scaffolding, project skeleton, Docker, CI, SQLite concurrency proof |
| 2026-10-03 | 3 | Day 3: domain core (test-first), invariant guard spike with an LLM-free harness and the first recorded run |
| 2026-10-04 | 3 | Day 4: first API slice (identity, errors, seed and reset, create with idempotency, decide, approved discount, first end-to-end test), two test review rounds, AI usage log restructured |
| 2026-10-04 | 3 | Day 5: revise, the full decline-revise-approve story, API concurrency and response-snapshot tests, list endpoints, smoke script moved into the repository, plan review |
