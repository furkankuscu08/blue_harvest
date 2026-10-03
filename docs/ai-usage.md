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
- **Deterministic gates.** Tests, lint and dependency audit run in CI. An agent cannot argue its way past them.
- **Pull requests** say what the AI did and how I verified it. The verification part lists only what I actually did; the agent drafts it from my actions and I confirm it before merging.

## Examples

| What happened | What it shows |
|---|---|
| A reviewer proposed PostgreSQL in Docker to show realistic concurrency. Rejected: SQLite needs no setup and its constraints and transactions are real. PostgreSQL is listed as a production change instead. | Agent suggestions are weighed against the assignment, not followed by default. |
| One of the planned mutants for the agent demo, "duplicate create on retry", could never create a duplicate because the unique constraint already answers with `409`. A reviewer caught it. | A second model finds flaws the first one misses. |
| The builder silently widened the approved-discount endpoint from the mortgage process to every user. A reviewer noticed that it contradicted the agreed plan. Reverted. | Agents drift from earlier decisions; review catches it. |
| The builder noticed its own design flaw: with one role per user, the four-eyes rule could never fire and could not be tested. Users can now hold several roles. | An agent can catch its own errors when asked to check rules against data. |
| The builder proposed generating the UI's idempotency key when the form opens. A reviewer showed why that is wrong: one submission is one key plus one fixed payload. Changed. | Reviewers correct the builder on subtle correctness points. |
| After several review rounds the documents kept growing; no round removed anything. When I asked whether the plan was overengineered, we cut three planned documents. | Scope control stays a human decision. |

## Observation

Review rounds found real defects early on, then mostly added detail that would be settled while writing code. Since day 1, reviews are done on working code instead of document text.
