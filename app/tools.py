"""Agent tools: find/read documents, fill fields, ask, gate, submit.

Each tool takes the CaseRecord first and returns a plain JSON-serialisable
dict. TOOLS holds the OpenAI tool schemas; DISPATCH maps tool names to the
functions so the agent loop (and offline tests) can call them by name.
"""
import json
import os
import re
from typing import Any, Dict, List, Optional

import meta_client
from case_record import CaseRecord, state_dir

HERE = os.path.dirname(os.path.abspath(__file__))

SAM_PROMPTS = ("document", "paper", "card")

MIN_AREA_RATIO = 0.03
DEDUPE_IOU = 0.6
EDGE_TOLERANCE = 0.006
CROP_PADDING = 0.03

DOC_TYPES = ("identity_card", "marksheet", "income_certificate",
             "caste_certificate", "bank_passbook", "land_record",
             "crop_field_photo", "other")

LANG_NAMES = {
    "hi": "Hindi",
    "kn": "Kannada",
    "mr": "Marathi",
    "te": "Telugu",
    "ta": "Tamil",
    "bn": "Bengali",
    "en": "English",
}

_forms = {}  # type: Dict[str, Dict[str, Any]]


def load_form(form_id="post_matric_scholarship"):
    # type: (str) -> Dict[str, Any]
    """Load (and cache) a form spec from app/forms/<form_id>.json."""
    if form_id not in _forms:
        path = os.path.join(HERE, "forms", form_id + ".json")
        with open(path, "r", encoding="utf-8") as f:
            _forms[form_id] = json.load(f)
    return _forms[form_id]


def field_spec(form, field_id):
    # type: (Dict[str, Any], str) -> Optional[Dict[str, Any]]
    for f in form.get("fields", []):
        if f.get("id") == field_id:
            return f
    return None


# ------------------------------------------------------- format checks ---

