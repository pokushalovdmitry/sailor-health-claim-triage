"""
Loads the converted historical-denials / payer-rules JSON (produced by
scripts/convert_dataset_to_json.py from the reviewed .xlsx) into memory once,
and exposes small read-only helpers used by Agent 1 and Agent 2.
"""

import json
import os
from functools import lru_cache

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DENIALS_PATH = os.path.join(BASE_DIR, "data", "historical_denials.json")
RULES_PATH = os.path.join(BASE_DIR, "data", "payer_rules.json")


@lru_cache(maxsize=1)
def load_historical_denials():
    with open(DENIALS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_payer_rules():
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def payer_rules_lookup():
    """dict keyed by (payer, plan) -> deadline in days."""
    rules = load_payer_rules()
    return {
        (r["Payer"], r["Plan"]): r["Appeal Filing Deadline (Days from Denial Date)"]
        for r in rules
    }


@lru_cache(maxsize=1)
def known_payer_plans():
    """Ordered list of (payer, plan) tuples, grouped by payer, as they appear
    in the Payer Rules table -- the canonical set Agent 1 normalizes against."""
    rules = load_payer_rules()
    return [(r["Payer"], r["Plan"]) for r in rules]


def known_payer_plans_prompt_text():
    """Formats the canonical payer/plan list for injection into Agent 1's
    Claude call, grouped by payer so the model can normalize casing/wording."""
    rules = load_payer_rules()
    by_payer = {}
    for r in rules:
        by_payer.setdefault(r["Payer"], []).append(r["Plan"])
    lines = []
    for payer, plans in by_payer.items():
        lines.append(f"- {payer}: {', '.join(plans)}")
    return "\n".join(lines)
