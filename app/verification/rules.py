"""Deterministic verification rules. Pure apart from reading the form spec."""
import re
from typing import Any, Dict, List, Optional

import tools
from verification.checks import (
    CHECKS,
    name_similarity,
    parse_income,
    value_in_quote,
)

NAME_THRESHOLD = 0.9
PERCENT_TOLERANCE = 0.5


def _problem(code, field_id, detail):
    # type: (str, Optional[str], str) -> Dict[str, Any]
    return {"code": code, "field_id": field_id, "detail": detail}


def _blank(value):
    # type: (Any) -> bool
    return value is None or (isinstance(value, str) and not value.strip())


def _norm_quote(quote):
    # type: (Any) -> str
    s = "" if quote is None else str(quote).lower()
    return re.sub(r"\s+", " ", s).strip()


def _quote_on_doc(quote, doc):
    # type: (Any, Dict[str, Any]) -> bool
    nq = _norm_quote(quote)
    if not nq:
        return False
    for f in doc.get("fields") or []:
        if not isinstance(f, dict):
            continue
        dq = _norm_quote((f.get("quote") or ""))
        if not dq:
            continue
        if nq == dq or nq in dq or dq in nq:
            return True
    return False


def _float(value):
    # type: (Any) -> Optional[float]
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace("%", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def check_rules(record):
    # type: (Any) -> List[Dict[str, Any]]
    """Run every deterministic rule; return problems (empty when clean)."""
    form = tools.load_form(record.form_id)
    problems = []  # type: List[Dict[str, Any]]

    elig = record.eligibility
    if elig is None:
        problems.append(_problem("ELIGIBILITY_NOT_CHECKED", None,
                                "check_eligibility has not been run"))
    elif elig.get("eligible") is False:
        problems.append(_problem("NOT_ELIGIBLE", None,
                                "eligibility check failed: %s"
                                % ("; ".join(elig.get("reasons") or [])
                                   or "not eligible")))

    suppressed = set()  # type: set
    for d in record.discrepancies or []:
        if isinstance(d, dict) and d.get("field_id"):
            suppressed.add(d["field_id"])

    for spec in form.get("fields", []):
        fid = spec["id"]
        entry = (record.fields or {}).get(fid)
        if entry is None or _blank(entry.get("value")):
            problems.append(_problem("MISSING_FIELD", fid,
                                     "field %s is not filled" % fid))
            continue
        value = entry.get("value")
        source = entry.get("source") or {}
        stype = source.get("type")
        if not isinstance(source, dict) or stype not in ("document",
                                                         "applicant"):
            problems.append(_problem("NO_SOURCE", fid,
                                     "field %s has no usable source"
                                     % fid))
            continue
        if stype == "applicant":
            if not any(u.get("id") == source.get("utterance_id")
                       for u in record.utterances or []):
                problems.append(_problem(
                    "BAD_SOURCE", fid,
                    "field %s cites unknown utterance %r"
                    % (fid, source.get("utterance_id"))))
                continue
            if not spec.get("voice_ok"):
                problems.append(_problem(
                    "NEEDS_DOCUMENT", fid,
                    "field %s cannot come from speech "
                    "(voice_ok is false)" % fid))
        else:
            doc = record.doc(source.get("doc_id"))
            if doc is None or doc.get("rejected"):
                problems.append(_problem(
                    "BAD_SOURCE", fid,
                    "field %s cites unknown or rejected document %r"
                    % (fid, source.get("doc_id"))))
                continue
            allowed = spec.get("doc_types") or []
            if allowed and doc.get("doc_type") not in allowed:
                problems.append(_problem(
                    "WRONG_DOC_TYPE", fid,
                    "field %s needs one of %s but %s is %r"
                    % (fid, "/".join(allowed),
                       source.get("doc_id"), doc.get("doc_type"))))
            quote = source.get("quote")
            if not quote or not value_in_quote(value, quote):
                problems.append(_problem(
                    "QUOTE_MISMATCH", fid,
                    "value %r of field %s is not in its quote %r"
                    % (value, fid, quote)))
            elif not _quote_on_doc(quote, doc):
                problems.append(_problem(
                    "QUOTE_NOT_ON_DOC", fid,
                    "quote for field %s was never read from document %s"
                    % (fid, source.get("doc_id"))))
        check = spec.get("check")
        if check and check in CHECKS:
            try:
                ok = bool(CHECKS[check](value))
            except Exception:
                ok = False
            if not ok:
                problems.append(_problem(
                    "INVALID_" + str(check).upper(), fid,
                    "field %s value %r fails the %s check"
                    % (fid, value, check)))

    obt = _float((record.fields.get("previous_marks_obtained")
                  or {}).get("value"))
    mx = _float((record.fields.get("previous_marks_max") or {}).get("value"))
    pct = _float((record.fields.get("previous_percentage")
                  or {}).get("value"))
    if (obt is not None and mx is not None and pct is not None and mx > 0
            and abs(obt / mx * 100.0 - pct) > PERCENT_TOLERANCE):
        problems.append(_problem(
            "PERCENT_MISMATCH", "previous_percentage",
            "percentage %s does not match %s/%s*100 (tolerance %s)"
            % (pct, obt, mx, PERCENT_TOLERANCE)))

    name_ids = list(form.get("name_fields") or [])
    targets = []  # type: List[Any]
    for fid in name_ids:
        entry = (record.fields or {}).get(fid) or {}
        if not _blank(entry.get("value")):
            targets.append((fid, entry.get("value")))
    holders = []  # type: List[Any]
    for doc in record.documents or []:
        if doc.get("rejected"):
            continue
        if not _blank(doc.get("holder_name")):
            holders.append(("doc:" + str(doc.get("id")),
                            doc.get("holder_name")))
    ref = None  # type: Any
    app_entry = (record.fields or {}).get("applicant_name") or {}
    if not _blank(app_entry.get("value")):
        ref = app_entry.get("value")
    elif targets:
        ref = targets[0][1]
    for target, name in targets + holders:
        if target in suppressed or ref is None:
            continue
        if target == "applicant_name":
            continue
        if name_similarity(name, ref) < NAME_THRESHOLD:
            problems.append(_problem(
                "NAME_MISMATCH", target,
                "%r does not match applicant name %r" % (name, ref)))

    if isinstance(elig, dict) and isinstance(elig.get("checked_values"),
                                              dict):
        checked = elig["checked_values"]
        cat_entry = (record.fields or {}).get("category") or {}
        if not _blank(cat_entry.get("value")):
            now_cat = str(cat_entry["value"]).strip().upper()
            old_cat = checked.get("category")
            old_cat_n = (str(old_cat).strip().upper()
                         if old_cat is not None else None)
            if old_cat_n is not None and now_cat != old_cat_n:
                problems.append(_problem(
                    "STALE_ELIGIBILITY", "category",
                    "category changed from %r to %r after the "
                    "eligibility check" % (old_cat, cat_entry["value"])))
        inc_entry = (record.fields or {}).get("annual_family_income") or {}
        if not _blank(inc_entry.get("value")):
            now_inc = parse_income(inc_entry.get("value"))
            old_inc = checked.get("annual_family_income")
            if (now_inc is not None and old_inc is not None
                    and now_inc != old_inc):
                problems.append(_problem(
                    "STALE_ELIGIBILITY", "annual_family_income",
                    "income changed from %r to %r after the "
                    "eligibility check"
                    % (old_inc, inc_entry.get("value"))))

    return problems
