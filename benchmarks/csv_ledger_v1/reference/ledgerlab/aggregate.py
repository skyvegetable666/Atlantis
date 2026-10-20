import re
from datetime import date


def _date(value: str) -> date:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("Expected an ISO date.")
    return date.fromisoformat(value)


def summarize(records: list[dict], start: str | None = None, end: str | None = None) -> dict:
    first = _date(start) if start is not None else None
    last = _date(end) if end is not None else None
    if first is not None and last is not None and first > last:
        raise ValueError("Start date must not follow end date.")
    groups = {}
    count = total = 0
    for row in records:
        day = _date(row["date"])
        if (first is not None and day < first) or (last is not None and day > last):
            continue
        group = groups.setdefault(row["category"], {"category": row["category"], "count": 0, "total_cents": 0})
        group["count"] += 1
        group["total_cents"] += row["amount_cents"]
        count += 1
        total += row["amount_cents"]
    return {"count": count, "total_cents": total, "categories": [groups[key] for key in sorted(groups)]}
