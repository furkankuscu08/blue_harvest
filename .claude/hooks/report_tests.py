"""Stop hook: run the tests and show the result to the human.

It never blocks the agent from stopping. While writing tests first, failing
tests are expected, and the agent must be able to stop and show them.
"""

import json
import subprocess
import sys
from pathlib import Path

PYTEST = Path(".venv/bin/pytest")


def main() -> int:
    if not PYTEST.exists():
        return 0
    result = subprocess.run(
        [PYTEST, "-q", "--no-header", "-p", "no:cacheprovider", "--color=no"],
        capture_output=True,
        text=True,
        check=False,
    )
    lines = result.stdout.strip().splitlines()
    summary = lines[-1] if lines else "no output"
    print(json.dumps({"systemMessage": f"pytest: {summary}"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
