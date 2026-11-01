"""Multi-agent pipeline.

intake (SAM + Spark read every document)
  -> profile agent   (who is this applicant? every value traced to a document)
  -> scheme scout    (which schemes fit? deterministic rules, explained)
  -> web researcher  (how to apply: official .gov.in/.nic.in pages only; every fact must quote its page)
  -> form agent      (fills the form, asks the applicant by voice, passes the verification gate)
  -> planner         (one action plan in the applicant's language; only verified facts allowed)
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor

import agent
import web
from case_record import CaseRecord
from meta_client import chat_json, segment
from tools import LANGUAGES, _translate, find_documents, read_document
from verification.checks import parse_money, value_in_quote

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CATALOG = os.path.join(APP_DIR, "schemes", "catalog.json")
EDU_RANK = {"class_8": 1, "class_10": 2, "class_12": 3, "graduate": 4, "postgraduate": 5}
OFFLINE = os.getenv("RESEARCH_OFFLINE") == "1"   # demo mode: use only cached pages


def catalog():
    with open(CATALOG) as f:
        return json.load(f)["schemes"]


def say(record, who, message, data=None):
    record.log.append({"agent": who, "message": message, "data": data})
    if os.getenv("FS_VERBOSE", "1") == "1":
        print(f"[{who}] {message}", flush=True)


def _doc_text(record):
    return "\n".join(f"[{d['id']} {d.get('doc_type')}] " + " | ".join(
        f"{f.get('key')}: {f.get('value')} ({f.get('quote')})" for f in d.get("fields", []))
        for d in record.documents if not d.get("rejected"))


# ---- stage 1: intake -------------------------------------------------------
def intake(record):
    out = find_documents(record, crop_dir=os.path.join(agent.STATE_DIR, record.case_id, "crops"))
    if out.get("error"):
        raise RuntimeError(out["error"])
    for d in record.documents:
        if d.get("doc_type") is None:
            r = read_document(record, d["id"])
            if r.get("error"):
                raise RuntimeError(r["error"])
    say(record, "Intake", f"SAM found {len(record.documents)} documents; Spark read each one.",
        [{"id": d["id"], "type": d["doc_type"], "holder": d["holder_name"]} for d in record.documents])
    return coach(record)


# ---- capture coach -----------------------------------------------------------
ADVICE = {
    "cut_off": "Part of the {doc} is cut off at the {edges}. Step back and keep all four corners inside the photo.",
    "too_far": "The {doc} is too small in the photo. Move closer so it fills most of the frame.",
    "unreadable": "Some details on the {doc} cannot be read ({what}). Hold the phone steady, in good light, without glare.",
    "field_coverage": "The photo does not show enough of the field. Take a wider photo from another angle so the damaged crop fills the frame.",
}


def coach(record):
    """SAM geometry + Spark quality: reject photos that will not work and say exactly how to retake them."""
    asks = []
    for d in record.documents:
        if d.get("rejected") or d.get("coached"):
            continue
        d["coached"] = True
        name = (d.get("doc_type") or "document").replace("_", " ")
        problems = []
        cut = d.get("cut_edges") or []
        if 0 < len(cut) <= 2:
            problems.append(ADVICE["cut_off"].format(doc=name, edges=" and ".join(cut)))
        if d.get("sam_found") and d.get("area_ratio", 1) < 0.05:
            problems.append(ADVICE["too_far"].format(doc=name))
        q = d.get("quality") or {}
        if q.get("usable") is False or d.get("unreadable"):
            problems.append(q.get("advice") or ADVICE["unreadable"].format(doc=name, what=", ".join(d.get("unreadable") or [])))
        if d.get("doc_type") == "crop_field_photo":
            try:
                boxes = segment(record.photos[d["photo_index"]], "plant")
                from PIL import Image
                w, h = Image.open(record.photos[d["photo_index"]]).size
                cover = sum((b["x2"] - b["x1"]) * (b["y2"] - b["y1"]) for b in boxes) / float(w * h)
                d["plant_coverage"] = round(min(cover, 1.0), 2)
                if cover < 0.2:
                    problems.append(ADVICE["field_coverage"])
            except Exception:
                pass
        if problems:
            d["rejected"] = True
            text_en = " ".join(problems)
            asks.append({"doc_id": d["id"], "photo_index": d.get("photo_index"), "advice_en": text_en,
                         "advice_local": _translate(record, text_en)})
    if asks:
        record.photo_requests = getattr(record, "photo_requests", []) + asks
        record.status = "needs_photo"
        say(record, "Capture coach", f"{len(asks)} photo(s) will not work; asked for a retake.", asks)
        return "needs_photo"
    say(record, "Capture coach", "All photos are usable.")
    return None


# ---- stage 2: profile ------------------------------------------------------
PROFILE_KEYS = ["name", "gender", "date_of_birth", "state", "district", "category", "annual_family_income",
                "education_level", "last_exam_percentage", "course_type", "owns_farmland"]


def profile(record):
    prompt = ("Build the applicant's profile from these documents. Use ONLY what is printed. Unknown -> null.\n"
              f"{_doc_text(record)}\n\nReturn ONLY JSON with keys {PROFILE_KEYS}. "
              "education_level is one of class_8|class_10|class_12|graduate|postgraduate (highest PASSED). "
              "course_type is technical|non_technical|null. owns_farmland is true|false|null. "
              'Also "evidence": {key: "the exact printed text it came from"}.')
    p = chat_json(prompt)
    evidence = p.pop("evidence", {}) or {}
    alltext = _doc_text(record)
    unverified = []
    for k in ("annual_family_income", "last_exam_percentage", "category", "date_of_birth"):
        v = p.get(k)
        if v is not None and not value_in_quote(v, alltext):
            unverified.append(k)
            p[k] = None
    p["annual_family_income"] = parse_money(p.get("annual_family_income")) if p.get("annual_family_income") is not None else None
    record.profile = {k: p.get(k) for k in PROFILE_KEYS}
    record.profile["evidence"] = evidence
    msg = "Profile built from documents."
    if unverified:
        msg += f" Dropped values not found on any document: {unverified}."
    say(record, "Profile agent", msg, record.profile)


# ---- stage 3: scheme scout ---------------------------------------------------
def _judge_rules(rules, prof):
    reasons, unknown = [], []

    def need(key):
        if prof.get(key) is None:
            unknown.append(key)
            return False
        return True

    if "category_in" in rules and need("category"):
        if str(prof["category"]).upper() not in rules["category_in"]:
            reasons.append(f"category {prof['category']} not in {rules['category_in']}")
    if "max_income" in rules and need("annual_family_income"):
        if prof["annual_family_income"] > rules["max_income"]:
            reasons.append(f"family income Rs {prof['annual_family_income']:,} is above Rs {rules['max_income']:,}")
    if "min_percentage" in rules and need("last_exam_percentage"):
        try:
            if float(str(prof["last_exam_percentage"]).rstrip("%")) < rules["min_percentage"]:
                reasons.append(f"{prof['last_exam_percentage']}% is below {rules['min_percentage']}%")
        except ValueError:
            unknown.append("last_exam_percentage")
    if "min_education" in rules and need("education_level"):
        if EDU_RANK.get(prof["education_level"], 0) < EDU_RANK[rules["min_education"]]:
            reasons.append(f"needs {rules['min_education']} passed")
    if "gender" in rules and need("gender"):
        if str(prof["gender"]).lower() != rules["gender"].lower():
            reasons.append(f"only for {rules['gender']} applicants")
    if "course_type" in rules and need("course_type"):
        if prof["course_type"] != rules["course_type"]:
            reasons.append(f"only for {rules['course_type']} courses")
    if "owns_farmland" in rules and need("owns_farmland"):
        if not prof["owns_farmland"]:
            reasons.append("family does not own farmland")
    if reasons:
        return "not_eligible", reasons
    if unknown:
        return "needs_info", [f"unknown: {u}" for u in unknown]
    return "eligible", []


def scout(record):
    verdicts = []
    for s in catalog():
        v, why = _judge_rules(s["rules"], record.profile or {})
        verdicts.append({"id": s["id"], "name": s["name"], "verdict": v, "reasons": why, "form_id": s["form_id"]})
    record.schemes = verdicts
    n = sum(v["verdict"] == "eligible" for v in verdicts)
    say(record, "Scheme scout", f"Checked {len(verdicts)} schemes: {n} eligible.", verdicts)


# ---- stage 4: web research ---------------------------------------------------
def _research_one(scheme):
    pages, tried = [], set()
    urls = list(scheme.get("seed_urls", []))
    for q in scheme.get("search", []):
        try:
            for hit in web.search(q, offline=OFFLINE):
                if web.is_official(hit["url"], scheme.get("extra_domains", [])):
                    urls.append(hit["url"])
        except Exception:
            pass
    for u in urls:
        if u in tried or len(pages) >= 4:
            continue
        tried.add(u)
        if not web.is_official(u, scheme.get("extra_domains", [])):
            continue
        try:
            p = web.fetch(u, offline=OFFLINE)
        except Exception:
            continue
        if len(p.get("text", "")) > 300:
            pages.append(p)
    if not pages:
        return {"facts": [], "sources": [], "dropped": 0, "note": "no official page could be fetched"}
    corpus = "\n\n".join(f"### SOURCE {i}: {p['url']}\n{p['text'][:7000]}" for i, p in enumerate(pages))
    prompt = (f"Scheme: {scheme['name']}.\nFrom ONLY these official pages, extract how to apply.\n{corpus}\n\n"
              'Return ONLY JSON: {"facts": [{"kind": "portal|deadline|document|step|eligibility", '
              '"text": "plain English fact", "source": <SOURCE number>, '
              '"quote": "an exact sentence copied from that source that proves it"}]}. '
              "If something is not on the pages, leave it out. Never use outside knowledge.")
    try:
        raw = chat_json(prompt).get("facts", [])
    except Exception as e:
        return {"facts": [], "sources": [p["url"] for p in pages], "dropped": 0, "note": f"extraction failed: {e}"}
    facts, dropped = [], 0
    for i, f in enumerate(raw):
        try:
            page = pages[int(f.get("source"))]
        except (TypeError, ValueError, IndexError):
            dropped += 1
            continue
        if web.quote_on_page(f.get("quote"), page["text"]):
            facts.append({"id": f"{scheme['id']}#{len(facts) + 1}", "kind": f.get("kind"), "text": f.get("text"),
                          "url": page["url"], "quote": f.get("quote")})
        else:
            dropped += 1
    return {"facts": facts, "sources": [p["url"] for p in pages], "dropped": dropped}


def research(record):
    todo = [s for s in catalog() if any(v["id"] == s["id"] and v["verdict"] in ("eligible", "needs_info")
                                        for v in record.schemes)]
    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(_research_one, todo))
    for s, r in zip(todo, results):
        record.research[s["id"]] = r
        say(record, "Web researcher",
            f"{s['name']}: {len(r['facts'])} facts verified on {len(r['sources'])} official pages"
            + (f", {r['dropped']} unproven facts thrown out." if r.get("dropped") else ".")
            + (f" {r['note']}" if r.get("note") else ""), r)


# ---- stage 6: planner --------------------------------------------------------
def planner(record):
    facts = {f["id"]: f for r in record.research.values() for f in r.get("facts", [])}
    form_state = {"status": record.status, "discrepancies": record.discrepancies,
                  "filled": len(record.fields), "total": len(record.form["fields"])}
    prompt = ("Write an action plan for this applicant. Use ONLY the facts below; cite fact ids.\n"
              f"PROFILE: {json.dumps(record.profile, ensure_ascii=False)}\n"
              f"SCHEMES: {json.dumps(record.schemes, ensure_ascii=False)}\n"
              f"VERIFIED FACTS: {json.dumps(list(facts.values()), ensure_ascii=False)}\n"
              f"FORM: {json.dumps(form_state, ensure_ascii=False)}\n"
              'Return ONLY JSON: {"summary": "2 sentences", "steps": [{"title": "...", "detail": "...", '
              '"scheme_id": "... or null", "fact_ids": ["..."]}]}. Put fixing discrepancies first. '
              "Max 7 steps. Simple words.")
    plan = chat_json(prompt)
    bad = 0
    for st in plan.get("steps", []):
        refs = [f for f in st.get("fact_ids") or [] if f in facts]
        bad += len(st.get("fact_ids") or []) - len(refs)
        st["fact_ids"] = refs
        st["sources"] = sorted({facts[f]["url"] for f in refs})
    lang = LANGUAGES.get(record.language, "Hindi")
    text_en = plan.get("summary", "") + "\n" + "\n".join(
        f"{i + 1}. {s['title']}: {s['detail']}" for i, s in enumerate(plan.get("steps", [])))
    plan["local"] = _translate(record, text_en) if record.language != "en" else text_en
    plan["language"] = lang
    record.plan = plan
    say(record, "Planner", f"Plan ready: {len(plan.get('steps', []))} steps, translated to {lang}."
        + (f" Removed {bad} citations to unverified facts." if bad else ""), plan)


# ---- orchestration ------------------------------------------------------------
def _save(record, history, turn):
    agent.save(record, history, turn, record.status)


def run(case_id):
    record, history, turn, _ = agent.load(case_id)
    stages = [("intake", intake), ("profile", profile), ("scout", scout), ("research", research)]
    order = [s for s, _ in stages] + ["form", "plan", "done"]
    for name, fn in stages:
        if order.index(record.stage) > order.index(name):
            continue
        record.stage = name
        record.status = "running"
        _save(record, history, turn)
        if fn(record) == "needs_photo":
            _save(record, history, turn)
            return {"case_id": case_id, "status": "needs_photo", "stage": name}
        record.stage = order[order.index(name) + 1]
        _save(record, history, turn)
    if record.stage == "form":
        eligible_form = next((v for v in record.schemes if v["form_id"] == record.form_id and v["verdict"] == "eligible"), None)
        if eligible_form:
            say(record, "Form agent", f"Filling {record.form['title']}.")
            _save(record, history, turn)
            out = agent.run(record, history, turn)
            record, history, turn, _ = agent.load(case_id)
            if out["status"] == "needs_input":
                return out
        else:
            say(record, "Form agent", "Skipped: the applicant is not eligible for the scheme this form belongs to.")
        record.stage = "plan"
        _save(record, history, turn)
    if record.stage == "plan":
        final = record.status
        record.status = "running"
        _save(record, history, turn)
        planner(record)
        record.status = final if final not in ("running", "open") else "planned"
        record.stage = "done"
        _save(record, history, turn)
    return {"case_id": case_id, "status": record.status, "stage": record.stage}


def start(case_id, photos, language="hi"):
    record = CaseRecord(case_id, language=language)
    for p in photos:
        record.add_photo(p)
    agent.save(record, [], 0, "running")
    return run(case_id)


def add_photos(case_id, photos):
    record, history, turn, status = agent.load(case_id)
    for p in photos:
        record.add_photo(p)
    for r in getattr(record, "photo_requests", []):
        r["answered"] = True
    if status == "needs_photo":
        record.stage = "intake"
    elif record.stage == "done":
        record.stage = "intake"   # new evidence: rerun everything after intake
    say(record, "Applicant", f"Added {len(photos)} photo(s).")
    agent.save(record, history, turn, "running")
    return run(case_id)


def answer(case_id, text, audio=None):
    record, history, turn, status = agent.load(case_id)
    if status != "needs_input":
        raise ValueError(f"case is {status}, not waiting for an answer")
    uid = record.add_utterance(text, audio)
    history.append({"turn": turn, "plan": "Applicant answered", "act": "applicant_answer",
                    "observe": {"utterance_id": uid, "text": text}})
    agent.save(record, history, turn, "running")
    return run(case_id)
