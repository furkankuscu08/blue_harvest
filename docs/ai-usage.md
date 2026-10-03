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
- **Deterministic gates.** Tests, lint and a dependency audit will run in CI once the project skeleton exists. An agent cannot argue its way past them.
- **Pull requests** say what the AI did and how I verified it. The verification part lists only what I actually did; the agent drafts it from my actions and I confirm it before merging.

## Examples

| What happened | What it shows |
|---|---|
| A reviewer proposed PostgreSQL in Docker to show realistic concurrency. Rejected: SQLite needs no setup and its constraints and transactions are real. PostgreSQL is listed as a production change instead. | Agent suggestions are weighed against the assignment, not followed by default. |
| One of the planned mutants for the agent demo was "duplicate create on retry". A reviewer noted that the planned unique constraint would still prevent duplicate rows. The mutant was reframed to test broken idempotent replay rather than duplicate creation. | A second model finds flaws the first one misses. |
| The builder silently widened the approved-discount endpoint from the mortgage process to every user. A reviewer noticed that it contradicted the agreed plan. Reverted. | Agents drift from earlier decisions; review catches it. |
| The builder noticed its own design flaw: with one role per user, the four-eyes rule could never fire and could not be tested. Users can now hold several roles. | An agent can catch its own errors when asked to check rules against data. |
| The builder proposed generating the UI's idempotency key when the form opens. A reviewer clarified that this is not enough: retries must preserve both the key and the original payload. The submission lifecycle was clarified. | Reviewers sharpen the builder on subtle correctness points. |
| After several review rounds the documents kept growing; no round removed anything. When I asked whether the plan was overengineered, we cut three planned documents. | Scope control stays a human decision. |

## Observation

Review rounds found real defects early on, then mostly added detail that would be settled while writing code. From day 2 on, reviews will look at working code instead of document text.

Even this log needed review: a reviewer found three overstated claims in its first version (work described as done before it existed, a reviewer's finding made stronger than it was, and a database constraint credited with an HTTP response). They were corrected.
