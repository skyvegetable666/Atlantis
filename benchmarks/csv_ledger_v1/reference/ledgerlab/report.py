import json


def money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    whole, fractional = divmod(abs(cents), 100)
    return f"{sign}{whole}.{fractional:02d}"


def render_report(summary: dict) -> str:
    return json.dumps({
        "count": summary["count"],
        "total": money(summary["total_cents"]),
        "categories": [
            {"category": row["category"], "count": row["count"], "total": money(row["total_cents"])}
            for row in summary["categories"]
        ],
    }, ensure_ascii=False)
