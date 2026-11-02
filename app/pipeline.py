"""Multi-agent pipeline: intake -> profile -> scout -> research -> form -> plan -> done.

run(case_id) resumes from record.stage. start() begins a case, add_photos()
supplies retakes after a needs_photo pause, answer() replies to a
needs_input pause. Every agent logs {agent, message, data} and prints it.
"""
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

import agent
import meta_client
import tools
import web
from case_record import CaseRecord

HERE = os.path.dirname(os.path.abspath(__file__))

STAGES = ("intake", "profile", "scout", "research", "form", "plan", "done")

PAUSED = ("needs_photo", "needs_input")

PROFILE_KEYS = ("name", "gender", "date_of_birth", "state", "district",
                "category", "annual_family_income", "education_level",
                "last_exam_percentage", "course_type", "owns_farmland")

PROFILE_SYSTEM = (
    "You build an applicant profile from Indian document reads. "
    "Reply with exactly one JSON object, no other text."
)

PROFILE_PROMPT = """Build this applicant profile using ONLY the document lines below.

Keys: name, gender, date_of_birth, state, district, category,
annual_family_income (number, rupees), education_level, last_exam_percentage
(number 0-100), course_type, owns_farmland (true/false/null).
Use only values stated in the documents. When a value is not stated, use null.
Do not guess income, percentage, category, dates, land or course details.
Reply with exactly one JSON object with exactly these keys.

Documents:
---
%s
---"""

PLAN_SYSTEM = (
    "You write a scholarship action plan using only verified facts. "
    "Reply with exactly one JSON object, no other text."
)

PLAN_PROMPT = """Write an action plan for this applicant.

Verified facts (id | scheme | text):
---
%s
---
Open discrepancies (fix these first):
---
%s
---
Applicant profile: %s
Eligible schemes: %s

Rules: use ONLY the verified facts above (cite their ids); put discrepancy
fixes first; at most 7 steps. Each step: {"title", "detail", "scheme_id",
"fact_ids"}. Reply with exactly one JSON object:
{"summary": "...", "steps": [...]}"""

DOC_LABELS = {
    "identity_card": "identity card",
    "marksheet": "marksheet",
    "income_certificate": "income certificate",
    "caste_certificate": "caste certificate",
    "bank_passbook": "bank passbook",
    "land_record": "land record",
    "crop_field_photo": "crop field photo",
    "other": "document",
}

_catalog = None  # type: Optional[Dict[str, Any]]


# ------------------------------------------------------------------ log ---

def log_agent(record, agent_name, message, data=None):
    # type: (CaseRecord, str, str, Optional[Any]) -> Dict[str, Any]
    """Append {agent, message, data} to record.log and print it."""
    entry = {"agent": agent_name, "message": message,
             "data": data if data is not None else {}}  # type: Dict[str, Any]
    record.log.append(entry)
    print("[%s] %s" % (agent_name, message))
    return entry


def _translate(text, language):
    # type: (str, str) -> str
    if not text or language == "en":
        return text
    try:
        msg = meta_client.chat(
            "Translate this to %s. Reply with only the translation, no quotes."
            "\n\n%s" % (tools.LANG_NAMES.get(language, language), text))
        return (msg.content or "").strip() or text
    except Exception:
        return text


# -------------------------------------------------------------- catalog ---

def load_catalog():
    # type: () -> Dict[str, Any]
    """Load (and cache) app/schemes/catalog.json."""
    global _catalog
    if _catalog is None:
        path = os.path.join(HERE, "schemes", "catalog.json")
        with open(path, "r", encoding="utf-8") as f:
            _catalog = json.load(f)
    return _catalog


def scheme_by_id(scheme_id):
    # type: (str) -> Optional[Dict[str, Any]]
    for s in load_catalog().get("schemes", []):
        if s.get("scheme_id") == scheme_id:
            return s
    return None


