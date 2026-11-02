"""FormSaathi offline tests: no API key, no network.

Every Meta call is stubbed by monkeypatching module attributes, so this
script runs fully offline:
  meta_client.chat      -> scripted agent tool calls, "HINDI: ..." translations
  meta_client.chat_json -> document reads / profile / research / plan payloads
  meta_client.segment   -> fixed SAM boxes (cut-off or clean)
  web.ddg_search        -> one .gov.in hit plus one unofficial blog hit
  web.fetch_page        -> canned page text, but only for allowed domains
                          (the real web.allowed check still runs, so the
                          unofficial URL is ignored by real code)
  judge.judge_fields    -> clean (the deterministic rules do the refusing)

Covers:
  1. format checks (Aadhaar, IFSC, mobile, PIN, date, money-in-quote,
     name similarity Patil/Patel).
  2. deterministic rules (INVALID_AADHAAR, NEEDS_DOCUMENT, BAD_SOURCE,
     MISSING_FIELD, ELIGIBILITY_NOT_CHECKED).
  3. case_a scripted form run: needs_input -> answer -> submit refused
     with NAME_MISMATCH -> flag_discrepancy -> awaiting_signoff.
  4. case_c scripted pipeline run: needs_photo (bottom edge) -> retake ->
     research keeps the quoted fact and drops the invented one ->
     form -> plan strips the invented citation and is translated.

Run from the repo root:
  python tests/test_offline.py
Prints ALL OFFLINE TESTS PASSED on success.
"""
import json
import os
import shutil
import sys
import tempfile
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
sys.path.insert(0, APP)
sys.path.insert(0, ROOT)

import meta_client  # noqa: E402
import tools  # noqa: E402
import agent  # noqa: E402
import pipeline  # noqa: E402
import web  # noqa: E402
import render  # noqa: E402
import upload_pack  # noqa: E402
from case_record import CaseRecord  # noqa: E402
from verification import checks  # noqa: E402
from verification import rules  # noqa: E402
from verification import judge as judge_mod  # noqa: E402

COUNT = [0]


def expect(cond, msg):
    # type: (bool, str) -> None
    COUNT[0] += 1
    if not cond:
        raise AssertionError("FAIL: " + msg)
    print("ok %d - %s" % (COUNT[0], msg))


# ------------------------------------------------------------- constants ---

BASE11 = "23456789012"
GOOD_AADHAAR = BASE11 + checks.aadhaar_check_digit(BASE11)
BAD_AADHAAR = GOOD_AADHAAR[:-1] + str((int(GOOD_AADHAAR[-1]) + 1) % 10)

NAME_OK = "Ramesh Patel"
# One changed letter scores exactly 0.9, which rules treat as a match
# (NAME_THRESHOLD is a strict < 0.9), so the case_a mismatch also adds
# a middle initial and drops below the threshold.
NAME_STUBBORN = "Ramesh Patil"
NAME_BAD = "Ramesh K Patil"

Q_NAME = "Name: Ramesh Patel"
Q_FATHER = "Father: Suresh Patel"
Q_DOB = "DOB: 12/04/2002"
Q_GENDER = "Sex: Male"
Q_AADHAAR = "Aadhaar number " + GOOD_AADHAAR
Q_ADDR = "Address: At Post Wadgaon, Nashik"
Q_PIN = "PIN: 422001"
Q_EXAM = "Exam: HSC"
Q_OBT = "Obtained: 650"
Q_MAX = "Max: 1000"
Q_PCT = "Percentage: 65"
Q_CAT = "Category: OBC"
Q_INC = "Annual income Rs. 1,20,000"
Q_HOLDER_OK = "Holder: Ramesh Patel"
Q_HOLDER_BAD = "Holder: Ramesh K Patil"
Q_ACCT = "Account: 123456789012"
Q_IFSC = "IFSC: HDFC0001234"
Q_BANK = "Bank: HDFC Bank"

