"""LLM-free verification for the invariant guard experiment.

    python guard/harness.py prove <mutant>
        Run the full suite on the baseline and on the mutant. The tests that fail
        on the mutant must be exactly its reference tests.

    python guard/harness.py prepare <mutant> <workspace>
        Build the agent's experiment copy: baseline code without the reference
        tests and without files that name the mutants, plus pr.diff. Checks that
        the remaining tests miss the mutant, so the gap is real.

    python guard/harness.py verify <mutant> <workspace>
        Run only the test files the agent added, on the baseline and on the mutant,
        and classify each test as caught, missed or invalid run.

    python guard/harness.py calibrate <mutant>
        Run verify on three hand-written tests whose result is known.

Every run uses a fresh export of the baseline commit, so no stale file or
bytecode from an earlier run can leak in. Tests run in a container with no
network, a read-only file system, limited resources and a time limit.
"""

import argparse
import ast
import filecmp
import shutil
import subprocess
import sys
import tempfile
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "guard"
CONFIG = tomllib.loads((GUARD / "mutants.toml").read_text())
IMAGE = "blue-harvest-guard"
TEST_TIMEOUT_SECONDS = 120

# Not shown to the agent: they name the mutants, hold the withheld tests or
# carry instructions meant for the builder.
HIDDEN_FROM_AGENT = [
    "guard",
    ".claude",
    ".github",
    "CLAUDE.md",
    "AGENTS.md",
    "docs/plan.md",
    "docs/ai-usage.md",
    # The assignment text: its bonus section describes this experiment, and the rules
    # the agent needs are already in docs/state-model.md and docs/api-contract.md.
    "docs/Blue Harvest Agentic SDLC Engineering Assignment.md",
]

# A failure on the mutant counts as caught only if it comes from an assertion.
ASSERTION_PREFIXES = ("AssertionError", "assert ", "Failed: DID NOT RAISE")


# Trees


def export_baseline(dest: Path) -> Path:
    dest.mkdir(parents=True)
    archive = subprocess.run(
        ["git", "-C", str(ROOT), "archive", CONFIG["baseline"]], capture_output=True, check=True
    )
    subprocess.run(["tar", "-x", "-C", str(dest)], input=archive.stdout, check=True)
    return dest


def apply_mutant(tree: Path, mutant: str) -> None:
    patch = GUARD / mutant_config(mutant)["patch"]
    subprocess.run(["git", "apply", str(patch)], cwd=tree, check=True)


def build_workspace(mutant: str, dest: Path) -> Path:
    """The experiment copy the agent works in."""
    export_baseline(dest)
    for name in HIDDEN_FROM_AGENT:
        path = dest / name
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
    for test_file in (dest / "tests").glob("test_*.py"):
        remove_functions(test_file, set(mutant_config(mutant)["reference_tests"]))
    shutil.copy(GUARD / mutant_config(mutant)["patch"], dest / "pr.diff")
    return dest


