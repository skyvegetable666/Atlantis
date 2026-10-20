import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ledgerlab.aggregate import summarize
from ledgerlab.reader import read_records
from ledgerlab.report import render_report


class PublicExamples(unittest.TestCase):
    def test_basic_read(self):
        records = read_records("date,category,amount\n2026-01-01,Food,2.50\n")
        self.assertEqual(records, [{"date": "2026-01-01", "category": "Food", "amount_cents": 250}])

    def test_end_date_is_inclusive(self):
        records = [{"date": "2026-01-02", "category": "Food", "amount_cents": 100}]
        self.assertEqual(summarize(records, end="2026-01-02")["count"], 1)

    def test_refund_smaller_than_one_unit(self):
        report = json.loads(render_report({"count": 1, "total_cents": -13, "categories": []}))
        self.assertEqual(report["total"], "-0.13")

    def test_invalid_category_rejects_the_whole_input(self):
        with self.assertRaises(ValueError):
            read_records("date,category,amount\n2026-01-01,Food,1.00\n2026-01-02, ,2.00\n")

    def test_cli_connects_the_start_and_end_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.csv"
            source.write_text("date,category,amount\n2026-01-01,Food,1.00\n2026-01-02,Food,2.00\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-B", "-m", "ledgerlab", str(source), "--start", "2026-01-02", "--end", "2026-01-02"],
                capture_output=True, text=True, timeout=3,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["total"], "2.00")


if __name__ == "__main__":
    unittest.main()