ANSWER_TEXT = ("My mobile number is 9876543210. "
               "I study BCom at Shivaji College.")

GOV_URL = "https://scholarships.gov.in/post-matric"
BLOG_URL = "https://example-blog.com/scholarship-tips"
PAGE_TEXT = ("Post-Matric Scholarship. Applications must be submitted on "
             "scholarships.gov.in before 31 October 2025. "
             "Keep your caste certificate ready.")
QUOTED_FACT = {
    "kind": "eligibility",
    "text": ("Applications must be submitted on scholarships.gov.in "
             "before 31 October 2025."),
    "quote": ("must be submitted on scholarships.gov.in "
              "before 31 October 2025"),
}
INVENTED_FACT = {
    "kind": "deadline",
    "text": "The deadline is the next full moon.",
    "quote": "the deadline is the next full moon festival gala",
}
PLAN_SUMMARY_EN = "Apply before the deadline with all documents ready."
PLAN_DATA = {
    "summary": PLAN_SUMMARY_EN,
    "steps": [{
        "title": "Submit the application",
        "detail": "Apply on scholarships.gov.in before the deadline.",
        "scheme_id": "post_matric_scholarship",
        "fact_ids": ["f1", "f999"],
    }],
}
PROFILE_DATA = {
    "name": NAME_OK, "gender": None, "date_of_birth": None, "state": None,
    "district": None, "category": "OBC", "annual_family_income": 120000,
    "education_level": "ug", "last_exam_percentage": 65, "course_type": None,
    "owns_farmland": None,
}

GOOD_BOX = {"x1": 60, "y1": 60, "x2": 1740, "y2": 1190, "w": 1800, "h": 1250}
CUT_BOX = {"x1": 100, "y1": 100, "x2": 1700, "y2": 1250, "w": 1800, "h": 1250}

# ---------------------------------------------------- stub infrastructure ---

SCRIPT = []  # type: List[Any]  # queued (tool_name, args) for agent.chat
READS = []  # type: List[Dict[str, Any]]  # queued read_document payloads


def _no_client():
    # type: () -> Any
    raise AssertionError("offline test must not build a network client")


def _tool_msg(name, args):
    # type: (str, Dict[str, Any]) -> Any
    fn = SimpleNamespace(name=name, arguments=json.dumps(args))
    return SimpleNamespace(content="", tool_calls=[
        SimpleNamespace(function=fn)])


def fake_chat(prompt, image_path=None, tools=None, system=None, images=None):
    # type: (str, Optional[str], Optional[list], Optional[str], Optional[List[str]]) -> Any
    """Stand-in for agent.chat: pop one scripted tool call per agent turn.

    Plain translation calls (no tools) get a deterministic "HINDI: ..."
    reply so ask_applicant and the plan translator keep working offline.
    """
    if tools:
        if not SCRIPT:
            raise AssertionError(
                "agent asked for a tool call with an empty script; "
                "prompt starts: %r" % (prompt[:120],))
        name, args = SCRIPT.pop(0)
        return _tool_msg(name, args)
    text = prompt.split("\n\n")[-1] if "\n\n" in prompt else prompt
    return SimpleNamespace(content="HINDI: " + text, tool_calls=None)


def fake_chat_json(prompt, image_path=None, system=None):
    # type: (str, Optional[str], Optional[str]) -> Any
    """Stand-in for tools/pipeline chat_json: payload depends on the caller."""
    if system == tools.READ_SYSTEM:
        if not READS:
            raise AssertionError("read_document called with no queued read")
        return dict(READS.pop(0))
    if system == pipeline.PROFILE_SYSTEM:
        return dict(PROFILE_DATA)
    if system == web.EXTRACT_SYSTEM:
        return {"facts": [dict(QUOTED_FACT), dict(INVENTED_FACT)]}
    if system == pipeline.PLAN_SYSTEM:
        return json.loads(json.dumps(PLAN_DATA))
    raise AssertionError("unexpected chat_json system: %r" % (system,))


