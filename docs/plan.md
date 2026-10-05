# Working plan

The current plan, last updated on 2026-10-05 after day 8. Earlier versions are in the git history of this file; the reasons for the larger changes are listed under [Changes and why](#changes-and-why).

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

Days 1 to 8 are done; the API, the UI and the agent experiment are complete and the checklist is closed. Hours for days 9 and 10 are estimates.

| Day | Hours | Outcome | Done when |
|---|---|---|---|
| 1 | 4 | Assumptions and scope, state model, API contract | Done |
| 2 | 3 | Process scaffolding, skeleton, Docker, CI, proof that `BEGIN IMMEDIATE` works | Done |
| 3 | 3 | Domain core, test-first; invariant guard spike with the first recorded run | Done |
| 4 | 3 | Identity, errors, seed and reset, create with idempotency, get, decide, approved discount | Done |
| 5 | 3 | Revise, the full decline-revise-approve story, concurrency test at API level, list endpoints | Done |
| 6 | 5 | UI and a draft of the demo script | Done |
| 7 | 2 | Idempotent replay experiment | Done |
| 8 | 2 | Checklist | Done |
| 9 | 3 | README, contract clean-up, recorded demo | Someone else can follow the story from the README alone |
| 10 | 2 | Fresh-clone rehearsal, walkthrough rehearsal | The buffer is still there |

Spent so far, including 4 hours of planning: 29 hours. Remaining estimate: 5 hours. Projected total: about 34 hours.

### Day 6: UI

How the UI behaves is defined in [ui-design.md](ui-design.md). It is built in two pull requests:

1. Read-only: serving the page, choosing who to act as, the list of requests, the request detail, the applications with the approved discount. I look at it in the browser with the seed data before the second part starts.
2. Actions: create, revise, approve and decline, with the error, stale version and retry behaviour.

Checked by hand, because there are no browser tests: the demo script; switching users quickly and refreshing twice; a stale version keeps the draft and keeps the action closed until a reload; a submission while the connection is down; the main story on a narrow screen and with the keyboard only. The connection check covers the error and the "Retry" in the UI. It does not prove that a create that was stored and whose response was lost is replayed; the API test and the smoke script prove that.

A defect in the code a pull request adds is fixed in that pull request when it breaks the main story. Other findings become issues for day 8.

The demo script for the UI is drafted while the UI is built: create, decline, revise, act with a stale version in a second tab, approve, read the approved discount as the mortgage process. Automated browser tests are out of scope because of their setup and maintenance cost within this budget.

### Day 7: agent experiment

The invariant guard is described in [guard/README.md](../guard/README.md): an agent writes regression tests against a deliberately broken rule (a mutant), and an LLM-free harness checks whether those tests catch it. Both runs are recorded: stale approval, and idempotent replay with two tests that caught the mutant and one that missed it.

- The second experiment is idempotent replay broken: the same key and content does not return the first response. The unique constraint still prevents a second row, so the visible failure is a `409`.
- One mutant, a neutral prompt and at most two generation runs. The result is recorded as it comes out; the prompt is not tuned until it succeeds.
- The harness gets no new features. It changes only for a defect that makes its result unreliable. One exception: each mutant names its own baseline commit, because the first baseline has no API and the first recorded run must stay checkable against the code it was made on.
- The agent's copy also leaves out `scripts/` and `docs/demo-script.md`: the smoke script repeats the withheld check in bash.
- The prompt changes before the run, not after it: the example test name that hinted at the first mutant is gone, and a test may use the public API. A second generation run happens only if the first cannot be used for a reason outside the agent's judgement, such as a tool error or a timeout.
- Controls: the agent may only add files under `tests/`, never merges, and is advisory only. Its tests run in a container with no secrets, no network and a time limit. CI stays the merge gate.
- Residual risks, for the README: missed rules, false alarms, tests that pass for the wrong reason, prompt injection through diff content.
- It is a controlled experiment on deliberately created test gaps and is reported as such: two examples are evidence for two scenarios, not a general success rate.

### Day 8: checklist

Only what is on the list is fixed; new ideas go to the README as next steps. No GitHub issues were written on days 6 and 7, so the list was these five items; what they found is below.

1. `scripts/smoke.sh`, which starts from an empty volume and stops the service at the end.
2. `docker compose up --build -d --wait`, then the written UI script from start to end, including the two-tab stale version.
3. The error paths a user can reach in the UI, and a lost connection, each with a message the user can act on: validation, stale version, wrong role or owner, four-eyes. Errors only an API client can cause are covered by the API tests.
4. A seed reset while the UI is open.
5. Small open items: the ADR reference in `assumptions-and-scope.md`, and a consistency check in the API concurrency test (after the race, the request's status agrees with the decision on its latest revision), confirmed once against a build with broken locking.

All five were run on 2026-10-05; the fixes are in pull request #23.

- The smoke script passed with 23 checks. Its first run was answered by a local server on the same port and tested the wrong service; the script now stops when the port is already answered.
- The UI steps were done by hand in a browser. Step 4 of the demo script now says that an approval needs a comment.
- After a seed reset, a decision on a request that no longer exists shows "No request with this id." and the old screen stays open. Not fixed: the API has no delete, so only a reset causes it. It goes to the README as a next step.
- The consistency check fails on the build with broken locking in the revise-and-approve case: the request is stored `APPROVED` while its latest revision has no decision.

### Day 9: README and documents

- "Try it in five minutes": a few commands and one address.
- Deliberate assumptions, labelled as ours; real time spent; a short "with more time" section; what changes in production, including PostgreSQL.
- One traceability table that starts from the requirements R1 to R6: requirement, behaviour, test or run evidence, with the related invariants in the same row.
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
- If time runs short, cut first: optional extra agent runs, then UI decoration. Labels, keyboard use, a layout that fits a narrow screen, and the retry and stale version behaviour are not cut.
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
- The transaction race experiment stays a one-off, recorded in `ai-usage.md`. A script for it would need maintenance; instead the concurrency test will reject the broken end state directly, and that check runs in CI. It does not replace the comparison of the three transaction setups.
- The UI is treated as a real deliverable, not as the first thing to cut.
- This file was rewritten to show only the current plan. Decisions about behaviour that it used to repeat, some of them outdated, now live only in the documents named at the top.

**After the UI design review (2026-10-04).**

- The UI design moved into its own document, `ui-design.md`, because the UI has no automated tests and needs written rules to be checked against.
- The day 6 estimate rose from 3 to 5 hours and the total from about 33 to about 35: three screens with addresses instead of one, and the rules for late responses and uncertain results.
- Cut from the design to stay small: filters on the list of requests, a separate handling for a lost connection (it shares the stale version path), and a text for every error code (the API's own message is shown).

## Time log

| Date | Hours | What |
|---|---|---|
| 2026-10-02 to 03 | 4 | Planning and three review rounds |
| 2026-10-03 | 4 | Day 1: assumptions and scope, state model, API contract, review rounds |
| 2026-10-03 | 3 | Day 2: process scaffolding, project skeleton, Docker, CI, SQLite concurrency proof |
| 2026-10-03 | 3 | Day 3: domain core (test-first), invariant guard spike with an LLM-free harness and the first recorded run |
| 2026-10-04 | 3 | Day 4: first API slice (identity, errors, seed and reset, create with idempotency, decide, approved discount, first end-to-end test), two test review rounds, AI usage log restructured |
| 2026-10-04 | 3 | Day 5: revise, the full decline-revise-approve story, API concurrency and response-snapshot tests, list endpoints, smoke script moved into the repository, plan review |
| 2026-10-05 | 5 | Day 6: the UI in two pull requests (read-only screens, then create, revise and decide with the stale version and retry rules), UI design document, draft of the demo script, browser checks by a second agent and by hand |
| 2026-10-05 | 2 | Day 7: a baseline per mutant in the guard harness, the idempotent replay mutant, a review before the run, one recorded agent run with its result and limits |
| 2026-10-05 | 2 | Day 8: the checklist (smoke script, the UI script and error paths by hand, a seed reset under an open UI), a consistency check in the concurrency test, a port check in the smoke script |
