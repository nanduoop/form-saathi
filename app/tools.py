"""The agent's tools. Each takes the CaseRecord and returns an observation dict."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from boxes import box_pixels  # noqa: E402
from meta_client import chat_json, segment  # noqa: E402
from verification.checks import check_value, parse_money  # noqa: E402

LANGUAGES = {"hi": "Hindi", "kn": "Kannada", "mr": "Marathi", "te": "Telugu", "ta": "Tamil",
             "bn": "Bengali", "en": "English"}
DOC_TYPES = ["identity_card", "marksheet", "income_certificate", "caste_certificate", "bank_passbook",
             "land_record", "crop_field_photo", "other"]
SAM_PROMPTS = ["document", "paper", "card"]


def _fn(name, desc, props=None, required=None):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props or {}, "required": required or []}}}


S = {"type": "string"}
TOOLS = [
    _fn("find_documents", "Use SAM to locate every document in the photos not scanned yet; crops each one."),
    _fn("read_document", "Read one cropped document: its type, holder name and every printed field, verbatim.",
        {"doc_id": S}, ["doc_id"]),
    _fn("fill_fields", "Fill many form fields at once. Each entry gives EITHER doc_id + quote (exact text as printed "
        "on that document) OR utterance_id (what the applicant said).",
        {"entries": {"type": "array", "items": {"type": "object", "properties": {
            "field_id": S, "value": S, "doc_id": S, "quote": S, "utterance_id": S},
            "required": ["field_id", "value"]}}}, ["entries"]),
    _fn("clear_field", "Empty a field you filled wrongly.", {"field_id": S, "reason": S}, ["field_id", "reason"]),
    _fn("check_eligibility", "Check the scheme's eligibility rules against the filled category, income and percentage."),
    _fn("ask_applicant", "Stop and ask the applicant a question by voice, in their language. Ask for several fields at once.",
        {"question_en": S, "field_ids": {"type": "array", "items": S}}, ["question_en", "field_ids"]),
    _fn("flag_discrepancy", "Record a real-world inconsistency the applicant must know about (e.g. a different name "
        "spelling on a certificate). target is a field_id or 'doc:<doc_id>'.",
        {"target": S, "detail": S}, ["target", "detail"]),
    _fn("declare_ineligible", "End the case because the applicant is not eligible; explains why in their language.",
        {"reason": S}, ["reason"]),
    _fn("submit_form", "Submit the form to the verification gate. It refuses anything unproven."),
]


def _iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    area = lambda r: (r[2] - r[0]) * (r[3] - r[1])
    return inter / float(area(a) + area(b) - inter or 1)


def find_documents(record, crop_dir):
    os.makedirs(crop_dir, exist_ok=True)
    found = []
    for idx, photo in enumerate(record.photos):
        if idx in record.scanned_photos:
            continue
        img = Image.open(photo).convert("RGB")
        rects = []
        for prompt in SAM_PROMPTS:
            try:
                boxes = segment(photo, prompt)
            except Exception as e:
                return {"error": f"SAM failed on photo {idx}: {e}"}
            for b in boxes:
                r = box_pixels(b, img.width, img.height, pad=0.03)
                if (r[2] - r[0]) * (r[3] - r[1]) < 0.03 * img.width * img.height:
                    continue
                if all(_iou(r, o) < 0.6 for o, _ in rects):
                    rects.append((r, b))
            if rects:
                break
        if not rects:
            rects = [((0, 0, img.width, img.height), None)]
        for r, b in rects:
            n = len(record.documents) + 1
            crop_path = os.path.join(crop_dir, f"d{n}.jpg")
            img.crop(r).save(crop_path, quality=92)
            did = record.add_document(photo, list(r), crop_path)
            doc = record.doc(did)
            doc["photo_index"] = idx
            doc["sam_found"] = b is not None
            if b is not None:
                raw = box_pixels(b, img.width, img.height, pad=0)
                m = 0.006
                doc["cut_edges"] = [e for e, hit in (("left", raw[0] <= img.width * m), ("top", raw[1] <= img.height * m),
                                                     ("right", raw[2] >= img.width * (1 - m)),
                                                     ("bottom", raw[3] >= img.height * (1 - m))) if hit]
                doc["area_ratio"] = round((raw[2] - raw[0]) * (raw[3] - raw[1]) / float(img.width * img.height), 3)
            found.append({"doc_id": did, "photo": idx, "box": list(r), "sam_box": b is not None})
        record.scanned_photos.append(idx)
    if not found:
        return {"note": "no new photos to scan", "documents": [d["id"] for d in record.documents]}
    return {"documents_found": len(found), "documents": found}


def read_document(record, doc_id):
    doc = record.doc(doc_id)
    if not doc:
        return {"error": f"unknown doc_id {doc_id}"}
    prompt = ("You are reading an Indian document photo for a government form. Copy text EXACTLY as printed; "
              "never guess a digit. Return ONLY JSON: "
              '{"doc_type": one of ' + str(DOC_TYPES) + ', "holder_name": "name of the person the document belongs to", '
              '"fields": [{"key": "printed label", "value": "value", "quote": "the exact printed line containing it"}], '
              '"unreadable": ["labels you could not read clearly"], '
              '"quality": {"usable": true/false, "issues": ["blur"|"glare"|"too_dark"|"tilted"|"cut_off"|"too_far"|"not_a_document"], '
              '"advice": "one short instruction to retake the photo, or empty"}}')
    try:
        j = chat_json(prompt, image_path=doc["crop"])
    except Exception as e:
        return {"error": f"could not read {doc_id}: {e}"}
    doc["doc_type"] = j.get("doc_type") if j.get("doc_type") in DOC_TYPES else "other"
    doc["holder_name"] = j.get("holder_name")
    doc["fields"] = [f for f in j.get("fields", []) if isinstance(f, dict)]
    doc["quality"] = j.get("quality") if isinstance(j.get("quality"), dict) else {"usable": True, "issues": []}
    doc["unreadable"] = j.get("unreadable", [])
    return {"doc_id": doc_id, "doc_type": doc["doc_type"], "holder_name": doc["holder_name"],
            "fields": doc["fields"], "unreadable": doc["unreadable"], "quality": doc["quality"]}


def fill_field(record, field_id, value, doc_id=None, quote=None, utterance_id=None):
    spec = next((f for f in record.form["fields"] if f["id"] == field_id), None)
    if not spec:
        return {"error": f"unknown field_id {field_id}. Valid: {[f['id'] for f in record.form['fields']]}"}
    if doc_id:
        doc = record.doc(doc_id)
        if not doc:
            return {"error": f"unknown doc_id {doc_id}"}
        if not quote:
            return {"error": "quote is required with doc_id: copy the exact printed text"}
        source = {"type": "document", "doc_id": doc_id, "quote": quote}
    elif utterance_id:
        if not record.utterance(utterance_id):
            return {"error": f"unknown utterance_id {utterance_id}"}
        if not spec.get("voice_ok"):
            return {"error": f"{field_id} must come from a document ({spec['doc_types']}), not speech"}
        source = {"type": "applicant", "utterance_id": utterance_id}
    else:
        return {"error": "give doc_id + quote, or utterance_id"}
    record.fields[field_id] = {"value": str(value).strip(), "source": source}
    out = {"field_id": field_id, "value": value, "source": source}
    if spec.get("check"):
        err = check_value(spec["check"], value)
        if err:
            out["warning"] = err
    return out


def fill_fields(record, entries):
    results = []
    for e in entries or []:
        if not isinstance(e, dict):
            results.append({"error": f"bad entry {e!r}"})
            continue
        results.append(fill_field(record, e.get("field_id"), e.get("value"), e.get("doc_id"),
                                  e.get("quote"), e.get("utterance_id")))
    empty = [f["id"] for f in record.form["fields"] if f["id"] not in record.fields]
    return {"results": results, "still_empty": empty}


def clear_field(record, field_id, reason):
    if record.fields.pop(field_id, None) is None:
        return {"error": f"{field_id} was not filled"}
    return {"cleared": field_id, "reason": reason}


def check_eligibility(record):
    rules = record.form["eligibility"]
    f = record.fields
    need = [k for k in ("category", "annual_family_income", "previous_percentage") if k not in f]
    if need:
        return {"error": f"fill these first: {need}"}
    cat = str(f["category"]["value"]).upper()
    inc = parse_money(f["annual_family_income"]["value"])
    try:
        pct = float(str(f["previous_percentage"]["value"]).rstrip("%"))
    except ValueError:
        pct = None
    reasons = []
    if cat not in rules["categories"]:
        reasons.append(f"category {cat} is not one of {rules['categories']}")
    if inc is None or inc > rules["max_annual_income"]:
        reasons.append(f"family income {inc} is above the limit of {rules['max_annual_income']}")
    if pct is None or pct < rules["min_previous_percentage"]:
        reasons.append(f"percentage {pct} is below {rules['min_previous_percentage']}")
    record.eligibility = {"eligible": not reasons, "reasons": reasons,
                          "checked_values": {"category": cat, "annual_family_income": inc, "previous_percentage": pct}}
    return record.eligibility


def _translate(record, text_en):
    lang = LANGUAGES.get(record.language, "Hindi")
    if record.language == "en":
        return text_en
    try:
        j = chat_json(f"Translate for a village applicant into simple spoken {lang}, in {lang} script. "
                      f'Keep it short and polite. Return ONLY JSON: {{"text": "..."}}\n\n{text_en}')
        return j.get("text") or text_en
    except Exception:
        return text_en


def ask_applicant(record, question_en, field_ids):
    if record.open_question():
        return {"error": "a question is already waiting for an answer"}
    local = _translate(record, question_en)
    qid = record.add_question(field_ids, question_en, local)
    record.status = "needs_input"
    return {"status": "needs_input", "question_id": qid, "question_local": local}


def flag_discrepancy(record, target, detail):
    fields = {f["id"] for f in record.form["fields"]}
    if target not in fields and not (target.startswith("doc:") and record.doc(target[4:])):
        return {"error": f"target must be a field_id or doc:<doc_id>, got {target}"}
    did = record.add_discrepancy(target, detail)
    return {"discrepancy_id": did, "target": target}


def declare_ineligible(record, reason):
    if not record.eligibility or record.eligibility.get("eligible"):
        return {"error": "run check_eligibility first; it must say not eligible"}
    record.status = "ineligible"
    record.ineligible_reason = {"en": reason, "local": _translate(record, reason)}
    return {"status": "ineligible", **record.ineligible_reason}


def submit_form(record):
    from verification.gate import run_gate
    status, payload = run_gate(record)
    return {"status": status, **payload}


DISPATCH = {
    "find_documents": find_documents, "read_document": read_document, "fill_fields": fill_fields,
    "clear_field": clear_field, "check_eligibility": check_eligibility, "ask_applicant": ask_applicant,
    "flag_discrepancy": flag_discrepancy, "declare_ineligible": declare_ineligible, "submit_form": submit_form,
}