def fake_segment(image_path, prompt):
    # type: (str, str) -> List[Dict[str, int]]
    """Stand-in for tools/pipeline segment: fixed boxes per photo name."""
    base = os.path.basename(image_path or "")
    if "retake" in base:
        return [dict(GOOD_BOX)]
    if "cutoff" in base:
        return [dict(CUT_BOX)]
    return [dict(GOOD_BOX)]


def fake_search(query, max_results=5):
    # type: (str, int) -> List[Dict[str, str]]
    """Stand-in for web.search: one official hit plus one blog hit."""
    return [
        {"title": "Post-Matric Scholarship official portal",
         "url": GOV_URL, "snippet": "official scholarship portal"},
        {"title": "Scholarship tips blog", "url": BLOG_URL,
         "snippet": "unofficial tips"},
    ]


def fake_fetch(url, extra_domains=None, max_chars=8000):
    # type: (str, Optional[List[str]], int) -> Optional[Dict[str, str]]
    """Stand-in for web.fetch: canned text, but only on allowed domains."""
    if not web.allowed(url, extra_domains):
        return None
    return {"url": url, "text": PAGE_TEXT}


def install_stubs():
    # type: () -> None
    """Route every Meta/network call to the fakes above."""
    meta_client.get_client = _no_client  # type: ignore[assignment]
    meta_client.chat = fake_chat  # type: ignore[assignment]
    meta_client.chat_json = fake_chat_json  # type: ignore[assignment]
    meta_client.segment = fake_segment  # type: ignore[assignment]
    web.ddg_search = fake_search  # type: ignore[assignment]
    web.fetch_page = fake_fetch  # type: ignore[assignment]
    judge_mod.judge_fields = lambda record: []  # type: ignore[assignment]


# ------------------------------------------------------------- fixtures ---

def doc_fields(pairs):
    # type: (List[Any]) -> List[Dict[str, Any]]
    return [{"key": k, "value": v, "quote": q} for (k, v, q) in pairs]


def seed_doc(doc_id, index, doc_type, holder, pairs):
    # type: (str, int, str, Optional[str], List[Any]) -> Dict[str, Any]
    """A fully-read document, as if read_document had already run."""
    return {
        "id": doc_id, "photo": "photo%d" % index, "photo_index": index,
        "box": None, "crop": "", "doc_type": doc_type,
        "holder_name": holder, "fields": doc_fields(pairs),
        "quality": {"usable": True, "issues": [], "advice": ""},
        "unreadable": [], "sam_found": True, "cut_edges": False,
        "area_ratio": 0.8, "rejected": False,
    }


def read_payload(doc_type, holder, pairs):
    # type: (str, Optional[str], List[Any]) -> Dict[str, Any]
    """A read_document payload served from the READS queue."""
    return {
        "doc_type": doc_type, "holder_name": holder,
        "fields": doc_fields(pairs), "unreadable": [],
        "quality": {"usable": True, "issues": [], "advice": ""},
    }


ID_PAIRS = [
    ("applicant_name", NAME_OK, Q_NAME),
    ("father_name", "Suresh Patel", Q_FATHER),
    ("date_of_birth", "12/04/2002", Q_DOB),
    ("gender", "Male", Q_GENDER),
    ("aadhaar_number", GOOD_AADHAAR, Q_AADHAAR),
    ("address", "At Post Wadgaon, Nashik", Q_ADDR),
    ("pin_code", "422001", Q_PIN),
]
MARK_PAIRS = [
    ("previous_exam", "HSC", Q_EXAM),
    ("previous_marks_obtained", "650", Q_OBT),
    ("previous_marks_max", "1000", Q_MAX),
    ("previous_percentage", "65", Q_PCT),
]
INCOME_PAIRS = [
    ("category", "OBC", Q_CAT),
    ("annual_family_income", "Rs. 1,20,000", Q_INC),
]
PASS_PAIRS = [
    ("bank_account_number", "123456789012", Q_ACCT),
    ("ifsc_code", "HDFC0001234", Q_IFSC),
    ("bank_name", "HDFC Bank", Q_BANK),
]


