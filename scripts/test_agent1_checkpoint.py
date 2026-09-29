"""
Internal test checkpoint for Agent 1 (per the build instructions): runs the
live extraction against the 5 sample denial notice PDFs and prints each
structured result next to the known-correct ground truth, so a human can
confirm every field before Agent 1 is wired into the chat UI.

Requires ANTHROPIC_API_KEY to be set in the environment.

Run with:
    python scripts/test_agent1_checkpoint.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent1_extraction import run_agent1  # noqa: E402

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample-data")

# Ground truth -- what Agent 1 SHOULD extract from each PDF (see
# scripts/generate_sample_claims.py for how these were built and
# tests/test_agent2.py for the Agent-2-facing shape of the same claims).
GROUND_TRUTH = {
    "sample_claim_1_pursue.pdf": {
        "denial_reason_code": "CO-140",
        "denial_reason_category": "Technical",
        "payer": "Northlake Medicare Solutions",
        "plan": "Complete Care",
        "date_of_service": "2026-07-14",
        "denial_date": "2026-08-02",
        "billed_amount": 315.00,
        "date_of_service_bucket": "This Year (2026)",
    },
    "sample_claim_2_abandon.pdf": {
        "denial_reason_code": "CO-50",
        "denial_reason_category": "Clinical",
        "payer": "Cascade Health Partners",
        "plan": "Advantage Choice",
        "date_of_service": "2025-10-03",
        "denial_date": "2025-11-05",
        "billed_amount": 340.00,
        "date_of_service_bucket": "Prior Year (2025)",
    },
    "sample_claim_3_pursue.pdf": {
        "denial_reason_code": "CO-16 / N657",
        "denial_reason_category": "Clinical",
        "payer": "Summit Point Health",
        "plan": "Value Plan",
        "date_of_service": "2026-05-22",
        "denial_date": "2026-06-10",
        "billed_amount": 500.00,
        "date_of_service_bucket": "This Year (2026)",
    },
    "sample_claim_4_abandon.pdf": {
        "denial_reason_code": "CO-18",
        "denial_reason_category": "Technical",
        "payer": "Cascade Health Partners",
        "plan": "Advantage Plus",
        "date_of_service": "2025-04-11",
        "denial_date": "2025-05-01",
        "billed_amount": 115.00,
        "date_of_service_bucket": "Prior Year (2025)",
    },
    "sample_claim_5_deadline.pdf": {
        "denial_reason_code": "CO-197",
        "denial_reason_category": "Technical",
        "payer": "Summit Point Health",
        "plan": "Standard Plan",
        "date_of_service": "2026-09-02",
        "denial_date": "2026-09-14",
        "billed_amount": 445.00,
        "date_of_service_bucket": "This Year (2026)",
    },
}

CHECK_FIELDS = [
    "denial_reason_category",
    "payer",
    "plan",
    "date_of_service",
    "date_of_service_bucket",
    "denial_date",
    "billed_amount",
]


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set -- cannot run the live checkpoint.")
        print("Set it as an environment variable, then re-run this script.")
        sys.exit(1)

    all_pass = True
    for filename, expected in GROUND_TRUTH.items():
        path = os.path.join(SAMPLE_DIR, filename)
        print("=" * 88)
        print(filename)
        print("-" * 88)
        with open(path, "rb") as f:
            pdf_bytes = f.read()

        result = run_agent1(pdf_bytes)

        if not result.get("valid"):
            print(f"  REJECTED (expected a valid extraction): {result.get('reason')}")
            all_pass = False
            continue

        print("  field                      expected                              actual                                ok")
        row_ok = True
        for field in CHECK_FIELDS:
            exp_val = expected[field]
            act_val = result.get(field)
            ok = exp_val == act_val
            row_ok = row_ok and ok
            print(f"  {field:<26} {str(exp_val):<37} {str(act_val):<37} {'OK' if ok else 'MISMATCH'}")

        print(f"  denial_reason_code (informational, not blocking): expected={expected['denial_reason_code']!r} actual={result.get('denial_reason_code')!r}")
        print(f"  denial_reason_description (for manual read): {result.get('denial_reason_description')!r}")
        print(f"  -> {'PASS' if row_ok else 'FAIL'}")
        all_pass = all_pass and row_ok

    print("=" * 88)
    print("CHECKPOINT RESULT:", "ALL PASS -- safe to proceed to the chat UI" if all_pass else "FAILURES FOUND -- fix Agent 1 before proceeding")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
