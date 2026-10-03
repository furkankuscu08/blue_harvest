# Run: stale approval, 2026-10-03

Recorded. To check it again without an LLM: `python guard/harness.py replay stale_approval guard/runs/2026-10-03-stale-approval`.

## Setup

| | |
|---|---|
| Mutant | `stale_approval`: `decide()` skips the version check when the outcome is `APPROVED`. A reviewer can approve a revision they never saw (I3, I5). |
| Baseline | `229ad61` |
| Withheld from the agent | `test_stale_version_cannot_approve`, `test_stale_version_is_reported_before_invalid_state`; also `guard/`, `docs/plan.md`, `docs/ai-usage.md`, the assignment text, agent instructions and git history |
| Gap | The 38 remaining tests all pass on the mutant. |
| Agent | Claude Code 2.1.288, `claude-sonnet-5-5`, `--restricted --safe-mode`, read-only except `tests/`, no commands. Full command in `run.json`. |
| Agent run | 9 turns, about 20 seconds, USD 0.12, no permission denials, no rule violations |

## Result

| Agent test | Baseline | Mutant | Result | Failure on mutant |
|---|---|---|---|---|
| `test_stale_version_cannot_approve[older]` | passed | failed | caught | `DID NOT RAISE DomainError` |
| `test_stale_version_cannot_approve[newer]` | passed | failed | caught | `DID NOT RAISE DomainError` |
| `test_stale_version_is_reported_before_state_when_approving[APPROVED]` | passed | failed | caught | `INVALID_STATE` instead of `STALE_VERSION` |
| `test_stale_version_is_reported_before_state_when_approving[DECLINED]` | passed | failed | caught | `INVALID_STATE` instead of `STALE_VERSION` |

**Human-confirmed:** each failure comes from the business rule the mutant breaks. Either an approval with the wrong version goes through, or a stale version is reported as `INVALID_STATE`, against the order of checks in `docs/api-contract.md`.

The agent's report (in `transcript.json`) names I3 and I5 and the order of checks. It explains why each existing test misses the change. Its two tests cover the intent of both withheld reference tests.

## Limits

- **The gap was easy to see.** The experiment copy still had stale-version tests for revise and decline, each with an older and a newer version, so the missing approve case stood out. The agent's first test matches the withheld one in name and parameters. It most likely followed that symmetry; it had no access to the withheld test.
- **The prompt gave a hint.** Its example test name, `test_stale_version_cannot_revise`, points at the naming pattern and the topic. Later runs use a neutral example.
- **This is one run of one model on one mutant.** It is evidence for this scenario, not a success rate.
