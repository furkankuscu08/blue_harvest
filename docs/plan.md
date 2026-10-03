# Working plan

Frozen on 2026-10-03 after three review rounds. Only the time log is updated from here on. Later changes to decisions are recorded in the ADRs and day 1 documents, not here.

## Stack

| Area | Choice | Why / production note |
|---|---|---|
| Language | Python 3.12 | The language I can defend line by line. Team knows Java/C#; the assignment allows any. |
| API | FastAPI + Pydantic v2 | OpenAPI and Swagger UI for free, which doubles as the "explore" instructions. |
| Persistence | SQLite (file) via SQLAlchemy 2.0 | Zero setup for reviewers. Constraints and transactions are real. Production: Postgres + Alembic, with the concurrency tests re-validated there; not just a connection string change. |
| Running it | `docker compose up` (Dockerfile + single-service compose, volume for the SQLite file) | The one run path shown to reviewers; same result on any machine. |
| Development | `uv venv` + `requirements.txt` / `requirements-dev.txt` | Fast test loop and editor support; also the fallback for running without Docker. Direct dependencies live in `requirements.in`; `uv pip compile` produces the fully pinned `requirements.txt`. |
| Tests | pytest + FastAPI TestClient | Domain tests, API tests against a real SQLite file, concurrency tests. |
| Quality | ruff, GitHub Actions CI (tests via the venv path, plus image build and health check) | Deterministic gates that agents cannot talk their way past; keeps both paths working. |
| UI | One static page (vanilla JS) served by the same app | No frontend build; it uses the same public API. |

SQLite rules: `PRAGMA foreign_keys=ON` and `busy_timeout` on every connection, WAL mode, short write transactions opened with `BEGIN IMMEDIATE`. WAL does not give multiple concurrent writers; that limit is accepted. `BEGIN IMMEDIATE` under SQLAlchemy needs explicit setup, so it is proven on day 2.

## Domain decisions

1. **One exception file per application.** Each mortgage application has at most one pricing exception request, which can have several revisions and several decisions. Enforced by a unique constraint. Changing an approved discount is out of scope (production: a supersede flow).
2. **Revisions.** Revisions are immutable. Revising always creates a new revision and puts the request in `PENDING`.
3. **Transitions.**

   | From | Action | To |
   |---|---|---|
   | (none) | create | `PENDING`, revision 1 |
   | `PENDING` | revise | `PENDING`, new revision |
   | `PENDING` | decline | `DECLINED` |
   | `DECLINED` | revise and resubmit | `PENDING`, new revision |
   | `PENDING` | approve | `APPROVED` (terminal) |

4. **One decision per revision.** A decision can only be made on the latest revision while the request is `PENDING`. A declined revision is never approved later; it must be revised first. Backed by a unique constraint on the decision's revision.
5. **One concurrency token.** The request has a `version` that increases on every revision and every decision. Revise and decide both send the version the user was looking at; a stale version returns `409`. The decision row stores the revision it applied to. The version check and the change happen in the same write transaction. The UI sends the version the user actually saw; it does not re-read just before submitting.
6. **History.** Revisions and decisions are append-only rows written in the same transaction as the status change. No full event sourcing.
7. **Idempotency.** `Idempotency-Key` header is required on create, scoped per caller, stored in the same transaction as the request.
   - Checked before the one-per-application rule, so a retry gets the original response and not a `409`.
   - Same key and same validated fields (not byte-identical JSON): replay the stored first response, even if the request has changed since.
   - Same key and different fields: `422`. `409` is kept for state conflicts (existing request, stale version).
   - Failed calls are not stored; a retry is evaluated again.
   - One logical submission is one key plus one frozen payload; a retry resends exactly that pair.
   - UI: on submit, the key and payload are stored together. If the outcome is unknown (timeout, network error), the form locks and only "Retry" is offered. A definite response (success or validation error) closes the submission; later changes go through the revise flow.
8. **Identity.** Seed users with roles, selected by an `X-User-Id` header. Not real authentication, and documented as such. Authorisation is enforced server-side; the decision maker and timestamp never come from the request body.
9. **Permissions.**

   | Action | Who |
   |---|---|
   | Create | Relationship manager |
   | Revise | Only the manager who created the request |
   | Decide | Reviewer who is not the creator (four-eyes) |
   | View request and history | Any internal user |
   | Read approved discount | Downstream caller |

10. **Validation.** Application must exist; discount is a positive integer of basis points with one documented upper-bound setting (our assumption); reason is non-blank.
11. **Downstream endpoint.** `GET /applications/{id}/approved-discount` returns request id, revision, approved basis points, decided-by and decided-at, read from the approved revision. `404` with distinct error codes for "application not found" and "no approved discount".
12. **Stable error codes.** The HTTP status gives the category; a code in the body names the exact case, and clients branch on the code.

    | Status | Codes |
    |---|---|
    | `403` | `NOT_REQUEST_OWNER`, `FOUR_EYES_VIOLATION` |
    | `404` | `APPLICATION_NOT_FOUND`, `NO_APPROVED_DISCOUNT` |
    | `409` | `REQUEST_ALREADY_EXISTS`, `STALE_VERSION`, `NOT_PENDING` |
    | `422` | `IDEMPOTENCY_KEY_REUSED` |

## Agent bonus

An invariant guard for pull requests. Given a diff, the domain rules above and the existing tests, the agent names the rules at risk, looks for gaps in the tests, and writes the most valuable missing regression tests.

