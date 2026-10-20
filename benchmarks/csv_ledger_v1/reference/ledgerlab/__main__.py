import argparse
import sys
from pathlib import Path

from .aggregate import summarize
from .reader import read_records
from .report import render_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize a CSV ledger.")
    parser.add_argument("input")
    parser.add_argument("--start")
    parser.add_argument("--end")
    args = parser.parse_args()
    try:
        records = read_records(Path(args.input).read_text(encoding="utf-8-sig"))
        report = render_report(summarize(records, start=args.start, end=args.end))
    except (ValueError, OSError) as error:
        print(f"Invalid input: {error}", file=sys.stderr)
        return 2
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
