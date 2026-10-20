import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


class CSVTaskPackTests(unittest.TestCase):
    def test_task_materials_scoring_and_public_projection(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "-I", "-B", str(root / "benchmarks/csv_ledger_v1/verify.py")],
            cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=30,
            env={"PATH": os.defpath, "PYTHONIOENCODING": "utf-8"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["manifest_verified"])
        self.assertTrue(report["public_allowlist_verified"])
        self.assertEqual(report["public_tests_passed"], {"starter": False, "reference": True})
        self.assertEqual(report["independent_cases"], 32)
        self.assertEqual(report["independent_scores"]["reference"], 100)
        self.assertTrue(report["repeatable"])
        self.assertEqual(len(report["module_regression_scores"]), 4)
        self.assertTrue(all(score < 100 for score in report["module_regression_scores"].values()))


if __name__ == "__main__":
    unittest.main()
