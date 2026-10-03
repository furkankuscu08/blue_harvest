"""PostToolUse hook: format and lint a Python file right after the agent edits it.

Problems ruff cannot fix are sent back to the agent (exit code 2).

Unused imports are reported, not removed: an agent often adds an import in one
edit and the code that uses it in the next.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

RUFF = Path(".venv/bin/ruff")


def main() -> int:
    event = json.load(sys.stdin)
    file_path = event.get("tool_input", {}).get("file_path", "")
    if not file_path.endswith(".py") or not RUFF.exists():
        return 0

    # Plain text for the agent; FORCE_COLOR would override NO_COLOR.
    env = {k: v for k, v in os.environ.items() if k != "FORCE_COLOR"} | {"NO_COLOR": "1"}
    result = subprocess.run(
        [RUFF, "check", "--fix", "--unfixable", "F401", "--quiet", file_path],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    subprocess.run([RUFF, "format", "--quiet", file_path], check=False, env=env)
    if result.returncode != 0:
        print(result.stdout + result.stderr, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