def _num(value):
    # type: (Any) -> Optional[float]
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    parsed = tools.parse_income(value)
    if parsed is not None and re.search(r"\d", str(value)):
        return float(parsed)
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except (ValueError, TypeError):
        return None


def _check_op(actual, op, expected):
    # type: (Any, str, Any) -> bool
    if op == "is_true":
        return actual is True
    if op == "is_false":
        return actual is False
    if op == "in":
        want = [str(v).casefold() for v in (expected or [])]
        return str(actual).casefold() in want
    if op in ("==", "!=", ">=", "<=", ">", "<"):
        if op in ("==", "!="):
            eq = str(actual).casefold() == str(expected).casefold()
            return eq if op == "==" else not eq
        a, b = _num(actual), _num(expected)
        if a is None or b is None:
            return False
        if op == ">=":
            return a >= b
        if op == "<=":
            return a <= b
        if op == ">":
            return a > b
        return a < b
    return False


def evaluate_scheme(scheme, profile):
    # type: (Dict[str, Any], Dict[str, Any]) -> Dict[str, Any]
    """Deterministic eligible / not_eligible / needs_info with reasons."""
    rules = scheme.get("rules") or {}
    reasons = []  # type: List[str]
    missing = []
    for field in rules.get("required_fields") or []:
        val = (profile or {}).get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(field)
    if missing:
        reasons = ["need %s: not found in the documents" % f for f in missing]
        return {"scheme_id": scheme.get("scheme_id"),
                "title": scheme.get("title"), "status": "needs_info",
                "reasons": reasons}
    for cond in rules.get("all_of") or []:
        field = cond.get("field")
        if not _check_op((profile or {}).get(field), cond.get("op"),
                         cond.get("value")):
            reasons.append(cond.get("detail") or
                           "rule failed for %s" % (field,))
    if reasons:
        return {"scheme_id": scheme.get("scheme_id"),
                "title": scheme.get("title"), "status": "not_eligible",
                "reasons": reasons}
    return {"scheme_id": scheme.get("scheme_id"), "title": scheme.get("title"),
            "status": "eligible", "reasons": ["meets all scheme rules"]}


# ---------------------------------------------------------------- intake ---

def _touched_edges(box):
    # type: (Dict[str, int]) -> List[str]
    w, h = box["w"], box["h"]
    tol = tools.EDGE_TOLERANCE
    edges = []  # type: List[str]
    if box["x1"] <= tol * w:
        edges.append("left")
    if box["y1"] <= tol * h:
        edges.append("top")
    if box["x2"] >= w - tol * w:
        edges.append("right")
    if box["y2"] >= h - tol * h:
        edges.append("bottom")
    return edges


def _plant_cover(doc):
    # type: (Dict[str, Any]) -> Optional[float]
    """Total SAM 'plant' box area as a fraction of the frame."""
    try:
        boxes = meta_client.segment(doc.get("crop") or doc.get("photo"),
                                    "plant")
    except Exception:
        return None
    total = 0.0
    for b in boxes or []:
        frame = (b.get("w") or 0) * (b.get("h") or 0)
        if frame > 0:
            total += ((b["x2"] - b["x1"]) * (b["y2"] - b["y1"])) / frame
    return total


