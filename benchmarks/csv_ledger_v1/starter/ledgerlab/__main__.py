import argparse
from pathlib import Path

from .aggregate import summarize
from .reader import read_records
from .report import render_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize a CSV ledger.")
    parser.add_argument("input")
    parser.add_argument("--start")
    parser.add_argument("--end")
    args = parser.parse_args()
    records = read_records(Path(args.input).read_text(encoding="utf-8"))
    print(render_report(summarize(records, start=args.end, end=args.start)))


if __name__ == "__main__":
    main()
