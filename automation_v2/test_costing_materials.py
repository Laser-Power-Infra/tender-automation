"""Costing material extraction self-check for duplicate header names. No DB, no network.

Run: uv run python -m automation_v2.test_costing_materials
"""
import openpyxl

from automation_v2.lib.costing_excel_parse import _parse_table

# Header row 1. "Alumimium" and "PVC" each appear on two columns.
# Rate row 2, data row 3.
GRID = [
    ["Docket No", "Propose ERP Item", "MFG %", "Copper", "Alumimium", "Alumimium", "PVC", "PVC", "Steel"],
    ["D1", None, None, 100, 367, 367, 80, 80, 50],        # rate row
    ["D1", "ITEM1", 10, 5, 270, 0, 0, 46, 0],             # data row
]
# Alumimium used on FIRST dup col (270) -> include. PVC used on LAST dup col (46) -> include.
# Copper unique, nonzero -> include. Steel unique, zero -> exclude.
EXPECTED = {"Copper": 100, "Alumimium": 367, "PVC": 80}

wb = openpyxl.Workbook()
ws = wb.active
for row in GRID:
    ws.append(row)

table = _parse_table(ws, 1, ws.max_row + 1)
assert table is not None, "table not parsed"
assert table["materials"] == EXPECTED, table["materials"]
assert "Steel" not in table["materials"]

print("costing materials self-check OK")
