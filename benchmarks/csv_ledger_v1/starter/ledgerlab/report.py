import json


def money(cents: int) -> str:
    return f"{cents // 100}.{abs(cents) % 100:02d}"


def render_report(summary: dict) -> str:
    return json.dumps({
        "count": summary["count"],
        "total": money(summary["total_cents"]),
        "categories": [
            {"category": row["category"], "count": row["count"], "total": money(row["total_cents"])}
            for row in summary["categories"]
        ],
    })