def parse_income(value):
    # type: (Any) -> Optional[int]
    """Parse 'Rs. 1,20,000' style amounts to an int; None if unparseable."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^\d]", "", str(value))
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _warn(check, value):
    # type: (str, Any) -> Optional[str]
    """Run one named format check; return a warning string or None."""
    s = "" if value is None else str(value).strip()
    if check == "date":
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
            try:
                import datetime
                datetime.datetime.strptime(s, fmt)
                return None
            except ValueError:
                continue
        return "expected a date like DD/MM/YYYY, got %r" % (value,)
    if check == "gender":
        if s.lower() in ("male", "female", "other", "m", "f"):
            return None
        return "expected Male/Female/Other, got %r" % (value,)
    if check == "aadhaar":
        if re.fullmatch(r"\d{12}", re.sub(r"\D", "", s)):
            return None
        return "expected a 12-digit Aadhaar number, got %r" % (value,)
    if check == "pin":
        if re.fullmatch(r"\d{6}", s):
            return None
        return "expected a 6-digit PIN code, got %r" % (value,)
    if check == "mobile":
        if re.fullmatch(r"[6-9]\d{9}", re.sub(r"\D", "", s)):
            return None
        return "expected a 10-digit mobile number, got %r" % (value,)
    if check == "category":
        if s.upper() in ("SC", "ST", "OBC"):
            return None
        return "expected one of SC/ST/OBC, got %r" % (value,)
    if check == "income":
        if parse_income(value) is not None:
            return None
        return "expected an amount like 'Rs. 1,20,000', got %r" % (value,)
    if check == "int":
        try:
            int(str(value).replace(",", "").strip())
            return None
        except (ValueError, TypeError):
            return "expected a whole number, got %r" % (value,)
    if check == "percentage":
        try:
            p = float(str(value).replace("%", "").strip())
        except (ValueError, TypeError):
            return "expected a percentage 0-100, got %r" % (value,)
        if 0.0 <= p <= 100.0:
            return None
        return "expected a percentage 0-100, got %r" % (value,)
    if check == "account":
        if re.fullmatch(r"\d{9,18}", re.sub(r"\s", "", s)):
            return None
        return "expected a 9-18 digit account number, got %r" % (value,)
    if check == "ifsc":
        if re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}",
                        re.sub(r"\s", "", s).upper()):
            return None
        return "expected an IFSC like 'SMPL0001234', got %r" % (value,)
    return None


# ------------------------------------------------------------- geometry ---

def _iou(a, b):
    # type: (Dict[str, int], Dict[str, int]) -> float
    ix1 = max(a["x1"], b["x1"])
    iy1 = max(a["y1"], b["y1"])
    ix2 = min(a["x2"], b["x2"])
    iy2 = min(a["y2"], b["y2"])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    aa = (a["x2"] - a["x1"]) * (a["y2"] - a["y1"])
    ab = (b["x2"] - b["x1"]) * (b["y2"] - b["y1"])
    union = aa + ab - inter
    if union <= 0:
        return 0.0
    return inter / union


def _area_ratio(box):
    # type: (Dict[str, int]) -> float
    frame = box["w"] * box["h"]
    if frame <= 0:
        return 0.0
    return ((box["x2"] - box["x1"]) * (box["y2"] - box["y1"])) / frame


def _touches_edge(box):
    # type: (Dict[str, int]) -> bool
    w, h = box["w"], box["h"]
    return (box["x1"] <= EDGE_TOLERANCE * w or
            box["y1"] <= EDGE_TOLERANCE * h or
            box["x2"] >= w - EDGE_TOLERANCE * w or
            box["y2"] >= h - EDGE_TOLERANCE * h)


def _deduped(boxes):
    # type: (List[Dict[str, int]]) -> List[Dict[str, int]]
    """Drop boxes under 3% of the frame; dedupe pairs with IoU > 0.6."""
    big = [b for b in boxes if _area_ratio(b) >= MIN_AREA_RATIO]
    big.sort(key=lambda b: ((b["x2"] - b["x1"]) * (b["y2"] - b["y1"])),
             reverse=True)
    kept = []  # type: List[Dict[str, int]]
    for b in big:
        if all(_iou(b, k) <= DEDUPE_IOU for k in kept):
            kept.append(b)
    return kept


def _crop_box(photo_path, box, crop_path):
    # type: (str, Dict[str, int], str) -> None
    from PIL import Image
    img = Image.open(photo_path).convert("RGB")
    fw, fh = img.size
    bw = box["x2"] - box["x1"]
    bh = box["y2"] - box["y1"]
    # Boxes are source pixels; rescale if the file differs from w,h.
    sx = fw / box["w"] if box["w"] else 1.0
    sy = fh / box["h"] if box["h"] else 1.0
    x1 = int((box["x1"] - CROP_PADDING * bw) * sx)
    y1 = int((box["y1"] - CROP_PADDING * bh) * sy)
    x2 = int((box["x2"] + CROP_PADDING * bw) * sx)
    y2 = int((box["y2"] + CROP_PADDING * bh) * sy)
    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(fw, x2)
    y2 = min(fh, y2)
    folder = os.path.dirname(crop_path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    img.crop((x1, y1, x2, y2)).save(crop_path, "JPEG", quality=92)


# ---------------------------------------------------------------- tools ---

def find_documents(record):
    # type: (CaseRecord) -> Dict[str, Any]
    """Scan each unscanned photo with SAM; crop every document box."""
    new_docs = []  # type: List[str]
    for index, photo in enumerate(list(record.photos)):
        if photo in record.scanned_photos:
            continue
        boxes = []  # type: List[Dict[str, int]]
        for prompt in SAM_PROMPTS:
            try:
                boxes = meta_client.segment(photo, prompt)
            except Exception:
                boxes = []
            if boxes:
                break
        boxes = _deduped(boxes)
        if not boxes:
            doc_id = "d%d" % (len(record.documents) + 1)
            record.documents.append({
                "id": doc_id, "photo": photo, "photo_index": index,
                "box": None, "crop": photo, "doc_type": None,
                "holder_name": None, "fields": [], "quality": None,
                "unreadable": [], "sam_found": False, "cut_edges": False,
                "area_ratio": 1.0, "rejected": False,
            })
            new_docs.append(doc_id)
        else:
            for box in boxes:
                doc_id = "d%d" % (len(record.documents) + 1)
                crop = os.path.join(state_dir(record.case_id), "crops",
                                    doc_id + ".jpg")
                _crop_box(photo, box, crop)
                record.documents.append({
                    "id": doc_id, "photo": photo, "photo_index": index,
                    "box": {"x1": box["x1"], "y1": box["y1"],
                            "x2": box["x2"], "y2": box["y2"],
                            "w": box["w"], "h": box["h"]},
                    "crop": crop, "doc_type": None, "holder_name": None,
                    "fields": [], "quality": None, "unreadable": [],
                    "sam_found": True, "cut_edges": _touches_edge(box),
                    "area_ratio": round(_area_ratio(box), 4),
                    "rejected": False,
                })
                new_docs.append(doc_id)
        record.scanned_photos.append(photo)
    record.add_log("find_documents: %d new (%s)" %
                   (len(new_docs), ",".join(new_docs)))
    return {"documents": new_docs, "total": len(record.documents)}


READ_SYSTEM = (
    "You read Indian document photos for a scholarship form. "
    "Reply with exactly one JSON object, no other text."
)

READ_PROMPT = """Look at this document crop and transcribe what you see.

