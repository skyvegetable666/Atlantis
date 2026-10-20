def summarize(records: list[dict], start: str | None = None, end: str | None = None) -> dict:
    chosen = [row for row in records
              if (start is None or row["date"] >= start) and (end is None or row["date"] < end)]
    categories = {}
    for row in chosen:
        group = categories.setdefault(row["category"], {"category": row["category"], "count": 0, "total_cents": 0})
        group["count"] += 1
        group["total_cents"] += row["amount_cents"]
    return {
        "count": len(chosen),
        "total_cents": sum(row["amount_cents"] for row in chosen),
        "categories": list(categories.values()),
    }
