"""
Formats Agent 2's output into the chat layer's fixed response structure:
a headline (bold recommendation sentence), an italicized rationale line,
then a fixed sequence of prose paragraphs with key figures marked for bold
emphasis (and the claim-identification parenthetical in italics) -- per the
output-formatting instructions.

Each paragraph is returned as a list of {"text": ..., "bold": ..., "italic":
...} segments rather than raw HTML, so the frontend controls
rendering/escaping while the backend controls exactly which parts get
emphasized.
"""

import re

DECISION_PHRASES = {
    "pursue": "pursue",
    "pursue_expedite": "pursue, but expedite filing",
    "do_not_pursue": "not pursue",
}


def money(v: float) -> str:
    return f"${v:,.2f}"


def pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def seg(text: str, bold: bool = False, italic: bool = False) -> dict:
    return {"text": text, "bold": bold, "italic": italic}


def _extract_year(date_of_service_bucket: str) -> str:
    match = re.search(r"\((\d{4})\)", date_of_service_bucket)
    return match.group(1) if match else date_of_service_bucket


def build_chat_response(agent2_output: dict, reference: str) -> dict:
    d = agent2_output
    decision_phrase = DECISION_PHRASES[d["decision"]]

    headline = f"For denial notice {reference}, the recommendation is to {decision_phrase}."
    rationale = d["rationale"]

    year = _extract_year(d["date_of_service_bucket"])
    total_days = round(d["time_to_resolution"])

    claim_descriptor = (
        f"({d['payer']}, {d['plan']}, {d['denial_reason_category']} denial, year {year})"
    )

    paragraph_1 = [
        seg("For a claim of this type "),
        seg(claim_descriptor, italic=True),
        seg(", we found "),
        seg(str(d["sample_size"]), bold=True),
        seg(" similar historical denials."),
    ]

    paragraph_2 = [
        seg("On average, the probability of success is "),
        seg(pct(d["win_probability"]), bold=True),
        seg(", and the expected payout percentage is "),
        seg(pct(d["avg_payout_pct"]), bold=True),
        seg("."),
    ]

    paragraph_3 = [
        seg("The expected average revenue from pursuing this appeal is "),
        seg(money(d["expected_recovery"]), bold=True),
        seg("."),
    ]

    paragraph_4 = [
        seg("An appeal of this type typically costs an additional "),
        seg(money(d["avg_appeal_cost"]), bold=True),
        seg(" to pursue, and is typically resolved within "),
        seg(str(total_days), bold=True),
        seg(" days."),
    ]

    paragraph_5 = [
        seg("The net profit expected from this claim is "),
        seg(money(d["net_expected_value"]), bold=True),
        seg(", adjusted for net present value: "),
        seg(money(d["npv"]), bold=True),
        seg("."),
    ]

    paragraphs = [paragraph_1, paragraph_2, paragraph_3, paragraph_4, paragraph_5]

    plain_text = "\n\n".join(
        [headline, rationale] + ["".join(s["text"] for s in p) for p in paragraphs]
    )

    return {
        "headline": headline,
        "rationale": rationale,
        "paragraphs": paragraphs,
        "plain_text": plain_text,
        "decision": d["decision"],
        "raw": d,
    }