doc_type must be one of: identity_card, marksheet, income_certificate,
caste_certificate, bank_passbook, land_record, crop_field_photo, other.
holder_name is the person the document belongs to (or null).
fields is a list of {"key": <field id>, "value": <exact value>,
"quote": <VERBATIM text from the document>} using these field ids:
applicant_name, father_name, date_of_birth, gender, aadhaar_number,
address, pin_code, category, annual_family_income, previous_exam,
previous_marks_obtained, previous_marks_max, previous_percentage,
bank_account_holder, bank_account_number, ifsc_code, bank_name.
Only include fields you can actually read. The quote must be copied
word-for-word from the document, including spelling mistakes.
unreadable lists labels of parts you cannot read (e.g. "seal",
"signature", "photo").
quality is {"usable": true/false, "issues": [...],
"advice": "one short retake tip or empty string"}.

Reply with exactly one JSON object:
{"doc_type": ..., "holder_name": ..., "fields": [...],
 "unreadable": [...], "quality": {...}}"""


def read_document(record, doc_id):
    # type: (CaseRecord, str) -> Dict[str, Any]
    """Ask Spark to read a document crop; store type, fields and quality."""
    doc = record.doc()
    if doc is None:
        return {"ok": False, "error": "unknown doc_id %r" % (doc_id,)}
    if doc.get("rejected"):
        return {"ok": False, "error": "document %s is rejected" % doc_id}
    try:
        data = meta_client.chat_json(READ_PROMPT, image_path=doc["crop"],
                                     system=READ_SYSTEM)
    except Exception as e:
        return {"ok": False, "error": "read failed: %s" % (e,)}
    doc_type = data.get("doc_type", "other")
    if doc_type not in DOC_TYPES:
        doc_type = "other"
    doc["doc_type"] = doc_type
    doc["holder_name"] = data.get("holder_name")
    kept = []  # type: List[Dict[str, Any]]
    for f in data.get("fields") or []:
        if not isinstance(f, dict):
            continue
        if not f.get("key") or f.get("value") is None:
            continue
        kept.append({"key": f["key"], "value": f["value"],
                     "quote": f.get("quote", "")})
    doc["fields"] = kept
    doc["unreadable"] = list(data.get("unreadable") or [])
    doc["quality"] = data.get("quality") or {"usable": True, "issues": [],
                                             "advice": ""}
    record.add_log("read_document %s: %s (%d fields)" %
                   (doc_id, doc_type, len(kept)))
    return {"ok": True, "doc_id": doc_id, "doc_type": doc_type,
            "holder_name": doc.get("holder_name"), "fields": kept,
            "unreadable": doc["unreadable"], "quality": doc["quality"]}


def fill_fields(record, entries):
    # type: (CaseRecord, List[Dict[str, Any]]) -> Dict[str, Any]
    """Fill form fields from document quotes or applicant utterances."""
    form = load_form(record.form_id)
    results = []  # type: List[Dict[str, Any]]
    for entry in entries or []:
        field_id = (entry or {}).get("field_id")
        spec = field_spec(form, field_id) if field_id else None
        if spec is None:
            results.append({"field_id": field_id, "ok": False,
                            "error": "unknown field %r" % (field_id,)})
            continue
        value = entry.get("value")
        if value is None or (isinstance(value, str) and not value.strip()):
            results.append({"field_id": field_id, "ok": False,
                            "error": "missing value"})
            continue
        doc_id = entry.get("doc_id")
        utterance_id = entry.get("utterance_id")
        source = None  # type: Optional[Dict[str, Any]]
        if utterance_id:
            if not spec.get("voice_ok"):
                results.append({
                    "field_id": field_id, "ok": False,
                    "error": "field %s cannot be filled from speech "
                             "(voice_ok is false)" % field_id})
                continue
            if not any(u.get("id") == utterance_id
                       for u in record.utterances):
                results.append({"field_id": field_id, "ok": False,
                                "error": "unknown utterance %r"
                                % (utterance_id,)})
                continue
            source = {"type": "applicant", "utterance_id": utterance_id}
        elif doc_id:
            doc = record.doc(doc_id)
            if doc is None or doc.get("rejected"):
                results.append({"field_id": field_id, "ok": False,
                                "error": "unknown or rejected doc %r"
                                % (doc_id,)})
                continue
            quote = entry.get("quote")
            if not quote:
                results.append({"field_id": field_id, "ok": False,
                                "error": "document source needs a quote"})
                continue
            source = {"type": "document", "doc_id": doc_id, "quote": quote}
        else:
            results.append({"field_id": field_id, "ok": False,
                            "error": "give doc_id + quote or utterance_id"})
            continue
        warnings = []  # type: List[str]
        if spec.get("check"):
            w = _warn(spec["check"], value)
            if w:
                warnings.append(w)
        record.fields[field_id] = {"value": value, "source": source}
        results.append({"field_id": field_id, "ok": True,
                        "warnings": warnings})
    still_empty = [f["id"] for f in form.get("fields", [])
                   if f["id"] not in record.fields]
    record.add_log("fill_fields: %d/%d ok, %d still empty" %
                   (sum(1 for r in results if r.get("ok")),
                    len(results), len(still_empty)))
    return {"results": results, "still_empty": still_empty}


def clear_field(record, field_id):
    # type: (CaseRecord, str) -> Dict[str, Any]
    """Remove a filled field so it can be filled again."""
    if field_id in record.fields:
        del record.fields[field_id]
        record.add_log("clear_field %s" % field_id)
        return {"ok": True, "field_id": field_id}
    return {"ok": False, "error": "field %s is not filled" % (field_id,)}


def _effective_percentage(record):
    # type: (CaseRecord) -> Any
    """Stored percentage, else computed from obtained/max, else None."""
    raw = (record.fields.get("previous_percentage") or {}).get("value")
    if raw is not None and str(raw).strip() != "":
        try:
            return float(str(raw).replace("%", "").strip())
        except (ValueError, TypeError):
            return raw
    try:
        obt = float(str((record.fields.get("previous_marks_obtained")
                         or {}).get("value")).replace(",", "").strip())
        mx = float(str((record.fields.get("previous_marks_max")
                        or {}).get("value")).replace(",", "").strip())
    except (ValueError, TypeError, AttributeError):
        return None
    if mx <= 0:
        return None
    return round(obt / mx * 100.0, 2)


def check_eligibility(record):
    # type: (CaseRecord) -> Dict[str, Any]
    """Deterministic eligibility check from the form's rules."""
    form = load_form(record.form_id)
    rules = form.get("eligibility", {})
    reasons = []  # type: List[str]
    cat_raw = (record.fields.get("category") or {}).get("value")
    category = str(cat_raw).strip().upper() if cat_raw else None
    income = parse_income((record.fields.get("annual_family_income")
                           or {}).get("value"))
    percentage = _effective_percentage(record)
    checked = {"category": category, "annual_family_income": income,
               "previous_percentage": percentage}
    allowed = [c.upper() for c in rules.get("categories", [])]
    if not category:
        reasons.append("category is missing")
    elif category not in allowed:
        reasons.append("category %s is not eligible (need one of %s)"
                       % (category, "/".join(allowed)))
    if income is None:
        reasons.append("annual family income is missing")
    elif income > rules.get("max_annual_income", 0):
        reasons.append("annual family income %d exceeds the limit %d"
                       % (income, rules.get("max_annual_income", 0)))
    if percentage is None or (isinstance(percentage, str)):
        reasons.append("previous percentage is missing")
    elif percentage < rules.get("min_previous_percentage", 0):
        reasons.append("previous percentage %s is below the minimum %s"
                       % (percentage,
                          rules.get("min_previous_percentage", 0)))
    eligible = not reasons
    record.eligibility = {"eligible": eligible, "reasons": reasons,
                          "checked_values": checked}
    record.add_log("check_eligibility: %s" %
                   ("eligible" if eligible else "; ".join(reasons)))
    return {"eligible": eligible, "reasons": reasons,
            "checked_values": checked}


