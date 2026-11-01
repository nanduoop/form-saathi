"""Backwards-compatible entry point for the verification gate."""
from typing import Any, Dict

from verification.judge import judge_fields
from verification.rules import check_rules


def verify_case(record):
    # type: (Any) -> Dict[str, Any]
    """Detect verification problems without changing the record.

    Returns {"ok", "problems", "refusals"} where refusals renders each
    problem as one human-readable string.
    """
    problems = check_rules(record)
    if not problems:
        problems = judge_fields(record)
    refusals = ["%s %s: %s" % (p.get("code"), p.get("field_id"),
                               p.get("detail")) for p in problems]
    return {"ok": not problems, "problems": problems, "refusals": refusals}
