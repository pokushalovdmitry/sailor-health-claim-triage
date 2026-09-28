"""
Direct conversion of the reviewed historical_denial_dataset.xlsx into the JSON
files the web app reads at runtime.

This performs NO regeneration and NO recalculation -- it reads the exact values
a human already reviewed and confirmed in the .xlsx workbook and writes them
out as JSON, unchanged. If the dataset is ever revised, re-run this script
against the updated workbook; do not hand-edit the JSON files.
"""

import json
import os
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XLSX_PATH = os.path.join(BASE_DIR, "data", "historical_denial_dataset.xlsx")
DENIALS_OUT = os.path.join(BASE_DIR, "data", "historical_denials.json")
RULES_OUT = os.path.join(BASE_DIR, "data", "payer_rules.json")


def main():
    denials_df = pd.read_excel(XLSX_PATH, sheet_name="Historical Denials")
    rules_df = pd.read_excel(XLSX_PATH, sheet_name="Payer Rules")

    # Booleans/NaNs round-trip cleanly through pandas -> Python native types
    denials_records = denials_df.where(pd.notnull(denials_df), None).to_dict(orient="records")
    rules_records = rules_df.where(pd.notnull(rules_df), None).to_dict(orient="records")

    # Sanity checks -- fail loudly if the reviewed workbook doesn't look like
    # what the app expects, rather than silently shipping a bad conversion.
    # 900-row baseline (25 per cell) plus a few cells with extra rows added
    # on top -- see generate_dataset.py's EXTRA_ROWS_PLAN -- so the total is
    # >= 900, not necessarily exactly 900.
    assert len(denials_records) >= 900, f"expected at least 900 historical rows, got {len(denials_records)}"
    assert len(rules_records) == 9, f"expected 9 payer/plan rules, got {len(rules_records)}"
    for r in denials_records:
        assert r["Denial Reason Category"] in ("Technical", "Clinical")
        assert r["Appealed - Won"] in (True, False)

    with open(DENIALS_OUT, "w", encoding="utf-8") as f:
        json.dump(denials_records, f, indent=2, default=str)
    with open(RULES_OUT, "w", encoding="utf-8") as f:
        json.dump(rules_records, f, indent=2, default=str)

    print(f"Wrote {len(denials_records)} rows -> {DENIALS_OUT}")
    print(f"Wrote {len(rules_records)} rows -> {RULES_OUT}")


if __name__ == "__main__":
    main()
