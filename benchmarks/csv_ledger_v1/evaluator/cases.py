"""Private, fixed expectations; no expected result is calculated by the reference."""

HEADER = "date,category,amount\n"

CASES = [
    {"id": "read-empty", "group": "read", "operation": "read", "checks": [
        {"input": "", "expected": []}, {"input": "\n\n", "expected": []},
        {"input": HEADER, "expected": []},
    ]},
    {"id": "read-exact-cents", "group": "read", "operation": "read", "checks": [
        {"input": HEADER + "2026-01-01,A,1.13\n2026-01-02,B,-0.13\n2026-01-03,C,+001.2\n2026-01-04,D,-0.00\n",
         "expected": [
             {"date": "2026-01-01", "category": "A", "amount_cents": 113},
             {"date": "2026-01-02", "category": "B", "amount_cents": -13},
             {"date": "2026-01-03", "category": "C", "amount_cents": 120},
             {"date": "2026-01-04", "category": "D", "amount_cents": 0},
         ]},
    ]},
    {"id": "read-quoted-and-bom", "group": "read", "operation": "read", "checks": [
        {"input": '\ufeff' + HEADER + '2026-01-01,"Office, ""A""",2.00\n',
         "expected": [{"date": "2026-01-01", "category": 'Office, "A"', "amount_cents": 200}]},
    ]},
    {"id": "read-whitespace", "group": "read", "operation": "read", "checks": [
        {"input": HEADER + "\n 2026-01-02 , Food Shop , 1.2 \n\n",
         "expected": [{"date": "2026-01-02", "category": "Food Shop", "amount_cents": 120}]},
        {"input": HEADER + "2026-01-01, ,1.00\n", "error": "ValueError"},
    ]},
    {"id": "read-header-and-width", "group": "read", "operation": "read", "checks": [
        {"input": value, "error": "ValueError"} for value in (
            "category,date,amount\nFood,2026-01-01,1.00\n", "date,category,amount,extra\n",
            HEADER + "2026-01-01,Food\n", HEADER + "2026-01-01,Food,1.00,extra\n",
            "date,category, category\n", " date,category,amount\n",
        )
    ]},
    {"id": "read-calendar", "group": "read", "operation": "read", "checks": [
        {"input": HEADER + "2024-02-29,A,1\n", "expected": [{"date": "2024-02-29", "category": "A", "amount_cents": 100}]},
        *[{"input": HEADER + day + ",A,1.00\n", "error": "ValueError"}
          for day in ("2026-02-29", "20260101", "2026-1-01", "0000-01-01")],
    ]},
    {"id": "read-invalid-amounts", "group": "read", "operation": "read", "checks": [
        {"input": HEADER + "2026-01-01,A,1.00\n2026-01-02,B," + amount + "\n", "error": "ValueError"}
        for amount in ("1e2", "NaN", "Infinity", "1.005", ".50", "1.", "1_000", "", "\u0661.00")
    ]},
    {"id": "read-malformed-csv", "group": "read", "operation": "read", "checks": [
        {"input": HEADER + '2026-01-01,"Unclosed,1.00\n', "error": "ValueError"},
    ]},
    {"id": "sum-empty", "group": "sum", "operation": "sum", "checks": [
        {"input": [], "expected": {"count": 0, "total_cents": 0, "categories": []}},
    ]},
    {"id": "sum-inclusive-boundaries", "group": "sum", "operation": "sum", "checks": [
        {"input": [
            {"date": "2026-01-01", "category": "A", "amount_cents": 100},
            {"date": "2026-01-02", "category": "A", "amount_cents": 200},
            {"date": "2026-01-03", "category": "A", "amount_cents": 300},
        ], "kwargs": {"start": "2026-01-02", "end": "2026-01-03"},
         "expected": {"count": 2, "total_cents": 500, "categories": [{"category": "A", "count": 2, "total_cents": 500}]}},
    ]},
    {"id": "sum-one-sided", "group": "sum", "operation": "sum", "checks": [
        {"input": [{"date": "2026-01-02", "category": "A", "amount_cents": 200}],
         "kwargs": kwargs, "expected": {"count": 1, "total_cents": 200, "categories": [{"category": "A", "count": 1, "total_cents": 200}]}}
        for kwargs in ({"start": "2026-01-02"}, {"end": "2026-01-02"})
    ]},
    {"id": "sum-category-order", "group": "sum", "operation": "sum", "checks": [
        {"input": [
            {"date": "2026-01-01", "category": "z", "amount_cents": 1},
            {"date": "2026-01-01", "category": "Z", "amount_cents": 2},
            {"date": "2026-01-01", "category": "A", "amount_cents": 3},
        ], "expected": {"count": 3, "total_cents": 6, "categories": [
            {"category": "A", "count": 1, "total_cents": 3},
            {"category": "Z", "count": 1, "total_cents": 2},
            {"category": "z", "count": 1, "total_cents": 1},
        ]}},
    ]},
    {"id": "sum-refunds-and-duplicates", "group": "sum", "operation": "sum", "checks": [
        {"input": [
            {"date": "2026-01-01", "category": "A", "amount_cents": 113},
            {"date": "2026-01-01", "category": "A", "amount_cents": 113},
            {"date": "2026-01-02", "category": "A", "amount_cents": -226},
        ], "expected": {"count": 3, "total_cents": 0, "categories": [{"category": "A", "count": 3, "total_cents": 0}]}},
    ]},
    {"id": "sum-no-matches", "group": "sum", "operation": "sum", "checks": [
        {"input": [{"date": "2026-01-01", "category": "A", "amount_cents": 113}],
         "kwargs": {"start": "2026-01-02"}, "expected": {"count": 0, "total_cents": 0, "categories": []}},
    ]},
    {"id": "sum-invalid-dates-even-empty", "group": "sum", "operation": "sum", "checks": [
        {"input": [], "kwargs": kwargs, "error": "ValueError"} for kwargs in (
            {"start": "20260101"}, {"end": "2026-02-29"}, {"start": ""}, {"end": "2026-1-01"},
        )
    ]},
    {"id": "sum-reversed-even-empty", "group": "sum", "operation": "sum", "checks": [
        {"input": [], "kwargs": {"start": "2026-02-01", "end": "2026-01-01"}, "error": "ValueError"},
    ]},
    {"id": "report-empty", "group": "report", "operation": "report", "checks": [
        {"input": {"count": 0, "total_cents": 0, "categories": []},
         "expected": {"count": 0, "total": "0.00", "categories": []}},
    ]},
    {"id": "report-small-refund", "group": "report", "operation": "report", "checks": [
        {"input": {"count": 1, "total_cents": -1, "categories": [{"category": "A", "count": 1, "total_cents": -1}]},
         "expected": {"count": 1, "total": "-0.01", "categories": [{"category": "A", "count": 1, "total": "-0.01"}]}},
    ]},
    {"id": "report-negative-units", "group": "report", "operation": "report", "checks": [
        {"input": {"count": 1, "total_cents": -113, "categories": [{"category": "A", "count": 1, "total_cents": -113}]},
         "expected": {"count": 1, "total": "-1.13", "categories": [{"category": "A", "count": 1, "total": "-1.13"}]}},
    ]},
    {"id": "report-large-integer", "group": "report", "operation": "report", "checks": [
        {"input": {"count": 1, "total_cents": 9007199254740993, "categories": [{"category": "A", "count": 1, "total_cents": 9007199254740993}]},
         "expected": {"count": 1, "total": "90071992547409.93", "categories": [{"category": "A", "count": 1, "total": "90071992547409.93"}]}},
    ]},
    {"id": "report-escaped-category", "group": "report", "operation": "report", "checks": [
        {"input": {"count": 1, "total_cents": 113, "categories": [{"category": '\u9910\u996e, "A"', "count": 1, "total_cents": 113}]},
         "expected": {"count": 1, "total": "1.13", "categories": [{"category": '\u9910\u996e, "A"', "count": 1, "total": "1.13"}]}},
    ]},
    {"id": "report-zero-category", "group": "report", "operation": "report", "checks": [
        {"input": {"count": 2, "total_cents": 0, "categories": [{"category": "A", "count": 2, "total_cents": 0}]},
         "expected": {"count": 2, "total": "0.00", "categories": [{"category": "A", "count": 2, "total": "0.00"}]}},
    ]},
    {"id": "report-order-and-counts", "group": "report", "operation": "report", "checks": [
        {"input": {"count": 3, "total_cents": 550, "categories": [
            {"category": "A", "count": 2, "total_cents": 500}, {"category": "B", "count": 1, "total_cents": 50}]},
         "expected": {"count": 3, "total": "5.50", "categories": [
             {"category": "A", "count": 2, "total": "5.00"}, {"category": "B", "count": 1, "total": "0.50"}]}},
    ]},
    {"id": "report-padding", "group": "report", "operation": "report", "checks": [
        {"input": {"count": 1, "total_cents": 5, "categories": [{"category": "A", "count": 1, "total_cents": 5}]},
         "expected": {"count": 1, "total": "0.05", "categories": [{"category": "A", "count": 1, "total": "0.05"}]}},
    ]},
    {"id": "cli-basic", "group": "cli", "operation": "cli", "checks": [
        {"input": HEADER + "2026-01-01,A,1.13\n2026-01-02,B,-0.13\n", "expected": {
            "count": 2, "total": "1.00", "categories": [
                {"category": "A", "count": 1, "total": "1.13"}, {"category": "B", "count": 1, "total": "-0.13"}]}},
    ]},
    {"id": "cli-range-wiring", "group": "cli", "operation": "cli", "checks": [
        {"input": HEADER + "2026-01-01,A,1.00\n2026-01-02,A,2.00\n2026-01-03,A,3.00\n",
         "args": ["--start", "2026-01-02", "--end", "2026-01-03"],
         "expected": {"count": 2, "total": "5.00", "categories": [{"category": "A", "count": 2, "total": "5.00"}]}},
    ]},
    {"id": "cli-one-sided", "group": "cli", "operation": "cli", "checks": [
        {"input": HEADER + "2026-01-02,A,2.00\n", "args": args,
         "expected": {"count": 1, "total": "2.00", "categories": [{"category": "A", "count": 1, "total": "2.00"}]}}
        for args in (["--start", "2026-01-02"], ["--end", "2026-01-02"])
    ]},
    {"id": "cli-empty", "group": "cli", "operation": "cli", "checks": [
        {"input": "", "expected": {"count": 0, "total": "0.00", "categories": []}},
    ]},
    {"id": "cli-utf8-bom", "group": "cli", "operation": "cli", "checks": [
        {"input": '\ufeff' + HEADER + '2026-01-01,"\u9910\u996e, A",2\n',
         "expected": {"count": 1, "total": "2.00", "categories": [{"category": '\u9910\u996e, A', "count": 1, "total": "2.00"}]}},
    ]},
    {"id": "cli-missing-file", "group": "cli", "operation": "cli", "checks": [
        {"missing": True, "error": "cli"},
    ]},
    {"id": "cli-invalid-input", "group": "cli", "operation": "cli", "checks": [
        {"input": value, "error": "cli"} for value in (
            HEADER + "2026-01-01, ,1.00\n", HEADER + "2026-01-01,A,1.005\n", "bad,header\n", b"\xff\xfe\x00",
        )
    ]},
    {"id": "cli-invalid-range", "group": "cli", "operation": "cli", "checks": [
        {"input": "", "args": args, "error": "cli"} for args in (
            ["--start", "20260101"], ["--end", "2026-02-29"], ["--start", "2026-02-01", "--end", "2026-01-01"],
        )
    ]},
]
