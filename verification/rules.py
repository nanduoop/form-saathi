"""Hard rules. Every field must be proven, valid, and consistent before submission."""

from verification.checks import check_value, name_similarity, parse_money, value_in_quote

NAME_MATCH = 0.9


def check_rules(record):
    form = record.form
    problems = []
    fields = record.fields
    acknowledged = {d["field_id"] for d in record.discrepancies}

    def add(code, field_id, detail):
        problems.append({"code": code, "field_id": field_id, "detail": detail})

    if record.eligibility is None:
        add("ELIGIBILITY_NOT_CHECKED", None, "call check_eligibility before submitting")
    elif not record.eligibility.get("eligible"):
        add("NOT_ELIGIBLE", None, "applicant is not eligible: " + "; ".join(record.eligibility.get("reasons", [])))

    for spec in form["fields"]:
        fid = spec["id"]
        entry = fields.get(fid)
        if not entry or not str(entry.get("value", "")).strip():
            add("MISSING_FIELD", fid, f"'{spec['label']}' is empty")
            continue
        value, src = entry["value"], entry.get("source") or {}
        if src.get("type") == "document":
            doc = record.doc(src.get("doc_id"))
            if doc is None:
                add("BAD_SOURCE", fid, f"cites unknown document {src.get('doc_id')}")
                continue
            if spec["doc_types"] and doc.get("doc_type") not in spec["doc_types"]:
                add("WRONG_DOC_TYPE", fid, f"'{spec['label']}' must come from {spec['doc_types']}, not {doc.get('doc_type')}")
            if not value_in_quote(value, src.get("quote")):
                add("QUOTE_MISMATCH", fid, f"value '{value}' is not in the quoted text '{src.get('quote')}'")
            extracted = " | ".join(f"{f.get('key')}: {f.get('quote') or f.get('value')}" for f in doc.get("fields", []))
            if src.get("quote") and not value_in_quote(src["quote"], extracted) and not value_in_quote(value, extracted):
                add("QUOTE_NOT_ON_DOC", fid, f"quote '{src.get('quote')}' was never read from document {doc['id']}")
        elif src.get("type") == "applicant":
            if not spec.get("voice_ok"):
                add("NEEDS_DOCUMENT", fid, f"'{spec['label']}' must be proven by a document, not by what the applicant said")
            if record.utterance(src.get("utterance_id")) is None:
                add("BAD_SOURCE", fid, f"cites unknown utterance {src.get('utterance_id')}")
        else:
            add("NO_SOURCE", fid, f"'{spec['label']}' has no evidence")
        if spec.get("check"):
            err = check_value(spec["check"], value)
            if err:
                add("INVALID_" + spec["check"].upper(), fid, f"'{spec['label']}' = '{value}': {err}")

    # Percentage must match marks.
    try:
        got = float(fields["previous_marks_obtained"]["value"])
        mx = float(fields["previous_marks_max"]["value"])
        pct = float(str(fields["previous_percentage"]["value"]).rstrip("%"))
        if mx > 0 and abs(got / mx * 100 - pct) > 0.5:
            add("PERCENT_MISMATCH", "previous_percentage", f"{got}/{mx} is {got / mx * 100:.2f}%, not {pct}%")
    except (KeyError, ValueError, TypeError):
        pass

    # The same person on every document.
    name = (fields.get("applicant_name") or {}).get("value")
    if name:
        for fid in form.get("name_fields", []):
            other = (fields.get(fid) or {}).get("value")
            if fid != "applicant_name" and other and name_similarity(name, other) < NAME_MATCH and fid not in acknowledged:
                add("NAME_MISMATCH", fid, f"'{other}' does not match applicant name '{name}'")
        for doc in record.documents:
            holder = doc.get("holder_name")
            key = f"doc:{doc['id']}"
            if holder and name_similarity(name, holder) < NAME_MATCH and key not in acknowledged:
                add("NAME_MISMATCH", key, f"{doc.get('doc_type')} {doc['id']} is in the name '{holder}', applicant is '{name}'")

    # Eligibility must have used the values now on the form.
    if record.eligibility and record.eligibility.get("eligible"):
        used = record.eligibility.get("checked_values", {})
        inc = parse_money((fields.get("annual_family_income") or {}).get("value"))
        if used.get("annual_family_income") is not None and inc is not None and used["annual_family_income"] != inc:
            add("STALE_ELIGIBILITY", "annual_family_income", "income changed after eligibility was checked; check again")
        cat = str((fields.get("category") or {}).get("value", "")).upper()
        if used.get("category") and cat and used["category"] != cat:
            add("STALE_ELIGIBILITY", "category", "category changed after eligibility was checked; check again")

    return problems
