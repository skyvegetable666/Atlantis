"""Check the task pack, its public projection and trusted fixtures."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PACK = Path(__file__).resolve().parent
TASK_ID = "csv-ledger-repair-v1"
CLEAN_ENV = {"PATH": os.defpath, "PYTHONIOENCODING": "utf-8"}
PUBLIC_BOOT = "import sys,unittest; sys.path.insert(0,'.'); r=unittest.TextTestRunner().run(unittest.defaultTestLoader.discover('public_tests')); sys.exit(not r.wasSuccessful())"
PUBLIC_FILES = (
    "task.md", "examples/basic.csv", "public_tests/test_examples.py",
    "ledgerlab/__init__.py", "ledgerlab/reader.py", "ledgerlab/aggregate.py",
    "ledgerlab/report.py", "ledgerlab/__main__.py",
)


def files() -> list[Path]:
    return sorted(path for path in PACK.rglob("*") if path.is_file() and path.suffix in (".py", ".md", ".csv"))


def manifest() -> dict:
    return {
        "task_id": TASK_ID, "version": 1, "status": "candidate",
        "groups": {"read": 25, "sum": 25, "report": 25, "cli": 25},
        "files": {str(path.relative_to(PACK)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files()},
    }


def export_public(destination: Path, fixture: str = "starter") -> None:
    if fixture not in ("starter", "reference"):
        raise ValueError("Unknown fixture.")
    destination.mkdir(parents=True, exist_ok=False)
    for relative in PUBLIC_FILES:
        prefix = fixture if relative.startswith("ledgerlab/") else "starter" if relative.startswith("examples/") else ""
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PACK / prefix / relative, target)


def run_evaluator(fixture: str, pack: Path = PACK) -> dict:
    result = subprocess.run(
        [sys.executable, "-I", "-B", str(pack / "evaluator" / "run.py"), "--fixture", fixture],
        capture_output=True, text=True, encoding="utf-8", env=CLEAN_ENV, timeout=30,
    )
    if result.returncode not in (0, 1) or result.stderr:
        raise AssertionError("Evaluator did not finish normally: " + result.stderr[:400])
    return json.loads(result.stdout)


def verify() -> dict:
    recorded = json.loads((PACK / "manifest.json").read_text())
    if recorded != manifest():
        raise AssertionError("Task contents differ from the recorded manifest.")
    public_results = {}
    with tempfile.TemporaryDirectory() as directory:
        for fixture in ("starter", "reference"):
            destination = Path(directory) / fixture
            export_public(destination, fixture)
            actual_files = {str(path.relative_to(destination)) for path in destination.rglob("*") if path.is_file()}
            if actual_files != set(PUBLIC_FILES):
                raise AssertionError("Public export differs from its allowlist.")
            result = subprocess.run(
                [sys.executable, "-I", "-B", "-c", PUBLIC_BOOT], cwd=destination,
                capture_output=True, text=True, encoding="utf-8", env=CLEAN_ENV, timeout=15,
            )
            public_results[fixture] = result.returncode == 0
        if public_results != {"starter": False, "reference": True}:
            raise AssertionError("Public tests did not distinguish the two fixtures.")
    initial = run_evaluator("starter")
    reference = run_evaluator("reference")
    if initial["passed"] or not 0 < initial["score"] < 100 or not reference["passed"] or reference["score"] != 100:
        raise AssertionError("Independent scoring did not distinguish the two fixtures.")
    if any(group["total"] != 8 for group in reference["groups"].values()):
        raise AssertionError("The score must contain eight cases per group.")
    if reference != run_evaluator("reference") or initial != run_evaluator("starter"):
        raise AssertionError("Repeated evaluation changed the report.")
    mutation_scores = {}
    with tempfile.TemporaryDirectory() as directory:
        for module, group in (("reader", "read"), ("aggregate", "sum"), ("report", "report"), ("__main__", "cli")):
            mutant = Path(directory) / module
            shutil.copytree(PACK / "reference", mutant / "reference")
            shutil.copytree(PACK / "evaluator", mutant / "evaluator")
            shutil.copy2(PACK / "starter" / "ledgerlab" / f"{module}.py", mutant / "reference" / "ledgerlab" / f"{module}.py")
            degraded = run_evaluator("reference", mutant)
            if degraded["passed"] or degraded["groups"][group]["score"] >= 25:
                raise AssertionError(f"The evaluator missed a regression in {module}.")
            mutation_scores[module] = degraded["score"]
    return {
        "task_id": TASK_ID, "manifest_verified": True, "public_allowlist_verified": True,
        "public_tests_passed": public_results,
        "independent_scores": {"starter": initial["score"], "reference": reference["score"]},
        "independent_cases": len(reference["cases"]), "repeatable": True,
        "module_regression_scores": mutation_scores,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-manifest", action="store_true")
    parser.add_argument("--export-public", type=Path)
    args = parser.parse_args()
    if args.write_manifest:
        (PACK / "manifest.json").write_text(json.dumps(manifest(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif args.export_public:
        export_public(args.export_public)
        print(f"Public task exported to {args.export_public.resolve()}")
    else:
        print(json.dumps(verify(), ensure_ascii=False, indent=2))