def fill_entries(pairs, doc_id):
    # type: (List[Any], str) -> List[Dict[str, Any]]
    return [{"field_id": field_id, "value": value, "doc_id": doc_id,
             "quote": quote} for (field_id, value, quote) in pairs]


def doc_fill_entries(holder_value, holder_quote, bank_doc="d4"):
    # type: (str, str, str) -> List[Dict[str, Any]]
    """All 17 document-sourced entries (d1 id, d2 marksheet, d3 income,
    bank_doc passbook)."""
    entries = fill_entries(ID_PAIRS, "d1")
    entries += fill_entries(MARK_PAIRS, "d2")
    entries += fill_entries(INCOME_PAIRS, "d3")
    bank = fill_entries(PASS_PAIRS, bank_doc)
    bank.append({"field_id": "bank_account_holder", "value": holder_value,
                 "doc_id": bank_doc, "quote": holder_quote})
    return entries + bank


def voice_fill_entries():
    # type: () -> List[Dict[str, Any]]
    return [
        {"field_id": "mobile_number", "value": "9876543210",
         "utterance_id": "u1"},
        {"field_id": "current_course", "value": "BCom", "utterance_id": "u1"},
        {"field_id": "institution_name", "value": "Shivaji College",
         "utterance_id": "u1"},
    ]


ASK_ARGS = {
    "question_en": ("What is your mobile number, current course "
                    "and institution name?"),
    "field_ids": ["mobile_number", "current_course", "institution_name"],
}


def problem_codes(problems):
    # type: (List[Dict[str, Any]]) -> List[str]
    return [p.get("code") for p in problems]


# -------------------------------------------------------- 1. checks ---

def test_checks():
    # type: () -> None
    print("--- 1. format checks ---")
    expect(checks.valid_aadhaar(GOOD_AADHAAR),
           "Aadhaar good (%s) passes" % GOOD_AADHAAR)
    expect(not checks.valid_aadhaar(BAD_AADHAAR),
           "Aadhaar one-digit-wrong (%s) fails" % BAD_AADHAAR)
    expect(not checks.valid_aadhaar("123456789012"),
           "Aadhaar starting with 1 fails")
    expect(checks.valid_ifsc("HDFC0001234"),
           "IFSC HDFC0001234 passes")
    expect(checks.valid_ifsc("hdfc0001234"),
           "IFSC lowercase passes")
    expect(not checks.valid_ifsc("HDFCO001234"),
           "IFSC with letter O instead of zero fails")
    expect(checks.valid_mobile("9876543210"),
           "mobile 9876543210 passes")
    expect(checks.valid_mobile("+91 98765 43210"),
           "mobile with +91 passes")
    expect(not checks.valid_mobile("5123456789"),
           "mobile starting with 5 fails")
    expect(checks.valid_pin("422001"), "PIN 422001 passes")
    expect(not checks.valid_pin("042001"), "PIN starting with 0 fails")
    expect(not checks.valid_pin("42200"), "5-digit PIN fails")
    expect(checks.valid_date("12/04/2002"), "date 12/04/2002 passes")
    expect(checks.valid_date("12-04-2002"), "date 12-04-2002 passes")
    expect(not checks.valid_date("31/02/2020"), "impossible date fails")
    tomorrow = (date.today() + timedelta(days=1)).strftime("%d/%m/%Y")
    expect(not checks.valid_date(tomorrow), "future birth date fails")
    expect(checks.value_in_quote("Rs. 1,20,000",
                                 "Annual income Rs. 1,20,000 for the year"),
           "money-in-quote exact match passes")
    expect(checks.value_in_quote("1.2 lakh",
                                 "Annual income Rs. 1,20,000 for the year"),
           "money-in-quote 1.2 lakh equals Rs. 1,20,000")
    expect(not checks.value_in_quote("Rs. 2,50,000",
                                     "Annual income Rs. 1,20,000 for the year"),
           "money-in-quote different amount fails")
    expect(checks.name_similarity(NAME_OK, NAME_OK) == 1.0,
           "identical names score 1.0")
    expect(checks.name_similarity("Priya R Patil",
                                  "Priya Ramesh Patil") == 0.95,
           "initial-for-middle-name scores 0.95")
    stubborn = checks.name_similarity("Ramesh Patil", "Ramesh Patel")
    expect(stubborn == 0.9,
           "Patil/Patel scores exactly 0.9 (threshold is strict < 0.9)")
    expect(checks.name_similarity(NAME_BAD, NAME_OK) < 0.9,
           "Ramesh K Patil vs Ramesh Patel scores below 0.9")


