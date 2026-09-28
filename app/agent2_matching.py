"""
Agent 2 -- matching and calculation.

Deterministic, no LLM call: exact-match filtering plus fixed arithmetic, per
app/skills/agent2_matching_skill.md (the authoritative spec for every formula
below). Kept as plain code rather than a model call because there is no
judgment call anywhere in this pipeline stage, and financial figures should
never be left to sampling.
"""

from .data_store import load_historical_denials, payer_rules_lookup

# A round, easy-to-read placeholder threshold, not a fitted or fully
# justified figure. The project spec's initial suggestion was $100, tied to
# an industry finding that claims below roughly that size are commonly
# written off regardless of win probability; lowered to $50 per product
# decision to let a bit more of the thin-but-positive middle through while
# still screening out negligible claims. Expected to be revisited once real
# Sailor claims data exists.
MIN_NET_VALUE_THRESHOLD_USD = 50

DISCOUNT_RATE_ANNUAL = 0.10  # fixed, not user-configurable in this prototype


class MatchingError(Exception):
    """Raised when Agent 2 cannot proceed: no historical subset, or no
    payer-rules entry, for the given claim. Should not occur in normal
    operation given the dataset's construction -- surfaced clearly rather
    than silently producing a zero/garbage result."""


def match_subset(claim: dict, denials: list = None) -> list:
    denials = denials if denials is not None else load_historical_denials()
    return [
        row
        for row in denials
        if row["Denial Reason Category"] == claim["denial_reason_category"]
        and row["Payer"] == claim["payer"]
        and row["Plan"] == claim["plan"]
        and row["Date of Service Bucket"] == claim["date_of_service_bucket"]
    ]


def compute_statistics(subset: list) -> dict:
    n = len(subset)
    won_rows = [r for r in subset if r["Appealed - Won"]]

    win_probability = len(won_rows) / n
    avg_payout_pct = (
        sum(r["Payout % (if Won)"] for r in won_rows) / len(won_rows)
        if won_rows
        else 0.0
    )
    avg_days_to_file = sum(r["Days: Denial to Appeal Filed"] for r in subset) / n
    avg_days_to_resolve = sum(r["Days: Appeal Filed to Resolution"] for r in subset) / n
    avg_appeal_cost = sum(r["Appeal Cost ($)"] for r in subset) / n

    return {
        "sample_size": n,
        "win_probability": win_probability,
        "avg_payout_pct": avg_payout_pct,
        "avg_days_to_file": avg_days_to_file,
        "avg_days_to_resolve": avg_days_to_resolve,
        "avg_appeal_cost": avg_appeal_cost,
    }


def lookup_deadline(payer: str, plan: str) -> int:
    rules = payer_rules_lookup()
    key = (payer, plan)
    if key not in rules:
        raise MatchingError(f"No Payer Rules entry for payer={payer!r}, plan={plan!r}")
    return rules[key]


def compute_financials(billed_amount: float, stats: dict, deadline_days: int) -> dict:
    expected_recovery = billed_amount * stats["win_probability"] * stats["avg_payout_pct"]
    net_expected_value = expected_recovery - stats["avg_appeal_cost"]
    time_to_resolution = stats["avg_days_to_file"] + stats["avg_days_to_resolve"]
    npv = net_expected_value / ((1 + DISCOUNT_RATE_ANNUAL) ** (time_to_resolution / 365))
    feasible = deadline_days >= stats["avg_days_to_file"]

    return {
        "expected_recovery": expected_recovery,
        "net_expected_value": net_expected_value,
        "time_to_resolution": time_to_resolution,
        "npv": npv,
        "feasible": feasible,
    }


def recommend(net_expected_value: float, feasible: bool, threshold: float = MIN_NET_VALUE_THRESHOLD_USD):
    """Returns (decision, rationale) per the skill's Step 5 branches.
    decision is one of: 'pursue', 'pursue_expedite', 'do_not_pursue'."""
    value_ok = net_expected_value > threshold

    if value_ok and feasible:
        decision = "pursue"
        rationale = f"Expected net value is above ${threshold:,.0f}, and filing pace meets the deadline."
    elif value_ok and not feasible:
        decision = "pursue_expedite"
        rationale = (
            f"Expected net value is above ${threshold:,.0f}. Average filing time typically "
            "exceeds the remaining deadline for this claim type -- expediting would be "
            "required to make the deadline, but the expected value justifies the effort if "
            "that's achievable."
        )
    elif not value_ok and feasible:
        decision = "do_not_pursue"
        rationale = f"Expected net value is below ${threshold:,.0f}."
    else:
        decision = "do_not_pursue"
        rationale = (
            f"Expected net value is below ${threshold:,.0f}, and average filing time also "
            "exceeds the remaining deadline for this claim type."
        )

    return decision, rationale


def run_agent2(claim: dict) -> dict:
    """claim: Agent 1's trimmed output (see agent1_extraction.to_agent2_input).
    Returns every figure + the recommendation, ready for the chat layer."""
    subset = match_subset(claim)
    if not subset:
        raise MatchingError(
            "No historical denials match this claim's category/payer/plan/date-bucket "
            "combination -- cannot compute a recommendation."
        )
    stats = compute_statistics(subset)
    deadline_days = lookup_deadline(claim["payer"], claim["plan"])
    financials = compute_financials(claim["billed_amount"], stats, deadline_days)
    decision, rationale = recommend(financials["net_expected_value"], financials["feasible"])

    return {
        **stats,
        **financials,
        "appeal_filing_deadline_days": deadline_days,
        "decision": decision,
        "rationale": rationale,
        "billed_amount": claim["billed_amount"],
        "denial_reason_category": claim["denial_reason_category"],
        "payer": claim["payer"],
        "plan": claim["plan"],
        "date_of_service_bucket": claim["date_of_service_bucket"],
    }