def _coach(doc):
    # type: (Dict[str, Any]) -> Tuple[List[str], str]
    """Return (reasons, advice_en) for a freshly read document."""
    label = DOC_LABELS.get(doc.get("doc_type") or "other", "document")
    reasons = []  # type: List[str]
    parts = []  # type: List[str]
    box = doc.get("box")
    if box and box.get("w") and box.get("h"):
        edges = _touched_edges(box)
        if 1 <= len(edges) <= 2:
            reasons.append("cut_off")
            parts.append("Part of the %s is cut off at the %s. Step back "
                         "and keep all four corners inside the photo."
                         % (label, " and ".join(edges)))
        area = doc.get("area_ratio")
        if area is None:
            frame = box["w"] * box["h"]
            area = ((box["x2"] - box["x1"]) *
                    (box["y2"] - box["y1"])) / frame if frame else 0.0
        if area < 0.05:
            reasons.append("too_small")
            parts.append("The %s covers only a small part of the photo. "
                         "Move closer so it fills the frame." % (label,))
    quality = doc.get("quality") or {}
    if quality.get("usable") is False:
        reasons.append("quality")
        tip = (quality.get("advice") or "").strip()
        if tip:
            parts.append(tip)
        else:
            parts.append("The %s photo is not readable. Retake it in good "
                         "light without shadow." % (label,))
    unreadable = doc.get("unreadable") or []
    if [u for u in unreadable if str(u).strip()]:
        reasons.append("unreadable")
        parts.append("We could not read the %s in the %s photo. Retake it "
                     "sharply in good light."
                     % (", ".join(str(u) for u in unreadable), label))
    if doc.get("doc_type") == "crop_field_photo":
        cover = _plant_cover(doc)
        if cover is not None and cover < 0.20:
            reasons.append("no_crop")
            parts.append("The crop photo shows too few plants. Step back so "
                         "the crop fills the frame and retake it.")
    return reasons, " ".join(parts)


def _intake(record, history):
    # type: (CaseRecord, List[Dict[str, Any]]) -> None
    tools.find_documents(record)
    fresh = [d for d in record.documents
             if not d.get("rejected") and d.get("doc_type") is None]
    for doc in fresh:
        tools.read_document(record, doc["id"])
        reasons, advice_en = _coach(doc)
        if reasons:
            doc["rejected"] = True
            advice_local = _translate(advice_en, record.language)
            record.photo_requests.append({
                "doc_id": doc["id"], "photo": doc.get("photo"),
                "advice_en": advice_en, "advice_local": advice_local,
                "reasons": reasons,
            })
            log_agent(record, "intake",
                      "rejected %s (%s)" % (doc["id"], ", ".join(reasons)),
                      {"doc_id": doc["id"], "advice": advice_en})
    new_rejects = [d for d in fresh if d.get("rejected")]
    if new_rejects:
        record.status = "needs_photo"
        log_agent(record, "intake",
                  "paused: %d photo request(s), waiting for retakes"
                  % len(record.photo_requests),
                  {"photo_requests": record.photo_requests})
        return
    record.status = "open"
    record.stage = "profile"
    log_agent(record, "intake",
              "read %d document(s), all usable" % len(record.documents),
              {"documents": [d.get("id") for d in record.documents]})


# --------------------------------------------------------------- profile ---

def _doc_blob(record):
    # type: (CaseRecord) -> str
    lines = []  # type: List[str]
    for d in record.documents:
        if d.get("rejected"):
            continue
        for f in d.get("fields") or []:
            if isinstance(f, dict):
                lines.append("%s = %s [%s]" % (f.get("key"), f.get("value"),
                                               f.get("quote")))
    return "\n".join(lines)


def _norm(text):
    # type: (Any) -> str
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]", " ",
                                      "" if text is None else str(text).lower())).strip()


def _digits(text):
    # type: (Any) -> str
    return re.sub(r"\D", "", "" if text is None else str(text))


def _literal_present(value, blob):
    # type: (Any, str) -> bool
    if value is None or (isinstance(value, str) and not value.strip()):
        return True
    nv, nb = _norm(value), _norm(blob)
    if nv and nv in nb:
        return True
    dv, db = _digits(value), _digits(blob)
    return bool(dv) and dv in db


def _profile(record, history):
    # type: (CaseRecord, List[Dict[str, Any]]) -> None
    blob = _doc_blob(record)
    try:
        data = meta_client.chat_json(PROFILE_PROMPT % blob,
                                     system=PROFILE_SYSTEM)
    except Exception as e:
        data = {}
        log_agent(record, "profile", "Spark profile failed: %s" % (e,), {})
    profile = {}  # type: Dict[str, Any]
    if isinstance(data, dict):
        for key in PROFILE_KEYS:
            profile[key] = data.get(key)
    else:
        for key in PROFILE_KEYS:
            profile[key] = None
    for key in ("annual_family_income", "last_exam_percentage", "category",
                "date_of_birth"):
        if not _literal_present(profile.get(key), blob):
            profile[key] = None
    record.profile = profile
    record.stage = "scout"
    log_agent(record, "profile", "built profile from %d document(s)"
              % len([d for d in record.documents if not d.get("rejected")]),
              {"profile": profile})


