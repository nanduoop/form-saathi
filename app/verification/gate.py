"""Verification gate: rules first, the Spark judge only when clean."""
from typing import Any, Dict, List

from verification.judge import judge_fields
from verification.rules import check_rules

MAX_REFUSALS = 3


def run_gate(record):
    # type: (Any) -> Dict[str, Any]
    """Verify a case. Clean cases await signoff; problems add a refusal.

    Returns {"ok", "problems", "status"} where status is
    "awaiting_signoff", "refused" or "escalated".
    """
    problems = check_rules(record)  # type: List[Dict[str, Any]]
    if not problems:
        try:
            problems = judge_fields(record)
        except Exception as e:
            problems = [{"code": "JUDGE_ERROR", "field_id": None,
                         "detail": "judge failed: %s: %s"
                         % (type(e).__name__, e)}]
    if not problems:
        record.status = "awaiting_signoff"
        record.add_log("run_gate: passed, awaiting signoff")
        return {"ok": True, "problems": [], "status": "awaiting_signoff"}
    rid = "r%d" % (len(record.refusals) + 1)
    record.refusals.append({
        "id": rid,
        "detail": "; ".join("%s %s: %s"
                            % (p.get("code"), p.get("field_id"),
                               p.get("detail"))
                            for p in problems),
        "problems": [dict(p) for p in problems],
    })
    record.add_log("run_gate: refused (%s)" % rid)
    if len(record.refusals) >= MAX_REFUSALS:
        record.status = "escalated"
        record.add_log("run_gate: escalated for human helper")
        return {"ok": False, "problems": problems, "status": "escalated"}
    return {"ok": False, "problems": problems, "status": "refused"}
