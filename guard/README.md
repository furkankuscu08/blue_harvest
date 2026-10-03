# Invariant guard

An agent reviews a pull request against the domain rules and writes the regression tests that are missing. To check whether it works, we break one rule on purpose (a mutant), hide the tests that would catch it, and measure whether the agent's tests catch it. Writing the tests needs an LLM. Checking them does not.

Requires Docker. Run from the repository root.

```bash
python guard/harness.py prove stale_approval            # the mutant breaks exactly its reference tests
python guard/harness.py calibrate stale_approval        # the harness classifies known tests correctly
python guard/harness.py prepare stale_approval /tmp/ws  # the agent's copy, with the gap checked
python guard/generate.py stale_approval /tmp/ws guard/runs/<date>-stale_approval   # needs Claude Code
python guard/harness.py verify stale_approval /tmp/ws   # classify the agent's tests
python guard/harness.py replay stale_approval guard/runs/2026-10-03-stale-approval  # re-check a recorded run
```

| File | What it is |
|---|---|
| `mutants.toml`, `mutants/` | Each mutant, the rule it breaks and its reference tests |
| `prompt.md` | The agent's instructions |
| `harness.py` | LLM-free: prove, prepare, verify, calibrate, replay |
| `generate.py` | Runs the agent with restricted permissions and records the run |
| `calibration/` | Five tests with known results: caught, missed, and three kinds of invalid run |
| `runs/` | Recorded runs: prompt, command, transcript, the agent's tests, result |

The workspace must be outside any `.claude` directory: the agent is not allowed to write there.

What `caught` means: the agent's test passes on the baseline and fails on the mutant with an assertion. The harness checks only that it is an assertion. Whether the assertion is about the rule the mutant breaks is confirmed by a person and recorded in the run's `result.md`.

A run is an `invalid run` when the agent changed any existing file, when its file runs tests defined elsewhere (for example by importing them), when pytest does not end normally, or when it times out. `calibration/` covers the import, interrupted-run and collection-error cases; run `calibrate` after changing the harness.
