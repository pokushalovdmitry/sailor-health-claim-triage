"""
Unit tests for Agent 2, run against known-correct Agent-1-shaped fixtures
(the ground truth for the 5 sample claim PDFs, known because we generated
those PDFs from these exact dataset rows in the first place) -- per the
build order, Agent 2 is tested against confirmed-correct Agent 1 output
shapes before any live extraction checkpoint is required.

Run with: python -m pytest tests/test_agent2.py -v
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent2_matching import (
    MIN_NET_VALUE_THRESHOLD_USD,
    MatchingError,
    compute_financials,
    compute_statistics,
    lookup_deadline,
    match_subset,
    recommend,
    run_agent2,
)
from app.chat_formatter import build_chat_response

# Ground truth Agent-1-shaped inputs for the 5 sample claims (see
# scripts/generate_sample_claims.py for how these PDFs were built).
SAMPLE_CLAIMS = {
    "claim_1_technical_strong": {
        "denial_reason_category": "Technical",
        "payer": "Northlake Medicare Solutions",
        "plan": "Complete Care",
        "date_of_service_bucket": "This Year (2026)",
        "denial_date": "2026-08-02",
        "billed_amount": 315.00,
    },
    "claim_2_clinical_weak": {
        "denial_reason_category": "Clinical",
        "payer": "Cascade Health Partners",
        "plan": "Advantage Choice",
        "date_of_service_bucket": "Prior Year (2025)",
        "denial_date": "2025-11-05",
        "billed_amount": 340.00,
    },
    "claim_3_high_dollar": {
        "denial_reason_category": "Clinical",
        "payer": "Summit Point Health",
        "plan": "Value Plan",
        "date_of_service_bucket": "This Year (2026)",
        "denial_date": "2026-06-10",
        "billed_amount": 500.00,
    },
    "claim_4_low_dollar": {
        "denial_reason_category": "Technical",
        "payer": "Cascade Health Partners",
        "plan": "Advantage Plus",
        "date_of_service_bucket": "Prior Year (2025)",
        "denial_date": "2025-05-01",
        "billed_amount": 115.00,
    },
    "claim_5_deadline_infeasible": {
        "denial_reason_category": "Technical",
        "payer": "Summit Point Health",
        "plan": "Standard Plan",
        "date_of_service_bucket": "This Year (2026)",
        "denial_date": "2026-09-14",
        "billed_amount": 445.00,
    },
}


# A few cells intentionally have extra rows added on top of the 25-row
# baseline (see scripts/generate_dataset.py's EXTRA_ROWS_PLAN), so sample
# sizes vary realistically across the 5 sample claims instead of a flat 25.
EXPECTED_SAMPLE_SIZE = {
    "claim_1_technical_strong": 60,
    "claim_2_clinical_weak": 40,
    "claim_3_high_dollar": 25,
    "claim_4_low_dollar": 33,
    "claim_5_deadline_infeasible": 25,
}


def test_every_combination_has_a_nonempty_subset_with_expected_size():
    """The dataset was built to guarantee every cell is non-empty, and these
    5 specific cells to have the exact sizes above."""
    for name, claim in SAMPLE_CLAIMS.items():
        subset = match_subset(claim)
        expected = EXPECTED_SAMPLE_SIZE[name]
        assert len(subset) == expected, f"{name}: expected {expected} rows, got {len(subset)}"


def test_win_probability_within_sense_check_bands():
    for name, claim in SAMPLE_CLAIMS.items():
        stats = compute_statistics(match_subset(claim))
        if claim["denial_reason_category"] == "Technical":
            assert 0.60 <= stats["win_probability"] <= 0.95, name
        else:
            assert 0.20 <= stats["win_probability"] <= 0.65, name


def test_claim_1_clear_pursue():
    result = run_agent2(SAMPLE_CLAIMS["claim_1_technical_strong"])
    assert result["decision"] == "pursue"
    assert result["feasible"] is True
    assert result["net_expected_value"] > MIN_NET_VALUE_THRESHOLD_USD


def test_claim_4_low_dollar_fails_value_threshold_despite_good_odds():
    result = run_agent2(SAMPLE_CLAIMS["claim_4_low_dollar"])
    # Decent win probability (duplicate-claim technical reasons run hot), but the
    # $115 billed amount is too small for net EV to clear $50 once the ~$60-90
    # appeal cost is subtracted -- net EV is actually negative here.
    assert result["win_probability"] >= 0.6
    assert result["decision"] == "do_not_pursue"
    assert result["net_expected_value"] <= MIN_NET_VALUE_THRESHOLD_USD


def test_claim_5_deadline_infeasible_overrides_good_economics():
    result = run_agent2(SAMPLE_CLAIMS["claim_5_deadline_infeasible"])
    assert result["appeal_filing_deadline_days"] == 10
    assert result["feasible"] is False
    # Large billed amount + high win rate -> good economics...
    assert result["net_expected_value"] > MIN_NET_VALUE_THRESHOLD_USD
    # ...but the 10-day deadline against a 5-20 day filing window trips the
    # feasibility flag, so this must land on pursue_expedite, not a clean pursue.
    assert result["decision"] == "pursue_expedite"
    assert "expedit" in result["rationale"].lower()  # matches "expedite"/"expediting"


def test_recommend_all_four_branches_directly():
    pursue, r1 = recommend(net_expected_value=200, feasible=True)
    assert pursue == "pursue"
    assert "above" in r1 and "filing pace meets" in r1

    expedite, r2 = recommend(net_expected_value=200, feasible=False)
    assert expedite == "pursue_expedite"
    assert "expedit" in r2.lower() or "faster" in r2.lower()

    dnp1, r3 = recommend(net_expected_value=20, feasible=True)
    assert dnp1 == "do_not_pursue"
    assert "below" in r3 and "also exceeds" not in r3

    dnp2, r4 = recommend(net_expected_value=20, feasible=False)
    assert dnp2 == "do_not_pursue"
    assert "below" in r4 and "also exceeds" in r4  # both reasons stated together


def test_boundary_exactly_at_threshold_is_not_a_pursue():
    decision, _ = recommend(net_expected_value=MIN_NET_VALUE_THRESHOLD_USD, feasible=True)
    assert decision == "do_not_pursue"


def test_deadline_lookup_matches_payer_rules_sheet():
    assert lookup_deadline("Summit Point Health", "Standard Plan") == 10
    assert lookup_deadline("Northlake Medicare Solutions", "Complete Care") == 120


def test_unknown_payer_plan_raises_matching_error():
    try:
        lookup_deadline("Nonexistent Payer", "Nonexistent Plan")
        assert False, "expected MatchingError"
    except MatchingError:
        pass


def _flatten(paragraph):
    return "".join(s["text"] for s in paragraph)


def _bold_texts(paragraph):
    return [s["text"] for s in paragraph if s["bold"]]


def _italic_texts(paragraph):
    return [s["text"] for s in paragraph if s["italic"]]


def test_chat_response_structure_and_ordering():
    result = run_agent2(SAMPLE_CLAIMS["claim_1_technical_strong"])
    chat = build_chat_response(result, reference="claim_1_technical_strong.pdf")
    assert chat["headline"] == "For denial notice claim_1_technical_strong.pdf, the recommendation is to pursue."
    assert len(chat["paragraphs"]) == 5

    p1, p2, p3, p4, p5 = chat["paragraphs"]

    assert _flatten(p1) == (
        "For a claim of this type (Northlake Medicare Solutions, Complete Care, "
        "Technical denial, year 2026), we found 60 similar historical denials."
    )
    # The whole claim-identifying parenthetical is one italic segment, not bolded;
    # only the sample size (a number) is bold.
    assert _italic_texts(p1) == ["(Northlake Medicare Solutions, Complete Care, Technical denial, year 2026)"]
    assert _bold_texts(p1) == ["60"]

    assert "probability of success" in _flatten(p2)
    assert "expected average revenue" not in _flatten(p2)  # now its own paragraph

    assert "expected average revenue" in _flatten(p3)

    assert "typically costs an additional" in _flatten(p4)
    assert "typically resolved within" in _flatten(p4)

    assert "net profit expected" in _flatten(p5)
    assert "net present value" in _flatten(p5)
    assert len(_bold_texts(p5)) == 2  # net expected value and NPV, both dollar figures


def test_paragraphs_2_through_5_only_bold_numbers_and_have_no_italics():
    """Paragraph 1 italicizes the claim-identifying parenthetical and bolds
    only the sample size; paragraphs 2-5 bold numbers only (dollars/percents/
    day counts) and use no italics."""
    result = run_agent2(SAMPLE_CLAIMS["claim_3_high_dollar"])
    chat = build_chat_response(result, reference="claim_3_high_dollar.pdf")
    number_pattern = re.compile(r"^-?\$?[\d,]+(\.\d+)?%?$")
    for paragraph in chat["paragraphs"][1:]:
        for s in paragraph:
            assert not s["italic"]
            if s["bold"]:
                assert number_pattern.match(s["text"]), f"unexpected bold segment: {s['text']!r}"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