# ----------------------------------------------------------------- scout ---

def _scout(record, history):
    # type: (CaseRecord, List[Dict[str, Any]]) -> None
    profile = record.profile or {}
    record.schemes = [evaluate_scheme(s, profile)
                      for s in load_catalog().get("schemes", [])]
    record.stage = "research"
    log_agent(record, "scout", "scouted %d scheme(s): %s"
              % (len(record.schemes), ", ".join(
                  "%s=%s" % (s["scheme_id"], s["status"])
                  for s in record.schemes)),
              {"schemes": record.schemes})


# -------------------------------------------------------------- research ---

def _research(record, history):
    # type: (CaseRecord, List[Dict[str, Any]]) -> None
    wanted = [s for s in (record.schemes or [])
              if s.get("status") in ("eligible", "needs_info")]
    by_id = {}  # type: Dict[str, Dict[str, Any]]
    for s in load_catalog().get("schemes", []):
        by_id[s["scheme_id"]] = s
    results = {}  # type: Dict[str, Any]
    if wanted:
        with ThreadPoolExecutor(max_workers=min(4, len(wanted))) as pool:
            future_of = {}
            for s in wanted:
                full = by_id.get(s["scheme_id"]) or {"scheme_id": s["scheme_id"]}
                future_of[pool.submit(web.research_scheme, full)] = s["scheme_id"]
            for fut, scheme_id in future_of.items():
                try:
                    results[scheme_id] = fut.result()
                except Exception as e:
                    results[scheme_id] = {"scheme_id": scheme_id, "facts": [],
                                          "sources": [], "dropped": 1,
                                          "error": "%s" % (e,)}
    record.research = {}
    counter = 0
    total_dropped = 0
    for s in wanted:
        scheme_id = s["scheme_id"]
        res = results.get(scheme_id) or {}
        sources = list(res.get("sources") or [])
        facts = []  # type: List[Dict[str, Any]]
        for f in res.get("facts") or []:
            counter += 1
            src = f.get("source", 0)
            url = sources[src] if isinstance(src, int) and 0 <= src < len(sources) else ""
            facts.append({"id": "f%d" % counter, "kind": f.get("kind"),
                          "text": f.get("text"), "quote": f.get("quote"),
                          "scheme_id": scheme_id, "source": src, "url": url})
        record.research[scheme_id] = {"facts": facts, "sources": sources,
                                      "dropped": res.get("dropped", 0)}
        total_dropped += res.get("dropped", 0)
    record.stage = "form"
    log_agent(record, "research",
              "researched %d scheme(s): %d fact(s), %d dropped quote(s)"
              % (len(wanted), counter, total_dropped),
              {"schemes": [s["scheme_id"] for s in wanted],
               "facts": counter, "dropped": total_dropped})


# ------------------------------------------------------------------ form ---

