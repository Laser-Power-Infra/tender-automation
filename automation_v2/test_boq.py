"""BOQ parser self-check. No DB, no network: writes small xlsx/csv files and parses them.

Run: uv run python -m automation_v2.test_boq
"""
import csv
import os
import tempfile

import openpyxl

from automation_v2.lib.boq_parser import parse_boq

GRID = [
    ["Title"],
    [None],
    ["S.No", "Item Description", "Qty", "Unit"],
    [1, "Cable 3C", "1,200", "m"],
    [2, "Kit", None, None],
    [3, None, 5, "nos"],     # no description: skipped
    [4, "123", 1, "x"],      # numeric description: skipped
]
EXPECTED = [
    {"description": "Cable 3C", "quantity": 1200.0, "unit": "m"},
    {"description": "Kit", "quantity": "no_quantity_available", "unit": ""},
]

d = tempfile.mkdtemp()
wb = openpyxl.Workbook()
for row in GRID:
    wb.active.append(row)
wb.save(xlsx := os.path.join(d, "boq.xlsx"))
with open(csv_path := os.path.join(d, "boq.csv"), "w", newline="", encoding="utf-8") as f:
    csv.writer(f).writerows([["" if v is None else v for v in row] for row in GRID])

assert parse_boq(xlsx) == EXPECTED, parse_boq(xlsx)
assert parse_boq(csv_path) == EXPECTED, parse_boq(csv_path)

wb = openpyxl.Workbook()
wb.active.append(["no header here"])
wb.save(bad := os.path.join(d, "bad.xlsx"))
try:
    parse_boq(bad)
    raise AssertionError("expected ValueError")
except ValueError as e:
    assert "header row" in str(e)

# the BOQ picker only takes spreadsheets, and Drive links are recognised with or without a trailing slash
from automation_v2.lib.boq_parser import find_boq_file  # noqa: E402
from automation_v2.lib.costing_excel_parse import _extract_drive_file_id  # noqa: E402

assert find_boq_file(["/x/BOQ_notes.pdf", "/x/BOQ.xlsx"]) == "/x/BOQ.xlsx"
assert find_boq_file(["/x/BOQ_notes.pdf", "/x/NIT.xlsx"]) is None
assert _extract_drive_file_id("https://drive.google.com/file/d/ID1") == "ID1"
assert _extract_drive_file_id("https://drive.google.com/file/d/ID1/view?usp=sharing") == "ID1"
assert _extract_drive_file_id("https://drive.google.com/open?id=ID1") == "ID1"

print("boq self-check OK")
