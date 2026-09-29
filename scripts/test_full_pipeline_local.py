"""
End-to-end local check: runs Agent 1 (live Claude call) -> Agent 2
(deterministic calc) -> the chat formatter, for all 5 sample PDFs, and prints
exactly what the chat UI would show. This validates the full loop -- not just
Agent 1's extraction fields -- before trusting the live browser flow.

Requires ANTHROPIC_API_KEY to be set in the environment.

Run with:
    python scripts/test_full_pipeline_local.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent1_extraction import run_agent1, to_agent2_input  # noqa: E402
from app.agent2_matching import run_agent2  # noqa: E402
from app.chat_formatter import build_chat_response  # noqa: E402

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample-data")

SAMPLES = [
    "sample_claim_1_pursue.pdf",
    "sample_claim_2_abandon.pdf",
    "sample_claim_3_pursue.pdf",
    "sample_claim_4_abandon.pdf",
    "sample_claim_5_deadline.pdf",
]


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set -- cannot run this check.")
        sys.exit(1)

    for filename in SAMPLES:
        path = os.path.join(SAMPLE_DIR, filename)
        print("=" * 88)
        print(filename)
        print("=" * 88)

        with open(path, "rb") as f:
            pdf_bytes = f.read()

        extraction = run_agent1(pdf_bytes)
        if not extraction.get("valid"):
            print(f"REJECTED: {extraction.get('reason')}")
            continue

        agent2_input = to_agent2_input(extraction)
        agent2_output = run_agent2(agent2_input)
        chat = build_chat_response(agent2_output, reference=filename)

        print(chat["plain_text"])
        print()

    print("=" * 88)
    print("sample_negative_control.pdf (should be REJECTED, not extracted)")
    print("=" * 88)
    path = os.path.join(SAMPLE_DIR, "sample_negative_control.pdf")
    with open(path, "rb") as f:
        pdf_bytes = f.read()
    extraction = run_agent1(pdf_bytes)
    if extraction.get("valid"):
        print("UNEXPECTED: this was extracted as if it were a valid denial notice:")
        print(extraction)
    else:
        print(f"Correctly rejected. Reason given: {extraction.get('reason')}")


if __name__ == "__main__":
    main()
