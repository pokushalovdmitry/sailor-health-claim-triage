"""
Agent 1 -- claim extraction.

Takes an uploaded denial notice PDF and turns it into structured data via a
Claude API call (the document's layout isn't standardized across payers, so
this genuinely needs a model reading for meaning, not a fixed-template
parser). Loads app/skills/agent1_extraction_skill.md as its system prompt.

Requires ANTHROPIC_API_KEY to be set in the environment. Never hardcode a key
here or anywhere else in this project.
"""

import base64
import os
from datetime import date, datetime
from functools import lru_cache

import anthropic

from .data_store import known_payer_plans_prompt_text

SKILL_PATH = os.path.join(os.path.dirname(__file__), "skills", "agent1_extraction_skill.md")
DEFAULT_MODEL = os.environ.get("AGENT1_MODEL", "claude-sonnet-5")

EXTRACT_TOOL = {
    "name": "extract_denial_notice",
    "description": (
        "Record the structured fields extracted from a verified, valid "
        "denial notice."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "denial_reason_code": {
                "type": ["string", "null"],
                "description": "CARC-style code as stated on the notice, e.g. 'CO-197'. Null if no code is stated.",
            },
            "denial_reason_description": {
                "type": "string",
                "description": "Plain-language denial reason exactly as explained on the notice.",
            },
            "denial_reason_category": {
                "type": "string",
                "enum": ["Technical", "Clinical"],
                "description": "Classification of the denial reason per the skill's Step 3 rules.",
            },
            "payer": {
                "type": "string",
                "description": "Payer name, normalized to title case and to the canonical spelling if it matches a known payer.",
            },
            "plan": {
                "type": "string",
                "description": "Plan name, normalized the same way as payer.",
            },
            "date_of_service": {
                "type": "string",
                "description": "ISO 8601 date (YYYY-MM-DD) the billed service was rendered.",
            },
            "denial_date": {
                "type": "string",
                "description": "ISO 8601 date (YYYY-MM-DD) this notice/determination was issued.",
            },
            "billed_amount": {
                "type": "number",
                "description": "Total billed charge for the denied service (not allowed/paid/patient-responsibility amounts).",
            },
        },
        "required": [
            "denial_reason_description",
            "denial_reason_category",
            "payer",
            "plan",
            "date_of_service",
            "denial_date",
            "billed_amount",
        ],
    },
}

REJECT_TOOL = {
    "name": "reject_document",
    "description": (
        "Call this instead of extract_denial_notice when the uploaded PDF is "
        "not a valid denial notice."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Short, specific explanation of why this document is not a valid denial notice.",
            }
        },
        "required": ["reason"],
    },
}


@lru_cache(maxsize=1)
def _load_skill() -> str:
    with open(SKILL_PATH, "r", encoding="utf-8") as f:
        return f.read()


def compute_date_of_service_bucket(date_of_service_iso: str, today: date = None) -> str:
    """Buckets a date-of-service into the dataset's exact bucket label format
    ("This Year (YYYY)" / "Prior Year (YYYY)"), computed relative to `today`
    (real system date by default). Kept in Python, not the model, since it's
    pure arithmetic with no ambiguity.

    Note: the historical dataset was generated as of Sept 2026 and only
    covers Jan 2025-present. If this tool is still running unmodified in a
    later calendar year without the dataset being refreshed, dates outside
    that window will correctly report as out-of-range rather than silently
    mismatching -- see the About page for this known prototype limitation.
    """
    today = today or date.today()
    dos = datetime.strptime(date_of_service_iso, "%Y-%m-%d").date()
    this_year = today.year
    prior_year = this_year - 1
    if dos.year == this_year:
        return f"This Year ({this_year})"
    if dos.year == prior_year:
        return f"Prior Year ({prior_year})"
    return f"Out of Range ({dos.year})"


def _client() -> anthropic.Anthropic:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Set it as an environment variable "
            "before running Agent 1 -- never hardcode it in project files."
        )
    return anthropic.Anthropic()


def run_agent1(pdf_bytes: bytes, model: str = None) -> dict:
    """Runs Agent 1 against one uploaded PDF's raw bytes.

    Returns either:
      {"valid": False, "reason": "..."}
    or:
      {"valid": True, "denial_reason_code": ..., "denial_reason_description": ...,
       "denial_reason_category": ..., "payer": ..., "plan": ...,
       "date_of_service": ..., "date_of_service_bucket": ...,
       "denial_date": ..., "billed_amount": ...}
    """
    client = _client()
    b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    message = client.messages.create(
        model=model or DEFAULT_MODEL,
        max_tokens=1024,
        system=_load_skill(),
        tools=[EXTRACT_TOOL, REJECT_TOOL],
        tool_choice={"type": "any"},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Known valid payer/plan combinations for this system "
                            "(normalize the notice's payer/plan to one of these "
                            "exact spellings if it clearly matches one):\n"
                            f"{known_payer_plans_prompt_text()}\n\n"
                            "Extract from the attached denial notice."
                        ),
                    },
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": b64,
                        },
                    },
                ],
            }
        ],
    )

    tool_calls = [b for b in message.content if b.type == "tool_use"]
    if not tool_calls:
        raise RuntimeError("Agent 1 did not call a tool -- unexpected response shape.")
    call = tool_calls[0]

    if call.name == "reject_document":
        return {"valid": False, "reason": call.input.get("reason", "Not a valid denial notice.")}

    if call.name == "extract_denial_notice":
        result = dict(call.input)
        result["valid"] = True
        result["date_of_service_bucket"] = compute_date_of_service_bucket(result["date_of_service"])
        return result

    raise RuntimeError(f"Unexpected tool call from Agent 1: {call.name}")


def to_agent2_input(extraction: dict) -> dict:
    """Trims a valid Agent 1 extraction down to exactly the fields Agent 2
    consumes (Table 1's schema): category, payer, plan, date-of-service
    bucket, denial date, billed amount. Raw code/description/date-of-service
    are extraction-time detail, kept upstream for QC/display but not part of
    the contract Agent 2 depends on.
    """
    return {
        "denial_reason_category": extraction["denial_reason_category"],
        "payer": extraction["payer"],
        "plan": extraction["plan"],
        "date_of_service_bucket": extraction["date_of_service_bucket"],
        "denial_date": extraction["denial_date"],
        "billed_amount": extraction["billed_amount"],
    }
