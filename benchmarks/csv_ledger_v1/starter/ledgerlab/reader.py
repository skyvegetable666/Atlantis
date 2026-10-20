import csv
import io
from datetime import date


def read_records(text: str) -> list[dict]:
    records = []
    for row in csv.DictReader(io.StringIO(text)):
        records.append({
            "date": date.fromisoformat(row["date"]).isoformat(),
            "category": row["category"],
            "amount_cents": int(float(row["amount"]) * 100),
        })
    return records