def _form(record, history):
    # type: (CaseRecord, List[Dict[str, Any]]) -> None
    form_scheme = None  # type: Optional[Dict[str, Any]]
    for s in load_catalog().get("schemes", []):
        if s.get("form_id") == record.form_id:
            form_scheme = s
            break
    verdict = None  # type: Optional[Dict[str, Any]]
    for s in record.schemes or []:
        if form_scheme and s.get("scheme_id") == form_scheme.get("scheme_id"):
            verdict = s
    if verdict is None or verdict.get("status") != "eligible":
        record.stage = "plan"
        log_agent(record, "form",
                  "skipped Task 3 loop: scheme %s is %s"
                  % (form_scheme.get("scheme_id") if form_scheme else record.form_id,
                     (verdict or {}).get("status", "unknown")),
                  {"verdict": verdict})
        return
    record.stage = "form"
    agent.save(record, history)
    record, _ = agent.run(record, history)
    agent.save(record, history)
    if record.status == "needs_input":
        log_agent(record, "form", "paused: waiting for applicant answer",
                  {"questions": record.questions[-1:]})
        return
    if record.status == "awaiting_signoff" and form_scheme is not None:
        _build_pack(record, form_scheme.get("scheme_id"))
    record.stage = "plan"
    log_agent(record, "form", "Task 3 loop ended with status %s"
              % (record.status,), {"status": record.status})


# ----------------------------------------------------------------- pack ---

def _build_pack(record, scheme_id):
    # type: (CaseRecord, str) -> None
    """Build the upload-ready document pack after signoff (before planning)."""
    try:
        import upload_pack
        pack = upload_pack.make_pack(record, scheme_id)
    except Exception as e:
        log_agent(record, "pack", "upload pack failed: %s" % (e,), {})
        return
    record.pack = pack
    try:
        import upload_pack as _up
        section = _up.scheme_upload_section(scheme_id)
        limit = int((section.get("default") or {}).get("max_kb", 200))
    except Exception:
        limit = 200
    need_manual = [p for p in pack
                   if (p.get("checks") or {}).get("readable")
                   != True]  # noqa: E712
    if need_manual:
        message = ("Upload pack: %d file(s) ready, all under %d KB; "
                   "%d need(s) a manual check."
                   % (len(pack), limit, len(need_manual)))
    else:
        message = ("Upload pack: %d file(s) ready, all under %d KB, "
                   "still readable." % (len(pack), limit))
    log_agent(record, "pack", message, {"pack": pack})


# ------------------------------------------------------------------ plan ---

def _plan(record, history):
    # type: (CaseRecord, List[Dict[str, Any]]) -> None
    lines = []  # type: List[str]
    by_id = {}  # type: Dict[str, Dict[str, Any]]
    for scheme_id, res in ((record.research or {}).items()):
        for f in (res or {}).get("facts") or []:
            lines.append("%s | %s | %s" % (f.get("id"), scheme_id,
                                           f.get("text")))
            by_id[str(f.get("id"))] = f
    disc = ["%s: %s" % (d.get("field_id"), d.get("detail"))
            for d in (record.discrepancies or [])] or ["(none)"]
    eligible = [s["scheme_id"] for s in (record.schemes or [])
                if s.get("status") == "eligible"]
    pack_note = ""
    if getattr(record, "pack", None):
        names = ", ".join(os.path.basename(p.get("path", ""))
                          for p in record.pack)
        pack_note = ("\nUpload pack files ready: %s. You may add a step "
                     "telling the applicant to upload the files from "
                     "your pack on the portal." % names)
    try:
        data = meta_client.chat_json(
            PLAN_PROMPT % ("\n".join(lines) or "(no verified facts)",
                           "\n".join(disc), json.dumps(record.profile or {}),
                           ", ".join(eligible) or "(none)") + pack_note,
            system=PLAN_SYSTEM)
    except Exception as e:
        data = {}
        log_agent(record, "plan", "Spark plan failed: %s" % (e,), {})
    steps = []  # type: List[Dict[str, Any]]
    if isinstance(data, dict):
        for s in (data.get("steps") or [])[:7]:
            if not isinstance(s, dict):
                continue
            good = [fid for fid in (s.get("fact_ids") or [])
                    if str(fid) in by_id]
            urls = []  # type: List[str]
            for fid in good:
                u = by_id[str(fid)].get("url")
                if u and u not in urls:
                    urls.append(u)
            steps.append({"title": s.get("title", ""),
                          "detail": s.get("detail", ""),
                          "scheme_id": s.get("scheme_id", ""),
                          "fact_ids": good, "source_urls": urls})
        summary_en = str(data.get("summary", ""))
    else:
        summary_en = ""
    lang = record.language
    plan = {
        "summary": _translate(summary_en, lang),
        "summary_en": summary_en,
        "steps": [{
            "title": _translate(s["title"], lang),
            "title_en": s["title"],
            "detail": _translate(s["detail"], lang),
            "detail_en": s["detail"],
            "scheme_id": s["scheme_id"],
            "fact_ids": s["fact_ids"],
            "source_urls": s["source_urls"],
        } for s in steps],
        "sources": sorted({u for s in steps for u in s["source_urls"]}),
    }
    record.plan = plan
    record.stage = "done"
    log_agent(record, "plan", "wrote %d step(s)" % len(steps),
              {"plan": plan})