# ---------------------------------------------------------- 2. rules ---

def blank_record(case_id):
    # type: (str) -> CaseRecord
    return CaseRecord(case_id=case_id, language="hi")


def test_rules():
    # type: () -> None
    print("--- 2. deterministic rules ---")
    rec = blank_record("offline_rule_aadhaar")
    rec.documents = [seed_doc("d1", 0, "identity_card", "Test User",
                              [("aadhaar_number", BAD_AADHAAR,
                                "Aadhaar: " + BAD_AADHAAR)])]
    rec.fields = {"aadhaar_number": {
        "value": BAD_AADHAAR,
        "source": {"type": "document", "doc_id": "d1",
                   "quote": "Aadhaar: " + BAD_AADHAAR}}}
    expect("INVALID_AADHAAR" in problem_codes(rules.check_rules(rec)),
           "rules catch INVALID_AADHAAR")

    rec = blank_record("offline_rule_voice")
    rec.utterances = [{"id": "u1", "text": "my aadhaar is 234567890124",
                       "audio": None, "question_id": None}]
    rec.fields = {"aadhaar_number": {
        "value": GOOD_AADHAAR,
        "source": {"type": "applicant", "utterance_id": "u1"}}}
    expect("NEEDS_DOCUMENT" in problem_codes(rules.check_rules(rec)),
           "rules catch NEEDS_DOCUMENT for speech-filled Aadhaar")

    rec = blank_record("offline_rule_source")
    rec.fields = {"category": {
        "value": "OBC",
        "source": {"type": "document", "doc_id": "d99",
                   "quote": "Category: OBC"}}}
    expect("BAD_SOURCE" in problem_codes(rules.check_rules(rec)),
           "rules catch BAD_SOURCE for an unknown document")

    rec = blank_record("offline_rule_missing")
    expect("MISSING_FIELD" in problem_codes(rules.check_rules(rec)),
           "rules catch MISSING_FIELD on an empty case")

    rec = blank_record("offline_rule_elig")
    expect("ELIGIBILITY_NOT_CHECKED"
           in problem_codes(rules.check_rules(rec)),
           "rules catch ELIGIBILITY_NOT_CHECKED before the check runs")


# --------------------------------------------------------- 3. case_a ---

def case_a_documents():
    # type: () -> List[Dict[str, Any]]
    """Pre-read documents: the passbook holder spells the name differently."""
    return [
        seed_doc("d1", 0, "identity_card", NAME_OK, ID_PAIRS),
        seed_doc("d2", 1, "marksheet", NAME_OK, MARK_PAIRS),
        seed_doc("d3", 2, "income_certificate", NAME_OK, INCOME_PAIRS),
        seed_doc("d4", 0, "bank_passbook", None,
                 PASS_PAIRS + [("bank_account_holder", NAME_BAD,
                                Q_HOLDER_BAD)]),
    ]


