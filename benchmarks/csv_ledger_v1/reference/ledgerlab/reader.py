import csv
import io
import re
from datetime import date


def read_records(text: str) -> list[dict]:
    if text.startswith("\ufeff"):
        text = text[1:]
    try:
        rows = iter(csv.reader(io.StringIO(text, newline=""), strict=True))
        header = next((row for row in rows if row), None)
        if header is None:
            return []
        if header != ["date", "category", "amount"]:
            raise ValueError("Expected date,category,amount header.")
        records = []
        for row in rows:
            if not row:
                continue
            if len(row) != 3:
                raise ValueError("Expected three fields per row.")
            day, category, amount = (cell.strip() for cell in row)
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day):
                raise ValueError("Expected an ISO date.")
            date.fromisoformat(day)
            if not category:
                raise ValueError("Category cannot be empty.")
            if not re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]{1,2})?", amount):
                raise ValueError("Expected an amount with at most two decimal places.")
            magnitude = amount.lstrip("+-")
            whole, _, fractional = magnitude.partition(".")
            cents = int(whole) * 100 + int(fractional.ljust(2, "0"))
            if amount.startswith("-"):
                cents = -cents
            records.append({"date": day, "category": category, "amount_cents": cents})
        return records
    except csv.Error as error:
        raise ValueError("Invalid CSV.") from error