def _translate(text, language):
    # type: (str, str) -> str
    if language == "en":
        return text
    name = LANG_NAMES.get(language, language)
    msg = meta_client.chat(
        "Translate this to %s. Reply with only the translation, no quotes."
        "\n\n%s" % (name, text))
    return (msg.content or "").strip() or text


def ask_applicant(record, question_en, field_ids):
    # type: (CaseRecord, str, List[str]) -> Dict[str, Any]
    """Ask the applicant one question; case waits for their answer."""
    if not question_en or not str(question_en).strip():
        return {"ok": False, "error": "question_en is required"}
    if not field_ids:
        return {"ok": False, "error": "field_ids is required"}
    qid = "q%d" % (len(record.questions) + 1)
    try:
        local = _translate(str(question_en), record.language)
    except Exception as e:
        return {"ok": False, "error": "translation failed: %s" % (e,)}
    record.questions.append({"id": qid, "field_ids": list(field_ids),
                             "question_en": str(question_en),
                             "question_local": local, "answered": False})
    record.status = "needs_input"
    record.add_log("ask_applicant %s: %s" % (qid, question_en))
    return {"ok": True, "question_id": qid, "question_local": local}


def flag_discrepancy(record, target, detail):
    # type: (CaseRecord, str, str) -> Dict[str, Any]
    """Flag a mismatch openly instead of hiding it."""
    if not target or not detail:
        return {"ok": False, "error": "target and detail are required"}
    did = "disc%d" % (len(record.discrepancies) + 1)
    record.discrepancies.append({"id": did, "field_id": target,
                                 "detail": detail})
    record.add_log("flag_discrepancy %s on %s" % (did, target))
    return {"ok": True, "id": did, "field_id": target, "detail": detail}


