"""Independent re-read: a fresh model call checks each value against its evidence."""

from meta_client import chat_json

JUDGE_SYSTEM = ("You are an independent auditor of a government form. You only confirm values that are "
                "clearly visible in the evidence. If a digit or letter differs, the value is NOT supported.")


def judge_fields(record):
    problems = []
    form_labels = {f["id"]: f["label"] for f in record.form["fields"]}
    by_doc, spoken = {}, []
    for fid, entry in record.fields.items():
        src = entry.get("source") or {}
        if src.get("type") == "document":
            by_doc.setdefault(src.get("doc_id"), []).append((fid, entry["value"]))
        elif src.get("type") == "applicant":
            spoken.append((fid, entry["value"], src.get("utterance_id")))

    for doc_id, items in sorted(by_doc.items()):
        doc = record.doc(doc_id)
        if not doc or not doc.get("crop"):
            continue
        listing = "\n".join(f'- {fid} ({form_labels.get(fid, fid)}): "{v}"' for fid, v in items)
        prompt = ("Check each claimed value against this document image.\n" + listing +
                  '\nReturn ONLY JSON: {"results": [{"field_id": "...", "supported": true/false, "reason": "short"}]}')
        try:
            res = chat_json(prompt, image_path=doc["crop"], system=JUDGE_SYSTEM).get("results", [])
        except Exception as e:
            problems.append({"code": "JUDGE_ERROR", "field_id": None, "detail": f"could not judge {doc_id}: {e}"})
            continue
        seen = {r.get("field_id"): r for r in res}
        for fid, v in items:
            r = seen.get(fid)
            if r is None or not r.get("supported"):
                problems.append({"code": "UNSUPPORTED", "field_id": fid,
                                 "detail": f"{fid}='{v}' not visible on {doc.get('doc_type')} {doc_id}: {(r or {}).get('reason', 'no verdict')}"})

    if spoken:
        listing = []
        for fid, v, uid in spoken:
            u = record.utterance(uid) or {}
            listing.append(f'- {fid} ({form_labels.get(fid, fid)}) = "{v}"; applicant said: "{u.get("text", "")}"')
        prompt = ("The applicant answered by voice (possibly Hindi, Kannada, Marathi or mixed; numbers may be in words). "
                  "For each field, is the value a faithful reading of what they said?\n" + "\n".join(listing) +
                  '\nReturn ONLY JSON: {"results": [{"field_id": "...", "supported": true/false, "reason": "short"}]}')
        try:
            res = chat_json(prompt, system=JUDGE_SYSTEM).get("results", [])
            seen = {r.get("field_id"): r for r in res}
            for fid, v, _ in spoken:
                r = seen.get(fid)
                if r is None or not r.get("supported"):
                    problems.append({"code": "UNSUPPORTED", "field_id": fid,
                                     "detail": f"{fid}='{v}' is not what the applicant said: {(r or {}).get('reason', 'no verdict')}"})
        except Exception as e:
            problems.append({"code": "JUDGE_ERROR", "field_id": None, "detail": f"could not judge spoken answers: {e}"})
    return problems
