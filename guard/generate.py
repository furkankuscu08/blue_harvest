"""Run the invariant guard agent in a prepared workspace and record what it did.

    python guard/generate.py <mutant> <workspace> <run-dir>

Generation needs Claude Code and uses the caller's Claude plan. Verification
does not: `python guard/harness.py replay <mutant> <run-dir>` re-checks the
recorded tests without an LLM.

The agent runs with --restricted and --safe-mode: no tools that run commands
or code, no network tools, no project or user settings, no CLAUDE.md, hooks or
MCP servers, and file tools confined to the workspace. It may read anything in
the workspace and edit only under tests/.
"""

import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from harness import CONFIG, GUARD, agent_changes

MODEL = "claude-sonnet-5-5"
TIMEOUT_SECONDS = 900


def command(prompt: str) -> list[str]:
    return [
        "claude", "-p", prompt,
        "--restricted", "--safe-mode",
        "--tools", "Read,Glob,Grep,Write,Edit",
        "--allowedTools", "Read", "Glob", "Grep", "Edit(tests/**)",
        "--permission-mode", "dontAsk",
        "--model", MODEL,
        "--output-format", "json",
        "--no-session-persistence",
    ]  # fmt: skip


def main() -> int:
    mutant, workspace, run_dir = sys.argv[1], Path(sys.argv[2]).resolve(), Path(sys.argv[3])
    if run_dir.exists():
        print(f"{run_dir} already exists.")
        return 1
    if ".claude" in workspace.parts:
        # --restricted treats files under .claude as tool configuration and denies the
        # agent's writes there, even under tests/. Found in a preflight run.
        print("The workspace must not be inside a .claude directory.")
        return 1
    run_dir.mkdir(parents=True)
    prompt = (GUARD / "prompt.md").read_text()
    shutil.copy(GUARD / "prompt.md", run_dir / "prompt.md")

    version = subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout
    started = datetime.now(UTC)
    finished = subprocess.run(
        command(prompt), cwd=workspace, capture_output=True, text=True, timeout=TIMEOUT_SECONDS
    )
    (run_dir / "transcript.json").write_text(finished.stdout)

    added, violations = agent_changes(mutant, workspace)
    (run_dir / "tests").mkdir()
    for relative in added:
        shutil.copy(workspace / relative, run_dir / "tests" / relative.name)

    shown = command("<contents of prompt.md>")
    record = {
        "mutant": mutant,
        "baseline": CONFIG["baseline"],
        "model": MODEL,
        "claude_code": version.strip(),
        "started_at": started.isoformat(timespec="seconds"),
        "exit_code": finished.returncode,
        "command": " ".join(f'"{part}"' if " " in part else part for part in shown),
        "added_files": [str(p) for p in added],
        "rule_violations": violations,
    }
    (run_dir / "run.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))
    if finished.returncode != 0:
        print(finished.stderr[-2000:])
    return finished.returncode


if __name__ == "__main__":
    sys.exit(main())