def declare_ineligible(record, reason):
    # type: (CaseRecord, str) -> Dict[str, Any]
    """Close the case as ineligible after a failed eligibility check."""
    elig = record.eligibility or {}
    if elig.get("eligible") is not False:
        return {"ok": False,
                "error": "run check_eligibility first and only declare "
                         "after it fails"}
    if not reason or not str(reason).strip():
        return {"ok": False, "error": "reason is required"}
    try:
        local = _translate(str(reason), record.language)
    except Exception as e:
        return {"ok": False, "error": "translation failed: %s" % (e,)}
    record.eligibility["ineligible_reason_en"] = str(reason)
    record.eligibility["ineligible_reason_local"] = local
    record.status = "ineligible"
    record.add_log("declare_ineligible: %s" % (reason,))
    return {"ok": True, "reason_local": local}


def _minimal_gate(record):
    # type: (CaseRecord) -> Dict[str, Any]
    """Stand-in verification gate until Task 4's verify.py lands."""
    form = load_form(record.form_id)
    missing = [f["id"] for f in form.get("fields", [])
               if f["id"] not in record.fields]
    unquoted = [fid for fid, v in record.fields.items()
                if (v.get("source") or {}).get("type") == "document"
                and not (v.get("source") or {}).get("quote")]
    bad = []  # type: List[str]
    for fid, v in record.fields.items():
        spec = field_spec(form, fid)
        if spec and spec.get("check"):
            w = _warn(spec["check"], v.get("value"))
            if w:
                bad.append("%s: %s" % (fid, w))
    problems = []  # type: List[str]
    if missing:
        problems.append("missing fields: " + ", ".join(missing))
    if unquoted:
        problems.append("fields without quotes: " + ", ".join(unquoted))
    if bad:
        problems.append("format problems: " + "; ".join(bad))
    if problems:
        return {"ok": False, "refusals": problems}
    return {"ok": True, "refusals": []}


