"""Stop hook: run the tests and show the result to the human.

It never blocks the agent from stopping. While writing tests first, failing
tests are expected, and the agent must be able to stop and show them.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

PYTEST = Path(".venv/bin/pytest")


def main() -> int:
    if not PYTEST.exists():
        return 0
    # FORCE_COLOR would put colour codes into the message.
    env = {k: v for k, v in os.environ.items() if k != "FORCE_COLOR"} | {"NO_COLOR": "1"}
    result = subprocess.run(
        [PYTEST, "-q", "--no-header", "-p", "no:cacheprovider", "--color=no"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    print(json.dumps({"systemMessage": f"pytest (exit {result.returncode}): {summary(result)}"}))
    return 0


def summary(result: subprocess.CompletedProcess) -> str:
    """The result line, or the error if pytest could not start."""
    stdout = result.stdout.strip().splitlines()
    if stdout:
        return stdout[-1]
    stderr = [line.strip() for line in result.stderr.splitlines() if line.strip()]
    # The last error line usually names the cause.
    errors = [line for line in stderr if "error" in line.lower()]
    return (errors or stderr or ["no output"])[-1]


if __name__ == "__main__":
    sys.exit(main())
