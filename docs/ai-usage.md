# AI usage

How AI agents contributed to this work, and how their output was checked. Updated as the work happens. Every example links to the pull request or file where it can be checked. For the planning phase the link shows the outcome; the discussion itself happened in agent conversations. Checks run in one-off scripts outside the repository say so; their outcome is recorded here, not in the linked PR.

## Roles

| Role | Tool and model | Used for |
|---|---|---|
| Builder | Claude Code, Claude Opus 5.5 | Plans, documents, tests and code. |
| Reviewer | opencode, GPT 6 Astra | Independent review of plans, tests and code. |
| Reviewer | opencode, Qwen 3.8 Max | Independent review of plans, tests and code. |
| Guard agent | Claude Code, Claude Sonnet 5.5, restricted permissions | Writes tests against a planted defect in the [invariant guard](../guard/README.md) experiment. |
| Decision maker | Me | Every decision. Nothing is merged without my review. |

## How output is checked

In the order of the workflow:

1. **Plan first.** The builder proposes, reviewers on other models critique, and I decide. Scope is cut when it grows.
2. **Tests before code.** Tests are reviewed before anything is implemented, with one question: which wrong implementation would still pass?
3. **Hand mutants.** After implementing, the builder breaks the code on purpose. Each break must make a test fail.
4. **Deterministic gates.** CI runs tests, lint and a dependency audit, and checks that the Docker image starts and is healthy. An agent cannot argue its way past them.
5. **Guardrails for the builder.** `.claude/settings.json` limits what the agent may run without asking; hooks run ruff after each edit and report the test result when it stops. They reduce accidents; they are not a security boundary.
6. **Cross-model review of every pull request.** I pass the findings to the builder, read its evaluation of each, and decide.
7. **My own checks.** Before merging an API change I run the main story against the service myself, first done for [#13].

Pull requests describe the change only. This log records what the agents did, what was checked and what was rejected.

## Examples

### Reviewers find what the builder misses

- The builder silently widened the approved-discount endpoint from the mortgage process to every user. A reviewer saw that it contradicted the plan. Reverted. [#3]
- A planned mutant, "duplicate create on retry", could not work: the unique constraint already prevents a second row. It became "idempotent replay broken". [plan](plan.md)
- For the UI's idempotency key, a reviewer pointed out that a retry must keep the original payload as well as the key. [plan](plan.md)
- The API tests went through two review rounds before any code existed: 14 findings, then 6. One added a test that makes the idempotency record fail to store. After implementing, it was the only test that caught a hand mutant that commits the request before its record. [#13]
- A test restructure lost two cases, a version newer than the current one. The builder's own mutants missed it; the PR review caught it. [#9]
- Seeding checked only the users table, so a database with other rows was seeded again. Fixed with a regression test. [#12]
- A body that is not valid UTF-8 got the framework's plain 400 instead of the contract's error body. Fixed with a test. [#13]
- Two gaps had been open since [#13]: no test checked that a write endpoint builds its response before the commit, or that it validates the body before looking up the request. The test review for revise found both; the new tests cover revise and decide. [#16]
- The UI design went through two review rounds before any code. A reviewer moved the current discount and reason above the history, so that a reviewer decides with the reason in view, and replaced "show every action, disabled" with "hide what is not your role, explain what is not possible now". It also showed that the builder's rule for late responses, "same user and same screen", let through an earlier refresh and a switch from one user to another and back. One counter for all reads replaced it. [design](ui-design.md), [#19]
- The builder wrote a discount as `25 bps (0.25%)`. A reviewer pointed out that a percentage of a rate and percentage points are different things. The UI shows basis points. [#19]

### Suggestions are weighed, not followed

- PostgreSQL in Docker, to show realistic concurrency: rejected. SQLite needs no setup and its constraints and transactions are real. PostgreSQL is listed as a production change. [scope](assumptions-and-scope.md)
- Trimming whitespace from `outcome`: rejected, because it is a code, not text. The contract now names the trimmed fields, and a test pins the rule. [#13]
- A test that replays after an app restart: rejected. Idempotency records live in a table, so an in-memory cache is not a plausible wrong implementation. [#13]
- A test for a configurable discount limit: the setting was removed instead, because nobody needs it. The limit is now a constant (A5). [#13]
- A controllable clock, so that a story test would not rely on two decisions getting different timestamps: rejected as too much for one assertion. The assertion was dropped; who decided already tells the two decisions apart. [#16]
- A reviewer's screen sketch used the company's name as the product name in the top bar: rejected. The page is called "Pricing exceptions". [#19]

### The builder is wrong too

- With one role per user, the four-eyes rule could never fire. The builder caught this itself when asked to check the rules against the seed data. Users can now hold several roles. [#3]
- A planned Stop hook that blocks on failing tests would have fought test-first, where red tests are expected. The hook only reports. [#6]
- The edit hook removed imports added one edit before the code that used them. Unused imports are now reported, not removed. [#12]
- The builder said a wrongly sorted import "would fix itself". It did not, and the local ruff cache hid it. CI caught it. [#12]
- This log needed review too: its first version had three overstated claims. [#5]
- The check that two requests in the concurrency test really overlap went wrong twice. The first version failed on correct code: SQLAlchemy ignored `insert=True` for that event, so the check ran after the lock wait. A trace showed it. The second version could still fail when one request started late; a reviewer showed it with a 600 ms delay. Both write transactions now wait for each other just before `BEGIN`. [#16]
- The builder's mutant script restored files with `git checkout`, which also erased the uncommitted implementation, so nine of ten mutants ran against the old code. Their output made no sense, which exposed it. They were rerun from a backup. After the rerun, nine of ten mutants failed a test. The tenth loads the caller in a separate read session: it breaks the `AGENTS.md` rule but has no observable effect, because no endpoint changes users. The mutant runs were one-off scripts outside the repository. [#16]
- The builder gave "it would change the answer for unknown routes" as the reason for not mounting the UI's files at the root, and wrote a test for it. Its own hand mutant, a mount at the root, passed that test: a `GET` still got the framework's 404, and only other methods changed, to a 405. The test now covers `POST` as well and fails for the mutant. [#19]

### A claim counts only with a check that fails without it

- `BEGIN IMMEDIATE`: on the driver defaults, two concurrent read-modify-write increments ended at 1 instead of 2 in 10 of 10 runs. After the change: 2, in 50 of 50 runs. [#7]
- Two different mutants failed exactly the same tests. The builder distrusted the match: Python had reused cached bytecode from the previous mutant. Each run now gets its own cache. [#9]
- In a one-off script outside the repository, the same race between a revision and an approval under three transaction setups. With the driver's defaults both succeeded: the request was stored as `APPROVED` while its latest revision, at 35 bps, had no decision, and the approval sat on the earlier revision. The downstream read then failed with a 500. The builder first claimed the mortgage process would read the unapproved discount; a reviewer checked the code path and corrected it. With `BEGIN DEFERRED` the data stayed correct but the losing caller got a 500. With `BEGIN IMMEDIATE` it gets `409 STALE_VERSION`. The API concurrency test fails under the first two. [#16]
- Invariant guard, first run: Claude Sonnet 5.5 wrote tests that caught the stale-approval mutant in 4 of 4 cases, checked by an LLM-free harness and confirmed by me. In review, a second agent showed that the harness itself could report false catches; those cases are now part of its calibration. Limits are recorded with the [run](../guard/runs/2026-10-03-stale-approval/result.md). [#10]
- Hand mutants for the two list endpoints, in a one-off script outside the repository: eight of nine failed a test (no ordering, oldest first, no tie-break on `id`, tie-break reversed, discount of the first revision, list of requests without a caller, list of users needing a caller, users in another order). The ninth, roles left unsorted, cannot be observed: the primary key already returns a user's roles in alphabetical order. The tie-break test uses random ids, so its mutant can pass by chance in 1 of 24 runs; correct code never fails it. [#17]

### I decide rules and scope

- When documents kept growing over review rounds, I asked whether the plan was overengineered. Three planned documents were cut on day 1. After day 3, the ADRs, a guard subagent and the authorisation mutant were dropped. [#11]
- I made a comment mandatory for approvals as well as declines, and proposed a minimum of 20 characters. The builder argued against the minimum: it does not ensure quality, and 20 is arbitrary. I dropped it. [#13]
- Before merging the first API slice I ran a smoke script against the service in Docker: create, replay, stale retry, the downstream read and four-eyes. 10 of 10 checks passed. [#13]
- Before merging revise I ran the extended smoke script: a reset inside Docker, then 35 bps declined, revised to 20, a stale retry, a revise by another manager, the approval, and the downstream read of revision 2 at 20 bps. 20 of 20 checks passed. [#16]
- Before merging the list endpoints I ran the smoke script again, extended with the list of requests after the full story, the same list without a caller, and the list of users without a caller. 23 of 23 checks passed. [#17]
- The builder called the UI the largest scope risk and proposed to keep it deliberately minimal. I disagreed: the UI is a deliverable, and it should be simple but pleasant to use. After the design grew over two review rounds, I asked again where it was overengineered; the builder cut three things, listed in the [plan](plan.md). [#19]
- The builder cannot open a browser, so it could not see the page it wrote. Before merging the read-only UI I looked at every screen with the seed data, as five users and in a narrow window. A screenshot showed that opening a request scrolled the top bar out of view, and that the decision on an approved or declined request was only at the bottom of the page. Both were fixed and I looked again. Switching users quickly, pressing "Refresh" several times in a row and moving through the page with the Tab key showed no problem. [#19]

## What I learned so far

- Reviewing tests before the code exists found the most real defects. Reviewing documents found real flaws at first, then mostly added detail.
- A passing check can still be wrong: a cached result, a reused bytecode file, an assertion that accepts any error. Agents need the same distrust as humans.
- An agent's "this passes" or "this will fix itself" is a claim, not evidence. It counts after a test, CI or a run I watched.

[#3]: https://github.com/furkankuscu08/blue_harvest/pull/3
[#5]: https://github.com/furkankuscu08/blue_harvest/pull/5
[#6]: https://github.com/furkankuscu08/blue_harvest/pull/6
[#7]: https://github.com/furkankuscu08/blue_harvest/pull/7
[#9]: https://github.com/furkankuscu08/blue_harvest/pull/9
[#10]: https://github.com/furkankuscu08/blue_harvest/pull/10
[#11]: https://github.com/furkankuscu08/blue_harvest/pull/11
[#12]: https://github.com/furkankuscu08/blue_harvest/pull/12
[#13]: https://github.com/furkankuscu08/blue_harvest/pull/13
[#16]: https://github.com/furkankuscu08/blue_harvest/pull/16
[#17]: https://github.com/furkankuscu08/blue_harvest/pull/17
[#19]: https://github.com/furkankuscu08/blue_harvest/pull/19
