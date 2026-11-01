"""Submission gate: rules first, then the independent judge. Three refusals escalate to a human."""

from verification.judge import judge_fields
from verification.rules import check_rules

MAX_REFUSALS = 3


def run_gate(record):
    problems = check_rules(record)
    stage = "rules"
    if not problems:
        problems = judge_fields(record)
        stage = "judge"
    if problems:
        record.refusals += 1
        if record.refusals >= MAX_REFUSALS:
            record.status = "escalated"
            return "escalated", {"stage": stage, "refusals": record.refusals, "problems": problems,
                                 "message": "escalated to a human helper after 3 refusals"}
        return "refused", {"stage": stage, "refusals": record.refusals, "problems": problems}
    record.status = "awaiting_signoff"
    return "awaiting_signoff", {"message": "every field is proven; waiting for the applicant to confirm",
                                "discrepancies": record.discrepancies}
