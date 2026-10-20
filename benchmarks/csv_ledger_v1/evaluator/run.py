"""Developer-only evaluator for two repository-owned, trusted fixtures."""

import argparse
import copy
import importlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cases import CASES

GROUPS = ("read", "sum", "report", "cli")
CLI_BOOT = "import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); runpy.run_module('ledgerlab',run_name='__main__')"
CLEAN_ENV = {"PATH": os.defpath, "PYTHONIOENCODING": "utf-8"}


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False)


def check_cli(candidate: Path, check: dict) -> None:
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "input.csv"
        if not check.get("missing"):
            content = check["input"]
            source.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-c", CLI_BOOT, str(candidate), str(source), *check.get("args", [])],
            cwd=directory, env=CLEAN_ENV, capture_output=True, text=True, encoding="utf-8", timeout=3,
        )
    if "error" in check:
        if result.returncode != 2 or result.stdout or not result.stderr.strip() or "Traceback" in result.stderr:
            raise AssertionError("Expected exit 2, empty stdout and an error without a traceback.")
    else:
        if result.returncode != 0 or result.stderr or not result.stdout.endswith("\n"):
            raise AssertionError("Expected exit 0, newline-terminated stdout and empty stderr.")
        if canonical(json.loads(result.stdout)) != canonical(check["expected"]):
            raise AssertionError("CLI report differs from the contract.")


def check_function(function, check: dict, decode_json: bool = False) -> None:
    value = copy.deepcopy(check["input"])
    before = canonical(value)
    try:
        actual = function(value, **check.get("kwargs", {}))
    except ValueError:
        if check.get("error") != "ValueError":
            raise
    else:
        if "error" in check:
            raise AssertionError("Expected ValueError for invalid input.")
        if decode_json:
            if not isinstance(actual, str):
                raise AssertionError("The report must be JSON text.")
            actual = json.loads(actual)
        if canonical(actual) != canonical(check["expected"]):
            raise AssertionError("Function output differs from the contract.")
    if canonical(value) != before:
        raise AssertionError("The function changed its input.")


def evaluate(fixture: str) -> dict:
    if fixture not in ("starter", "reference"):
        raise ValueError("Only repository-owned starter and reference fixtures are supported.")
    candidate = PACK / fixture
    sys.path.insert(0, str(candidate))
    functions = {}
    import_error = None
    try:
        functions = {
            "read": importlib.import_module("ledgerlab.reader").read_records,
            "sum": importlib.import_module("ledgerlab.aggregate").summarize,
            "report": importlib.import_module("ledgerlab.report").render_report,
        }
    except Exception as error:
        import_error = type(error).__name__
    groups = {group: {"passed": 0, "total": 0, "score": 0.0, "maximum": 25} for group in GROUPS}
    results = []
    for case in CASES:
        group = groups[case["group"]]
        group["total"] += 1
        failure = None
        try:
            if import_error:
                raise RuntimeError(f"Fixture import failed: {import_error}.")
            for check in case["checks"]:
                if case["operation"] == "cli":
                    check_cli(candidate, check)
                else:
                    check_function(functions[case["operation"]], check, case["operation"] == "report")
        except Exception as error:
            failure = f"{type(error).__name__}: {error}"[:400]
        if failure is None:
            group["passed"] += 1
        results.append({"id": case["id"], "group": case["group"], "passed": failure is None, "failure": failure})
    for group in groups.values():
        group["score"] = 25 * group["passed"] / group["total"]
    return {
        "task_id": "csv-ledger-repair-v1", "evaluation_version": 1, "fixture": fixture,
        "score": sum(group["score"] for group in groups.values()),
        "passed": all(case["passed"] for case in results), "groups": groups, "cases": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", choices=("starter", "reference"), required=True)
    args = parser.parse_args()
    report = evaluate(args.fixture)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
