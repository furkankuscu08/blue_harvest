# Run: idempotent replay, 2026-10-05

Recorded. To check it again without an LLM: `python guard/harness.py replay idempotent_replay guard/runs/2026-10-05-idempotent-replay`.

## Setup

| | |
|---|---|
| Mutant | `idempotent_replay`: the create endpoint no longer returns the stored response for a key it has seen. A create sent again with the same key and fields is answered with `409 REQUEST_ALREADY_EXISTS` (I10). |
| Baseline | `33dd38a` |
| Withheld from the agent | `test_same_key_and_fields_replays_the_original_response`, `test_replay_returns_the_original_response_after_the_request_changed`, `test_whitespace_around_reason_does_not_change_the_payload`, `test_idempotency_key_is_scoped_to_the_caller`; also `guard/`, `scripts/`, `docs/plan.md`, `docs/ai-usage.md`, `docs/demo-script.md`, the assignment text, agent instructions and git history |
| Proof of the mutant | `prove`: 209 tests pass on the baseline; on the mutant exactly the four withheld tests fail. |
| Gap | The 205 remaining tests all pass on the mutant. |
| Agent | Claude Code 2.1.289, `claude-sonnet-5-5`, `--restricted --safe-mode`, read-only except `tests/`, no commands. Full command in `run.json`. |
| Agent run | One run, the first. 11 turns, about 16 seconds, USD 0.11, no permission denials, no rule violations |

The rules for this run were fixed in `docs/plan.md` before it: one mutant, the prompt changed before the run and not after it, a second run only after a tool failure. No second run was needed.

## Result

| Agent test | Baseline | Mutant | Result | Failure on mutant |
|---|---|---|---|---|
| `test_replay_of_a_committed_create_returns_the_stored_original_response` | passed | failed | caught | `assert 409 == 201` |
| `test_replay_is_never_answered_with_request_already_exists_after_the_request_changed` | passed | failed | caught | `assert 409 == 201` |
| `test_replay_changes_no_state` | passed | passed | missed | |

**Two caught, one missed.**

The two caught tests fail on the rule the mutant breaks: a create sent again with the same key and fields must get `201` and the first response, and on the mutant it gets `409`. The second one declines the request first, so on correct code it also pins that the replay returns the stored response and not the current state.

**Human-confirmed:** I read the three tests. The assertions of the two caught tests are about I10: the same key and fields must get `201` and the first response.

The missed test reads the request, sends the create again without looking at the answer, and reads the request again. On the mutant the second create is refused and writes nothing, so the request is unchanged and the test passes. It is a valid test of the other half of I10, "without changing any state", which this mutant does not break. It would catch a replay that creates or changes something.

**The agent's report was wrong about its third test.** It said that each of its three tests would fail once the change is applied. In the same report it had written that the retry "is rejected and writes nothing", which is the reason the third test cannot fail. The agent could not run anything; the harness showed the difference.

## Limits

- **The gap was visible.** Removing the four tests left the section comment "Idempotency: one logical submission is one key and one fixed payload." above a single test for the same key with different fields, and an import of `decide` that nothing used any more. The agent's report says so itself: "an empty Idempotency section where the replay tests would sit". Its second test has the shape of a withheld one, create, decide, create again; the unused import may have pointed there. It had no access to the withheld tests.
- **The diff is blunt.** It deletes one `return`, and the comment above it says what the line was for. A change hidden in a larger pull request would be harder to read.
- **Two of the four withheld tests have no counterpart.** The agent wrote nothing for the trimmed reason or for a key shared by two callers. The prompt allows at most three tests.
- **The harness is not calibrated on API tests.** Its five calibration samples are domain tests for the first mutant. See `guard/README.md`.
- **This is one run of one model on one mutant.** Together with the first run it is evidence for two scenarios, not a success rate.