def submit_form(record):
    # type: (CaseRecord) -> Dict[str, Any]
    """Run the verification gate; passed forms await applicant signoff."""
    try:
        from verification.gate import run_gate
    except ImportError:
        run_gate = None  # type: ignore[assignment]
    if run_gate is None:
        result = _minimal_gate(record)
        if result.get("ok"):
            record.status = "awaiting_signoff"
            record.add_log("submit_form: passed, awaiting signoff")
            return {"ok": True, "status": record.status}
        refusals = []
        for detail in result.get("refusals", []):
            rid = "r%d" % (len(record.refusals) + 1)
            record.refusals.append({"id": rid, "detail": detail})
            refusals.append({"id": rid, "detail": detail})
        record.add_log("submit_form: refused (%d)" % len(refusals))
        return {"ok": False, "refusals": refusals}
    try:
        gate_result = run_gate(record)
    except Exception as e:
        return {"ok": False, "error": "verification failed: %s" % (e,)}
    if gate_result.get("ok"):
        return {"ok": True, "status": record.status}
    last = record.refusals[-1] if record.refusals else {"detail": "refused"}
    return {"ok": False, "refusals": [last],
            "status": gate_result.get("status")}


def _schema(name, description, properties, required):
    # type: (str, str, Dict[str, Any], List[str]) -> Dict[str, Any]
    return {"type": "function",
            "function": {"name": name, "description": description,
                         "parameters": {"type": "object",
                                        "properties": properties,
                                        "required": required}}}


TOOLS = [
    _schema("find_documents",
            "Find and crop every document in the unscanned case photos.",
            {"properties": {}}, []),
    _schema("read_document",
            "Read one cropped document with vision; store its fields.",
            {"doc_id": {"type": "string",
                        "description": "Document id, e.g. d1"}},
            ["doc_id"]),
    _schema("fill_fields",
            "Fill form fields from document quotes or applicant speech.",
            {"entries": {
                "type": "array",
                "description": "Each entry: field_id, value, and "
                               "doc_id + quote OR utterance_id.",
                "items": {"type": "object",
                          "properties": {
                              "field_id": {"type": "string"},
                              "value": {"type": "string"},
                              "doc_id": {"type": "string"},
                              "quote": {"type": "string"},
                              "utterance_id": {"type": "string"}},
                          "required": ["field_id", "value"]}}},
            ["entries"]),
    _schema("clear_field",
            "Remove a filled field so it can be filled again.",
            {"field_id": {"type": "string"}}, ["field_id"]),
    _schema("check_eligibility",
            "Deterministically check the form's eligibility rules.",
            {"properties": {}}, []),
    _schema("ask_applicant",
            "Ask the applicant one question (translated); waits for input.",
            {"question_en": {"type": "string"},
             "field_ids": {"type": "array",
                           "items": {"type": "string"}}},
            ["question_en", "field_ids"]),
    _schema("flag_discrepancy",
            "Flag a mismatch on a field or doc:<id> instead of hiding it.",
            {"target": {"type": "string",
                        "description": "Field id or doc:<id>."},
             "detail": {"type": "string"}}, ["target", "detail"]),
    _schema("declare_ineligible",
            "Close the case as ineligible after a failed eligibility check.",
            {"reason": {"type": "string"}}, ["reason"]),
    _schema("submit_form",
            "Run the verification gate; passed forms await signoff.",
            {"properties": {}}, []),
]

DISPATCH = {
    "find_documents": find_documents,
    "read_document": read_document,
    "fill_fields": fill_fields,
    "clear_field": clear_field,
    "check_eligibility": check_eligibility,
    "ask_applicant": ask_applicant,
    "flag_discrepancy": flag_discrepancy,
    "declare_ineligible": declare_ineligible,
    "submit_form": submit_form,
}