def test_case_a():
    # type: () -> None
    print("--- 3. case_a scripted form run ---")
    rec = CaseRecord(case_id="offline_a", language="hi")
    rec.documents = case_a_documents()
    SCRIPT.extend([
        ("fill_fields", {"entries": doc_fill_entries(NAME_BAD,
                                                     Q_HOLDER_BAD)}),
        ("ask_applicant", dict(ASK_ARGS)),
    ])
    history = []  # type: List[Dict[str, Any]]
    rec, history = agent.run(rec, history)
    expect(rec.status == "needs_input",
           "case_a asks the applicant and waits (needs_input)")
    expect(rec.questions and
           rec.questions[-1]["field_ids"] == ["mobile_number",
                                             "current_course",
                                             "institution_name"],
           "case_a asks one question covering the empty fields")

    rec.utterances.append({"id": "u1", "text": ANSWER_TEXT, "audio": None,
                           "question_id": rec.questions[-1]["id"]})
    rec.questions[-1]["answered"] = True
    rec.status = "open"
    SCRIPT.extend([
        ("fill_fields", {"entries": voice_fill_entries()}),
        ("check_eligibility", {}),
        ("submit_form", {}),
        ("flag_discrepancy",
         {"target": "bank_account_holder",
          "detail": ("Passbook shows Ramesh K Patil but the ID card shows "
                     "Ramesh Patel; applicant to confirm the spelling.")}),
        ("submit_form", {}),
    ])
    rec, history = agent.run(rec, history)
    expect(rec.eligibility is not None
           and rec.eligibility.get("eligible") is True,
           "case_a eligibility passes (OBC, Rs. 1,20,000, 65%)")
    refused = [p.get("code") for r in rec.refusals
               for p in r.get("problems", [])]
    expect("NAME_MISMATCH" in refused,
           "case_a first submit is refused with NAME_MISMATCH")
    expect(any(d.get("field_id") == "bank_account_holder"
               for d in rec.discrepancies),
           "case_a flags the holder-name discrepancy openly")
    expect(rec.status == "awaiting_signoff",
           "case_a reaches awaiting_signoff after flagging")
    expect(not SCRIPT, "case_a consumes the whole tool-call script")
    html = render.render_form_html(rec)
    expect("Patel" in html and GOOD_AADHAAR in html,
           "render_form contains Patel and the Aadhaar number")


# --------------------------------------------------------- 4. case_c ---

