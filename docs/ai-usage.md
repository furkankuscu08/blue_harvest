# AI usage

How AI agents contributed to this work, and how their output was checked. Updated as the work happens.

## Roles

| Role | Tool and model | Used for |
|---|---|---|
| Builder | Claude Code, Claude Opus 5.5 | Drafting plans and documents, writing code and tests. |
| Reviewer | opencode, GPT 6 Astra | Independent review of plans and documents. |
| Reviewer | opencode, Qwen 3.8 Max | Independent review of plans and documents. |
| Decision maker | Me | Every decision. Nothing is merged without my review. |

## How output is checked

- **Cross-model review.** What the builder writes is reviewed by agents on different models. I pass feedback between them and decide.
- **Deterministic gates.** CI runs tests, lint and a dependency audit, and checks that the Docker image starts and is healthy. An agent cannot argue its way past them.
- **Guardrails for the builder.** `.claude/settings.json` limits what the agent may run without asking, and hooks run ruff after each edit and show the test result when it stops. These reduce accidents; they are not a security boundary.
- **This log** records how AI output was checked. Pull requests describe the change only; the examples below say what the agents did, what I checked and what was rejected.

## Examples

| What happened | What it shows |
|---|---|
| A reviewer proposed PostgreSQL in Docker to show realistic concurrency. Rejected: SQLite needs no setup and its constraints and transactions are real. PostgreSQL is listed as a production change instead. | Agent suggestions are weighed against the assignment, not followed by default. |
| One of the planned mutants for the agent demo was "duplicate create on retry". A reviewer noted that the planned unique constraint would still prevent duplicate rows. The mutant was reframed to test broken idempotent replay rather than duplicate creation. | A second model finds flaws the first one misses. |
| The builder silently widened the approved-discount endpoint from the mortgage process to every user. A reviewer noticed that it contradicted the agreed plan. Reverted. | Agents drift from earlier decisions; review catches it. |
| The builder noticed its own design flaw: with one role per user, the four-eyes rule could never fire and could not be tested. Users can now hold several roles. | An agent can catch its own errors when asked to check rules against data. |
| The builder proposed generating the UI's idempotency key when the form opens. A reviewer clarified that this is not enough: retries must preserve both the key and the original payload. The submission lifecycle was clarified. | Reviewers sharpen the builder on subtle correctness points. |
| The plan said a Stop hook would run the tests. While planning the skeleton, the builder noticed that a blocking hook would conflict with writing tests first: red tests are expected then, and the agent could not stop to show them. The hook only reports the result to me. | Guardrails have to fit the workflow; a strict one can work against the process it supports. |
| The plan said that `BEGIN IMMEDIATE` needs explicit setup under SQLAlchemy and must be proven. The builder wrote the tests first and ran them on the driver defaults. Two concurrent read-modify-write increments ended at 1 instead of 2, with no error, in 10 of 10 runs. After the change the test passed 50 of 50 runs. | A concurrency claim is accepted only with a test that fails without the fix. |
| The domain tests were reviewed before any implementation existed. A reviewer found four places where a wrong implementation would still pass, for example a decline attached to the first revision instead of the latest. The tests were restructured. After implementing, the builder applied those wrong implementations by hand and the tests caught each one. The restructure itself had lost two cases, a version newer than the current one; the builder's own mutants missed it, and the PR review caught it. | Reviewing tests against "which wrong code would pass?" finds gaps that reading them does not. |
| During that check two different mutants failed exactly the same tests. The builder distrusted the match and found that Python had reused the previous mutant's cached bytecode: same file size, written within the same second. Each run now gets its own bytecode cache. | A check that passes can still be wrong; the agent harness needs the same guard. |
| Invariant guard, first run. The stale-approval mutant was proven, its reference tests were withheld, and Claude Sonnet 5.5 ran with restricted permissions on the PR diff. Its tests caught the mutant in 4 of 4 cases, checked by the LLM-free harness and confirmed by me. The gap was easy to spot by symmetry, and the prompt's example test name hinted at the topic; both limits are recorded with the run. A preflight run had shown that the agent cannot write inside a `.claude` directory. In review, a second agent showed that the harness itself could report false catches: a test file that only imported the existing tests brought back the withheld reference tests, and an interrupted run still counted. Both cases, and a hard time limit, are now part of the harness and its calibration; the recorded result still holds. | An agent's output is accepted only after a deterministic check, and its limits are reported along with the result. |
| After several review rounds the documents kept growing; no round removed anything. When I asked whether the plan was overengineered, we cut three planned documents. | Scope control stays a human decision. |

## Observation

Review rounds found real defects early on, then mostly added detail that would be settled while writing code. From day 2 on, reviews will look at working code instead of document text.

Even this log needed review: a reviewer found three overstated claims in its first version (work described as done before it existed, a reviewer's finding made stronger than it was, and a database constraint credited with an HTTP response). They were corrected.