_STAGE_FN = {
    "intake": _intake,
    "profile": _profile,
    "scout": _scout,
    "research": _research,
    "form": _form,
    "plan": _plan,
}


# ------------------------------------------------------------ entry points ---

def load_case(case_id):
    # type: (str) -> Tuple[CaseRecord, List[Dict[str, Any]]]
    return agent.load(case_id)


def run(case_id):
    # type: (str) -> CaseRecord
    """Resume a case from its saved stage until done or paused."""
    record, history = agent.load(case_id)
    if record.stage not in STAGES:
        record.stage = "intake"
    while record.stage != "done":
        if record.status in PAUSED:
            agent.save(record, history)
            break
        fn = _STAGE_FN.get(record.stage)
        if fn is None:
            record.stage = "done"
            agent.save(record, history)
            break
        fn(record, history)
        agent.save(record, history)
    return record


def start(photos, language="hi", case_id=None, form_id="post_matric_scholarship"):
    # type: (List[str], str, Optional[str], str) -> CaseRecord
    """Start a case with photo paths, then run the pipeline."""
    if case_id is None:
        case_id = "case_%d" % int(time.time())
    record = CaseRecord(case_id=case_id, language=language, form_id=form_id)
    record.photos = list(photos)
    record.stage = "intake"
    record.status = "open"
    agent.save(record, [])
    log_agent(record, "pipeline", "started case %s with %d photo(s)"
              % (case_id, len(photos)), {"photos": list(photos)})
    return run(case_id)


def add_photos(case_id, new_photos):
    # type: (str, List[str]) -> CaseRecord
    """Attach retake photos after a needs_photo pause, then resume."""
    record, history = agent.load(case_id)
    added = [p for p in new_photos if p not in record.photos]
    record.photos.extend(added)
    if record.status == "needs_photo":
        record.status = "open"
    if added and record.stage != "intake":
        record.stage = "intake"
    agent.save(record, history)
    log_agent(record, "pipeline", "added %d photo(s)" % len(added),
              {"added": added})
    return run(case_id)


def answer(case_id, text, audio_path=None, question_id=None):
    # type: (str, str, Optional[str], Optional[str]) -> CaseRecord
    """Record an applicant reply after a needs_input pause, then resume."""
    record, history = agent.load(case_id)
    if audio_path:
        try:
            text = meta_client.transcribe(audio_path,
                                          language=record.language)
        except Exception as e:
            log_agent(record, "pipeline", "transcription failed: %s" % (e,),
                      {})
    target = None  # type: Optional[Dict[str, Any]]
    if question_id:
        for q in record.questions:
            if q.get("id") == question_id:
                target = q
    if target is None:
        for q in reversed(record.questions):
            if not q.get("answered"):
                target = q
                break
    uid = "u%d" % (len(record.utterances) + 1)
    record.utterances.append({
        "id": uid, "text": text, "audio": audio_path,
        "question_id": (target or {}).get("id"),
    })
    if target is not None:
        target["answered"] = True
    if record.status == "needs_input":
        record.status = "open"
    agent.save(record, history)
    log_agent(record, "pipeline", "recorded answer %s" % uid, {"text": text})
    return run(case_id)