def make_photo(path, label):
    # type: (str, str) -> None
    """Generate a plain 1800x1250 JPEG; reads are stubbed, pixels unused."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (1800, 1250), "white")
    ImageDraw.Draw(img).text((80, 80), label, fill="black")
    img.save(path, "JPEG", quality=90)


def test_case_c(workdir):
    # type: (str) -> None
    print("--- 4. case_c scripted pipeline run ---")
    photos = []
    for i, name in enumerate(["p1.jpg", "p2.jpg", "p3.jpg",
                              "p4_cutoff.jpg"]):
        path = os.path.join(workdir, name)
        make_photo(path, "case_c photo %d" % (i + 1))
        photos.append(path)
    retake = os.path.join(workdir, "retake.jpg")
    make_photo(retake, "case_c passbook retake")
    READS.extend([
        read_payload("identity_card", NAME_OK, ID_PAIRS),
        read_payload("marksheet", NAME_OK, MARK_PAIRS),
        read_payload("income_certificate", NAME_OK, INCOME_PAIRS),
        read_payload("bank_passbook", None,
                     PASS_PAIRS + [("bank_account_holder", NAME_OK,
                                    Q_HOLDER_OK)]),
        read_payload("bank_passbook", NAME_OK,
                     PASS_PAIRS + [("bank_account_holder", NAME_OK,
                                    Q_HOLDER_OK)]),
    ])
    SCRIPT.extend([
        ("fill_fields", {"entries": doc_fill_entries(NAME_OK, Q_HOLDER_OK,
                                                     bank_doc="d5")}),
        ("ask_applicant", dict(ASK_ARGS)),
    ])
    rec = pipeline.start(photos, language="hi", case_id="offline_c")
    expect(rec.status == "needs_photo",
           "case_c pauses for a retake (needs_photo)")
    advice = " ".join(r.get("advice_en", "")
                      for r in rec.photo_requests)
    expect("bottom" in advice,
           "case_c coach names the cut-off bottom edge")
    expect(len(READS) == 1,
           "case_c holds the retake read back until the retake arrives")

    rec = pipeline.add_photos("offline_c", [retake])
    expect(rec.status == "needs_input",
           "case_c form asks about the voice-only fields")
    expect(not READS, "case_c consumes every queued document read")
    SCRIPT.extend([
        ("fill_fields", {"entries": voice_fill_entries()}),
        ("check_eligibility", {}),
        ("submit_form", {}),
    ])
    rec = pipeline.answer("offline_c", ANSWER_TEXT)
    expect(rec.stage == "done", "case_c pipeline runs to done")
    expect(rec.status == "awaiting_signoff",
           "case_c form passes the gate after the retake")
    expect(not SCRIPT, "case_c consumes the whole tool-call script")

    pm = (rec.research or {}).get("post_matric_scholarship") or {}
    texts = [f.get("text") for f in pm.get("facts") or []]
    expect(QUOTED_FACT["text"] in texts,
           "research keeps the quoted fact")
    expect(INVENTED_FACT["text"] not in texts,
           "research drops the invented fact without a verbatim quote")
    expect((pm.get("dropped") or 0) >= 1,
           "research counts the dropped quote")
    expect(BLOG_URL not in (pm.get("sources") or []),
           "research ignores non-government URLs")
    expect(all("gov.in" in (u or "") for u in (pm.get("sources") or [])),
           "research sources are government pages only")

    plan = rec.plan or {}
    expect((plan.get("summary_en") or "") == PLAN_SUMMARY_EN,
           "plan keeps the English summary")
    expect((plan.get("summary") or "").startswith("HINDI:"),
           "plan summary is translated")
    steps = plan.get("steps") or []
    expect(len(steps) == 1 and steps[0].get("fact_ids") == ["f1"],
           "plan strips the invented citation f999")
    expect(steps[0].get("source_urls") == ["https://scholarships.gov.in/"],
           "plan cites the government source of the kept fact")


# ------------------------------------------------------- 5. upload pack ---

def make_noisy(path, width=3000, height=2000):
    # type: (str, int, int) -> None
    """Write harsh random-noise JPEG that only fits after compression."""
    from PIL import Image
    img = Image.frombytes("RGB", (width, height),
                          os.urandom(width * height * 3))
    img.save(path, "JPEG", quality=90)


def pack_record(case_id, crop):
    # type: (str, str) -> CaseRecord
    """One cited income-certificate document for Priya Patil."""
    rec = CaseRecord(case_id=case_id, language="hi")
    rec.profile = {"name": "Priya Patil", "category": "OBC",
                   "annual_family_income": 120000}
    rec.documents = [{
        "id": "d1", "photo": crop, "photo_index": 0, "box": None,
        "crop": crop, "doc_type": "income_certificate",
        "holder_name": "Priya Patil",
        "fields": [{"key": "annual_family_income",
                    "value": "Rs. 1,20,000",
                    "quote": "Annual income Rs. 1,20,000"}],
        "quality": {"usable": True, "issues": [], "advice": ""},
        "unreadable": [], "sam_found": True, "cut_edges": False,
        "area_ratio": 0.8, "rejected": False,
    }]
    rec.fields = {
        "annual_family_income": {
            "value": "Rs. 1,20,000",
            "source": {"type": "document", "doc_id": "d1",
                       "quote": "Annual income Rs. 1,20,000"}},
        "category": {
            "value": "OBC",
            "source": {"type": "document", "doc_id": "d1",
                       "quote": "Category: OBC"}},
    }
    return rec


def test_upload_pack(workdir):
    # type: (str) -> None
    print("--- 5. upload pack ---")
    noisy = os.path.join(workdir, "noisy.jpg")
    make_noisy(noisy)
    real_check = upload_pack.readability_check
    upload_pack.readability_check = lambda path, values: True  # type: ignore[assignment]
    try:
        rec = pack_record("offline_pack", noisy)
        pack = upload_pack.make_pack(rec, "post_matric_scholarship")
        expect(len(pack) == 1, "pack builds one file for the cited document")
        r = pack[0]
        expect(r["doc_id"] == "d1" and
               r["doc_type"] == "income_certificate",
               "pack result names the document")
        expect(os.path.basename(
            r["path"]) == "Priya_Patil_income_certificate.jpg",
            "pack file is named Priya_Patil_income_certificate.jpg")
        expect(os.path.getsize(r["path"]) <= 200 * 1024,
               "noisy 3000x2000 pack output is under 200 KB")
        expect(r["px"] <= 1200,
               "pack output long side is at most 1200 px")
        expect(r["format"] in ("jpg", "pdf"),
               "pack output format is allowed")
        expect(r["checks"].get("size_ok") and
               r["checks"].get("format_ok"),
               "pack deterministic checks pass")
        expect(r["checks"].get("readable") is True,
               "stubbed Spark readability check passes")
        expect(r["rule_source"] == "default",
               "pack uses default limits without an upload_limit fact")

        pdf_upload = {"default": {"formats": ["pdf"], "max_kb": 200,
                                  "min_kb": 10, "max_px": 1200,
                                  "min_dpi_hint": 150},
                      "per_doc": {}, "source": "default"}
        pack_pdf = upload_pack.make_pack(rec, "post_matric_scholarship",
                                         upload=pdf_upload)
        expect(len(pack_pdf) == 1 and
               pack_pdf[0]["format"] == "pdf",
               "a pdf-only rule produces a PDF")
        with open(pack_pdf[0]["path"], "rb") as f:
            magic = f.read(5)
        expect(magic == b"%PDF-",
               "the pdf-only pack file is a valid PDF")
        expect(os.path.getsize(pack_pdf[0]["path"]) <= 200 * 1024,
               "the pdf-only pack file is under 200 KB")

        parsed = web.parse_upload_rule(
            "The file size should not exceed 100 KB. "
            "Only PDF format is allowed.")
        expect(parsed == {"max_kb": 100, "formats": ["pdf"]},
               "upload_limit text parses to max_kb 100 and [pdf]")

        section = upload_pack.scheme_upload_section(
            "post_matric_scholarship")
        facts = [{"id": "f9", "kind": "upload_limit",
                  "text": ("The file size should not exceed 100 KB. "
                           "Only PDF format is allowed."),
                  "quote": "should not exceed 100 KB",
                  "scheme_id": "post_matric_scholarship"}]
        rule, source = upload_pack.rule_for_doc(section, "income_certificate",
                                                facts)
        expect(rule.get("max_kb") == 100 and
               rule.get("formats") == ["pdf"] and source == "f9",
               "a verified upload_limit fact overrides the defaults")

        upload_pack.readability_check = lambda path, values: False  # type: ignore[assignment]
        rec2 = pack_record("offline_pack_no", noisy)
        pack_no = upload_pack.make_pack(rec2, "post_matric_scholarship")
        expect(pack_no[0]["checks"].get("readable")
               == "needs_manual_check",
               "a failed read check retries once, then needs_manual_check")
    finally:
        upload_pack.readability_check = real_check


# --------------------------------------------------------------- main ---

def cleanup(paths):
    # type: (List[str]) -> None
    for path in paths:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)


def main():
    # type: () -> None
    install_stubs()
    workdir = tempfile.mkdtemp(prefix="formsaathi_offline_")
    state_dirs = [os.path.join(APP, "state", name)
                  for name in ("offline_a", "offline_c", "offline_pack",
                               "offline_pack_no")]
    try:
        test_checks()
        test_rules()
        test_case_a()
        test_case_c(workdir)
        test_upload_pack(workdir)
    finally:
        cleanup(state_dirs + [workdir])
    print("ALL OFFLINE TESTS PASSED")


if __name__ == "__main__":
    main()