def remove_functions(path: Path, names: set[str]) -> None:
    source = path.read_text()
    lines = source.splitlines(keepends=True)
    spans = [
        (min([node.lineno] + [d.lineno for d in node.decorator_list]), node.end_lineno)
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    for start, end in sorted(spans, reverse=True):
        del lines[start - 1 : end]
    path.write_text("".join(lines))


# Running tests


def ensure_image() -> None:
    subprocess.run(
        ["docker", "build", "-q", "-f", str(GUARD / "Dockerfile"), "-t", IMAGE, str(ROOT)],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def run_tests(tree: Path, paths: list[str]) -> dict[str, tuple[str, str]]:
    """Run pytest in an isolated container. Returns {test id: (outcome, message)}."""
    out = Path(tempfile.mkdtemp(prefix="guard-out-"))
    out.chmod(0o777)
    command = [
        "docker", "run", "--rm",
        "--network", "none",
        "--read-only", "--tmpfs", "/tmp",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--memory", "512m", "--pids-limit", "256",
        "-v", f"{tree}:/work:ro",
        "-v", f"{out}:/out",
        IMAGE,
        "timeout", str(TEST_TIMEOUT_SECONDS),
        "python", "-m", "pytest", "-q", "-p", "no:cacheprovider",
        "--junitxml=/out/report.xml", *paths,
    ]  # fmt: skip
    finished = subprocess.run(command, capture_output=True, text=True)
    report = out / "report.xml"
    if finished.returncode == 124 or not report.exists():
        reason = "timeout" if finished.returncode == 124 else finished.stdout[-500:]
        return {"<run>": ("error", reason)}
    return parse_junit(report)


def parse_junit(report: Path) -> dict[str, tuple[str, str]]:
    results = {}
    for case in ET.parse(report).iter("testcase"):
        module = case.get("classname", "").replace(".", "/")
        test_id = f"{module}.py::{case.get('name')}" if module else case.get("name")
        failure, error = case.find("failure"), case.find("error")
        if failure is not None:
            results[test_id] = ("failed", failure.get("message", ""))
        elif error is not None:
            results[test_id] = ("error", error.get("message", ""))
        elif case.find("skipped") is not None:
            results[test_id] = ("skipped", "")
        else:
            results[test_id] = ("passed", "")
    return results


def classify(baseline: tuple[str, str], mutant: tuple[str, str]) -> str:
    if baseline[0] != "passed":
        return "invalid run"
    if mutant[0] == "passed":
        return "missed"
    if mutant[0] == "failed" and mutant[1].startswith(ASSERTION_PREFIXES):
        return "caught"
    return "invalid run"


# Commands


def prove(mutant: str) -> int:
    with tempfile.TemporaryDirectory(prefix="guard-") as tmp:
        baseline = run_tests(export_baseline(Path(tmp) / "baseline"), ["tests"])
        mutated = export_baseline(Path(tmp) / "mutant")
        apply_mutant(mutated, mutant)
        on_mutant = run_tests(mutated, ["tests"])

    not_passing = [t for t, (outcome, _) in baseline.items() if outcome != "passed"]
    if not_passing:
        print(f"Baseline is not green: {not_passing}")
        return 1
    broken = sorted(t for t, (outcome, _) in on_mutant.items() if outcome != "passed")
    print(f"{len(baseline)} tests pass on the baseline. Failing on {mutant}:")
    for test_id in broken:
        print(f"  {test_id}")

    expected = set(mutant_config(mutant)["reference_tests"])
    found = {t.split("::")[1].split("[")[0] for t in broken}
    if found != expected:
        print(f"Reference tests in mutants.toml {sorted(expected)} do not match {sorted(found)}.")
        return 1
    print("The failing tests are exactly the reference tests.")
    return 0


def prepare(mutant: str, workspace: Path) -> int:
    if workspace.exists():
        print(f"{workspace} already exists.")
        return 1
    build_workspace(mutant, workspace)

    with tempfile.TemporaryDirectory(prefix="guard-") as tmp:
        mutated = Path(tmp) / "mutant"
        shutil.copytree(workspace, mutated)
        apply_mutant(mutated, mutant)
        on_baseline = run_tests(workspace, ["tests"])
        on_mutant = run_tests(mutated, ["tests"])

    for name, results in (("baseline", on_baseline), ("mutant", on_mutant)):
        not_passing = [t for t, (outcome, _) in results.items() if outcome != "passed"]
        if not_passing:
            print(f"The remaining tests do not all pass on the {name}: {not_passing}")
            return 1
    print(f"Workspace ready: {workspace}")
    print(f"{len(on_mutant)} remaining tests all pass on the mutant too, so the gap is real.")
    return 0


def agent_changes(mutant: str, workspace: Path) -> tuple[list[Path], list[str]]:
    """Test files the agent added, and any other change, which breaks the rules."""
    with tempfile.TemporaryDirectory(prefix="guard-") as tmp:
        pristine = build_workspace(mutant, Path(tmp) / "pristine")
        added, violations = [], []
        for path in sorted(p for p in workspace.rglob("*") if p.is_file()):
            relative = path.relative_to(workspace)
            if "__pycache__" in relative.parts or relative.parts[0] == ".pytest_cache":
                continue
            original = pristine / relative
            if not original.exists():
                is_test = relative.parts[0] == "tests" and relative.name.startswith("test_")
                (added if is_test else violations).append(relative)
            elif not filecmp.cmp(path, original, shallow=False):
                violations.append(f"changed {relative}")
        for path in pristine.rglob("*"):
            if path.is_file() and not (workspace / path.relative_to(pristine)).exists():
                violations.append(f"deleted {path.relative_to(pristine)}")
    return added, [str(v) for v in violations]


def verify(mutant: str, workspace: Path) -> list[tuple[str, str, str]]:
    added, violations = agent_changes(mutant, workspace)
    print(f"Agent added: {[str(p) for p in added] or 'nothing'}")
    if violations:
        print(f"Rule violations, so every result is an invalid run: {violations}")
    if not added:
        return []

    with tempfile.TemporaryDirectory(prefix="guard-") as tmp:
        trees = {}
        for name in ("baseline", "mutant"):
            tree = export_baseline(Path(tmp) / name)
            if name == "mutant":
                apply_mutant(tree, mutant)
            for relative in added:
                shutil.copy(workspace / relative, tree / relative)
            trees[name] = tree
        paths = [str(p) for p in added]
        on_baseline = run_tests(trees["baseline"], paths)
        on_mutant = run_tests(trees["mutant"], paths)

    rows = []
    for test_id in sorted(set(on_baseline) | set(on_mutant)):
        before = on_baseline.get(test_id, ("missing", ""))
        after = on_mutant.get(test_id, ("missing", ""))
        result = "invalid run" if violations else classify(before, after)
        rows.append((test_id, result, after[1].splitlines()[0][:120] if after[1] else ""))

    print("\n| Test | Baseline | Mutant | Result | Failure on mutant |")
    print("|---|---|---|---|---|")
    for test_id, result, message in rows:
        before = on_baseline.get(test_id, ("missing", ""))[0]
        after = on_mutant.get(test_id, ("missing", ""))[0]
        print(f"| `{test_id}` | {before} | {after} | **{result}** | {message} |")
    return rows


def calibrate(mutant: str) -> int:
    """Each file in guard/calibration/ is named after the result it must get."""
    ok = True
    for sample in sorted((GUARD / "calibration").glob("*.py")):
        expected = sample.stem.replace("_", " ")
        with tempfile.TemporaryDirectory(prefix="guard-") as tmp:
            workspace = build_workspace(mutant, Path(tmp) / "workspace")
            shutil.copy(sample, workspace / "tests" / f"test_calibration_{sample.stem}.py")
            print(f"\n## {sample.name}: expected {expected}")
            rows = verify(mutant, workspace)
        results = {result for _, result, _ in rows}
        if results != {expected}:
            print(f"CALIBRATION FAILED: got {results or 'no tests'}")
            ok = False
    print("\nCalibration passed." if ok else "\nCalibration failed.")
    return 0 if ok else 1


def mutant_config(mutant: str) -> dict:
    return CONFIG["mutants"][mutant]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("command", choices=["prove", "prepare", "verify", "calibrate"])
    parser.add_argument("mutant", choices=sorted(CONFIG["mutants"]))
    parser.add_argument("workspace", nargs="?", type=Path)
    args = parser.parse_args()

    ensure_image()
    if args.command == "prove":
        return prove(args.mutant)
    if args.command == "calibrate":
        return calibrate(args.mutant)
    if args.workspace is None:
        parser.error(f"{args.command} needs a workspace directory")
    if args.command == "prepare":
        return prepare(args.mutant, args.workspace.resolve())
    rows = verify(args.mutant, args.workspace.resolve())
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