- **Mutants to start with:** stale approval allowed; idempotent replay broken (same key and content does not return the first response; the unique constraint still prevents a second row, so the visible failure is a `409`); authorisation check removed.
- **Each mutant is proven first.** For every mutant we write down the externally observable behaviour it breaks and prove it with a hand-written reference test. A mutant that does not change behaviour is not used.
- **Reference tests are withheld from the agent, not from the project.** The main test suite and CI stay complete and include the reference tests. The agent experiment runs in a separate copy with the relevant reference tests removed, so the agent has a gap to fill; its test is compared with the reference afterwards.
- **What this measures.** It is a controlled experiment on deliberately created test gaps, and is reported as such. The agent sees both the rules and the change that weakens one, so the experiment shows whether it notices the weakening and writes a discriminating test, not whether it discovers unknown defects. Three examples are evidence for three scenarios, not a general success rate.
- **Verification harness (no LLM, free to run):** mutants are `mutants/*.patch` files. A script runs only the agent-written tests on a fixed baseline commit and on each mutant, and prints a table. Failures of existing or reference tests never count as an agent result.
  - `caught`: passes on the baseline, fails on the mutant on the expected business-rule assertion.
  - `missed`: passes on both.
  - `invalid run`: fails on the baseline, or fails on the mutant for another reason (import error, timeout, broken fixture, inspecting source text instead of behaviour).
  - Whether a failure comes from the right assertion is confirmed by a human and marked as such in the report. No general system for interpreting failures.
- **Generation and verification are separate.** Running the harness is not re-running the agent. For generation, the prompt, tool permissions and command are documented.
- **Controls:** agent may only add files under `tests/`, never merges, advisory only. Generated tests run in a container with no secrets, no network and a time limit. CI stays the merge gate.
- **Running it:** generating tests needs an LLM and is optional. The committed tests, prompt, model name and outputs are the recorded evidence, labelled as recorded; anyone can re-run the harness against them without an LLM.
- **Residual risks:** missed rules, false alarms, tests that pass for the wrong reason, prompt injection through diff content.

`docs/ai-usage.md` is written as we go: what the agent produced, what was rejected or corrected, how it was validated.

## Supporting documents

- Three or four ADRs: revision and decision model, idempotency, persistence and concurrency, agent verification.
- One-page traceability table: requirement, behaviour, test.
- Repeatable seed and a documented demo reset command.
- Manual demo script for the UI, actually executed with the result recorded. Automated browser tests are deferred because of their setup and maintenance cost within this budget. Required scenarios:
  - Decline, revise, resubmit, approve.
  - Two open tabs, acting with a stale version (`STALE_VERSION` message).
- Idempotent retry is proven at API level: an automated test and a `curl` step in the demo script that sends the same call twice. A lost response cannot be produced reliably by hand in a browser, so the UI retry path is not manually verified; the README lists this as a known limit.

## Notes to carry into the day 1 documents

- **Retry for revise and decide.** No extra idempotency mechanism; the version check covers it.
  - If the first call committed, a retry with the old version changes nothing and returns a conflict.
  - If it did not commit and the state still allows it, the retry can succeed.
  - A conflict alone does not prove the earlier call succeeded; another user may have changed the request. After a timeout the client reads the current request and its history to find out.
  - The UI never fetches a new version and resends the same action automatically.
- **Data the UI needs.** The API contract defines how the UI finds and selects requests, shows detail and history, and picks a seed user and application. Add only the read endpoints this requires. Leaning towards two small unfiltered, unpaginated lists (users, applications) so seed data has one source of truth; decided when the contract is written.
- **Assumptions are labelled as ours.** One request per application and four-eyes are not stated in the assignment; the README presents them as deliberate assumptions.
- **Stakeholder decision in one sentence.** Before approval a request can be changed through a new revision; every decision is bound to the revision that was reviewed, and after approval the request cannot be changed.
- **README** includes the real total time spent and a short "with more time" section. No extra documents for these.

## Schedule (about 28 hours)

| Day | Hours | Outcome |
|---|---|---|
| 1 | 3 | Assumptions, ADRs, state diagram, API contract, acceptance scenarios, traceability table |
| 2 | 2 | Skeleton, `CLAUDE.md`, prove `BEGIN IMMEDIATE` (priority), minimal Dockerfile + compose and CI |
| 3 | 4 | Domain core, test-first: revisions, transitions, permissions. Then the agent spike with one mutant (stale approval): generation plus LLM-free verification |
| 4 | 3 | API, persistence, seed and reset; first end-to-end flow, then one `docker compose up` check from a clean environment |
| 5 | 3 | Idempotency, concurrency tests, history, downstream endpoint |
| 6 | 3 | UI |
| 7 | 3 | Agent bonus: runnable flow |
| 8 | 3 | Agent bonus: mutant evaluation, recorded evidence, `ai-usage.md` |
| 9 | 2 | README, production gaps, operational notes, demo script |
| 10 | 2 | Fresh-clone rehearsal, buffer |

Concurrency tests use separate connections and a coordinated start, and assert only the durable outcome, never which thread wins or any timing:

- Of two valid decision attempts on the same version, one succeeds and the other gets a conflict.
- Exactly one decision row exists for that revision.
- Request status, version and history agree with each other.

## Standing rules

- Default answer to "should we add it" is no; record it under deliberate scope choices.
- Nothing enters the repository that I cannot explain in the walkthrough.
- Small, meaningful commits.
- If time runs short, cut in this order: UI visuals and presentation detail first, then the number of mutants.
- Never cut: run and test instructions, assumptions, time spent, both bonuses with meaningful verification evidence, isolation of agent-written tests.
- Log time spent per day below.

## Time log

| Date | Hours | What |
|---|---|---|
| 2026-10-02 to 03 | 4 | Planning and three review rounds |
| 2026-10-03 | 4 | Day 1: assumptions and scope, state model, API contract, review rounds |
| 2026-10-03 | 3 | Day 2: process scaffolding, project skeleton, Docker, CI, SQLite concurrency proof |
