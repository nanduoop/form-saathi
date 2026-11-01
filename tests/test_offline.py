"""Offline tests: rules, checks, and a scripted end-to-end agent run with the Meta API stubbed out.

    python tests/test_offline.py
"""

import json
import os
import shutil
import sys
import tempfile
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
sys.path.insert(0, ROOT)
os.environ.setdefault("MODEL_API_KEY", "offline-test")

import agent  # noqa: E402
import tools  # noqa: E402
from case_record import CaseRecord  # noqa: E402
from verification import judge, rules  # noqa: E402
from verification.checks import check_value, name_similarity, value_in_quote  # noqa: E402

PHOTOS = sorted(os.path.join(ROOT, "samples", "photos", n) for n in os.listdir(os.path.join(ROOT, "samples", "photos"))
                if n.startswith("case_a_"))

DOCS = {
    "identity_card": {"doc_type": "identity_card", "holder_name": "Priya Ramesh Patil", "fields": [
        {"key": "Name", "value": "Priya Ramesh Patil", "quote": "Name: Priya Ramesh Patil"},
        {"key": "Father", "value": "Ramesh Patil", "quote": "Father: Ramesh Patil"},
        {"key": "DOB", "value": "14/08/2007", "quote": "DOB: 14/08/2007"},
        {"key": "Gender", "value": "Female", "quote": "Gender: Female"},
        {"key": "Aadhaar No", "value": "9999 0000 1231", "quote": "Aadhaar No: 9999 0000 1231"},
        {"key": "Address", "value": "H.No 12, Ward 3, Shivaji Nagar, Hosapete, Karnataka",
         "quote": "Address: H.No 12, Ward 3, Shivaji Nagar, Hosapete, Karnataka"},
        {"key": "PIN", "value": "583201", "quote": "PIN: 583201"}]},
    "bank_passbook": {"doc_type": "bank_passbook", "holder_name": "PRIYA R PATIL", "fields": [
        {"key": "Bank", "value": "SAMPLE GRAMEENA BANK", "quote": "SAMPLE GRAMEENA BANK"},
        {"key": "Branch", "value": "Hosapete Main", "quote": "Branch: Hosapete Main"},
        {"key": "Account Holder", "value": "PRIYA R PATIL", "quote": "Account Holder: PRIYA R PATIL"},
        {"key": "A/c No", "value": "30412345678", "quote": "A/c No: 30412345678"},
        {"key": "IFSC", "value": "SMPL0001234", "quote": "IFSC: SMPL0001234"}]},
    "marksheet": {"doc_type": "marksheet", "holder_name": "PRIYA RAMESH PATIL", "fields": [
        {"key": "Exam", "value": "II PUC (Class 12)", "quote": "Statement of Marks - II PUC (Class 12)  March 2026"},
        {"key": "Grand Total", "value": "452 / 600", "quote": "Grand Total: 452 / 600"},
        {"key": "Percentage", "value": "75.33%", "quote": "Percentage: 75.33%"}]},
    "income_certificate": {"doc_type": "income_certificate", "holder_name": "Priya Ramesh Patel", "fields": [
        {"key": "Category", "value": "OBC", "quote": "belongs to the OBC category."},
        {"key": "Income", "value": "Rs. 1,20,000", "quote": "Annual family income from all sources: Rs. 1,20,000"}]},
}


def test_checks():
    assert check_value("aadhaar", "9999 0000 1231") is None
    assert check_value("aadhaar", "9999 0000 1281") is not None  # one misread digit
    assert check_value("ifsc", "SMPL0001234") is None and check_value("ifsc", "SMPLO001234") is not None
    assert check_value("mobile", "+91 98450 12345") is None and check_value("mobile", "12345") is not None
    assert check_value("pin", "583201") is None and check_value("pin", "083201") is not None
    assert check_value("date", "14/08/2007") is None and check_value("date", "2007-08-14") is not None
    assert value_in_quote("120000", "Annual family income: Rs. 1,20,000")
    assert not value_in_quote("1,50,000", "Annual family income: Rs. 1,20,000")
    assert name_similarity("Priya Ramesh Patil", "PRIYA R PATIL") >= 0.9
    assert name_similarity("Priya Ramesh Patil", "Priya Ramesh Patel") < 0.9
    print("checks ok")


class Script:
    """Feeds the agent a fixed sequence of tool calls, like a perfect model would."""

    def __init__(self, steps):
        self.steps = list(steps)

    def __call__(self, prompt, tools=None, system=None, **kw):
        name, args = self.steps.pop(0)
        call = SimpleNamespace(function=SimpleNamespace(name=name, arguments=json.dumps(args)))
        return SimpleNamespace(content=f"plan: {name}", tool_calls=[call])


def fake_chat_json(prompt, image_path=None, system=None):
    if "Translate" in prompt:
        return {"text": "[hi] " + prompt.split("\n\n", 1)[1]}
    if "Check each claimed value" in prompt or "faithful reading" in prompt:
        ids = [ln.split(" ")[1] for ln in prompt.splitlines() if ln.startswith("- ")]
        return {"results": [{"field_id": i, "supported": True, "reason": "visible"} for i in ids]}
    order = getattr(fake_chat_json, "order")
    return DOCS[order.pop(0)]


def run_case():
    tmp = tempfile.mkdtemp()
    agent.STATE_DIR = tmp
    tools.segment = lambda photo, prompt: (
        [{"x1": 60, "y1": 110, "x2": 930, "y2": 700}, {"x1": 950, "y1": 410, "x2": 1780, "y2": 1020}]
        if "id_and_passbook" in photo else [{"x1": 150, "y1": 100, "x2": 1250, "y2": 1300}])
    fake_chat_json.order = ["identity_card", "bank_passbook", "marksheet", "income_certificate"]
    tools.chat_json = fake_chat_json
    judge.chat_json = fake_chat_json
    q = lambda d, k: next(f["quote"] for f in DOCS[d]["fields"] if f["key"] == k)
    fill = [
        ("applicant_name", "Priya Ramesh Patil", "d1", q("identity_card", "Name")),
        ("father_name", "Ramesh Patil", "d1", q("identity_card", "Father")),
        ("date_of_birth", "14/08/2007", "d1", q("identity_card", "DOB")),
        ("gender", "Female", "d1", q("identity_card", "Gender")),
        ("aadhaar_number", "9999 0000 1231", "d1", q("identity_card", "Aadhaar No")),
        ("address", "H.No 12, Ward 3, Shivaji Nagar, Hosapete, Karnataka", "d1", q("identity_card", "Address")),
        ("pin_code", "583201", "d1", q("identity_card", "PIN")),
        ("bank_name", "SAMPLE GRAMEENA BANK", "d2", q("bank_passbook", "Bank")),
        ("bank_account_holder", "PRIYA R PATIL", "d2", q("bank_passbook", "Account Holder")),
        ("bank_account_number", "30412345678", "d2", q("bank_passbook", "A/c No")),
        ("ifsc_code", "SMPL0001234", "d2", q("bank_passbook", "IFSC")),
        ("previous_exam", "II PUC (Class 12)", "d3", q("marksheet", "Exam")),
        ("previous_marks_obtained", "452", "d3", q("marksheet", "Grand Total")),
        ("previous_marks_max", "600", "d3", q("marksheet", "Grand Total")),
        ("previous_percentage", "75.33", "d3", q("marksheet", "Percentage")),
        ("category", "OBC", "d4", q("income_certificate", "Category")),
        ("annual_family_income", "120000", "d4", q("income_certificate", "Income")),
    ]
    entries = [{"field_id": f, "value": v, "doc_id": d, "quote": qt} for f, v, d, qt in fill]
    agent.chat = Script([
        ("find_documents", {}), ("read_document", {"doc_id": "d1"}), ("read_document", {"doc_id": "d2"}),
        ("read_document", {"doc_id": "d3"}), ("read_document", {"doc_id": "d4"}),
        ("fill_fields", {"entries": entries}), ("check_eligibility", {}),
        ("ask_applicant", {"question_en": "What is your mobile number, course and college?",
                           "field_ids": ["mobile_number", "current_course", "institution_name"]}),
    ])
    rec = CaseRecord("t1", language="hi")
    for p in PHOTOS:
        rec.add_photo(p)
    out = agent.run(rec)
    assert out["status"] == "needs_input", out
    rec, hist, _, _ = agent.load("t1")
    assert len(rec.documents) == 4, rec.documents
    assert rec.eligibility["eligible"], rec.eligibility
    voice = [{"field_id": "mobile_number", "value": "9845012345", "utterance_id": "u1"},
             {"field_id": "current_course", "value": "B.Sc first year", "utterance_id": "u1"},
             {"field_id": "institution_name", "value": "Government First Grade College, Hosapete", "utterance_id": "u1"}]
    agent.chat = Script([
        ("fill_fields", {"entries": voice}),
        ("submit_form", {}),  # refused: Patil vs Patel on the income certificate
        ("flag_discrepancy", {"target": "doc:d4", "detail": "Income certificate says 'Patel', other documents say 'Patil'. Get it corrected at the taluk office."}),
        ("submit_form", {}),
    ])
    out = agent.answer("t1", "mera number nau aath chaar paanch zero ek do teen chaar paanch, B.Sc first year, Government First Grade College Hosapete")
    rec, hist, _, status = agent.load("t1")
    refused = [h for h in hist if h["act"].startswith("submit_form") and h["observe"].get("status") == "refused"]
    assert refused and refused[0]["observe"]["problems"][0]["code"] == "NAME_MISMATCH", refused
    assert status == "awaiting_signoff", hist[-1]
    from render import render_form
    with open(agent.state_path("t1")) as f:
        html = render_form(json.load(f))
    assert "Patel" in html and "9999 0000 1231" in html
    shutil.rmtree(tmp)
    print("scripted agent run ok: needs_input -> refused (NAME_MISMATCH) -> flagged -> awaiting_signoff")


def test_rules_catch_bad_values():
    rec = CaseRecord("r1")
    rec.documents = [{"id": "d1", "doc_type": "identity_card", "holder_name": "A B", "crop": None,
                      "fields": [{"key": "Aadhaar", "value": "9999 0000 1281", "quote": "Aadhaar No: 9999 0000 1281"}]}]
    rec.fields = {"aadhaar_number": {"value": "9999 0000 1281", "source": {"type": "document", "doc_id": "d1", "quote": "Aadhaar No: 9999 0000 1281"}},
                  "annual_family_income": {"value": "120000", "source": {"type": "applicant", "utterance_id": "u9"}}}
    codes = {p["code"] for p in rules.check_rules(rec)}
    for c in ("INVALID_AADHAAR", "NEEDS_DOCUMENT", "BAD_SOURCE", "MISSING_FIELD", "ELIGIBILITY_NOT_CHECKED"):
        assert c in codes, (c, codes)
    print("rules ok")


def run_pipeline_case_c():
    """Multi-agent pipeline on case C: capture coach rejects a cut-off passbook, retake, research, form, plan."""
    import pipeline
    import web
    tmp = tempfile.mkdtemp()
    agent.STATE_DIR = tmp
    W, H = 1800, 1250

    def fake_segment(photo, prompt):
        if "passbook_cut_off" in photo:
            return [{"x1": 73, "y1": 123, "x2": 923, "y2": 692, "w": W, "h": H},
                    {"x1": 985, "y1": 858, "x2": 1775, "y2": 1250, "w": W, "h": H}]
        if "retake" in photo:
            return [{"x1": 180, "y1": 180, "x2": 1000, "y2": 760, "w": 1200, "h": 1000}]
        return [{"x1": 150, "y1": 100, "x2": 1250, "y2": 1300, "w": 1400, "h": 1500}]
    tools.segment = fake_segment
    pipeline.segment = fake_segment
    fake_chat_json.order = ["identity_card", "bank_passbook", "marksheet", "income_certificate", "bank_passbook"]
    tools.chat_json = fake_chat_json
    judge.chat_json = fake_chat_json
    page = ("Post Matric Scholarship for OBC students. Apply online on the National Scholarship Portal at scholarships.gov.in. "
            "Students must upload the income certificate and caste certificate issued by the competent authority.")
    web.search = lambda q, max_results=8, offline=False: [{"title": "NSP", "url": "https://scholarships.gov.in/", "snippet": ""},
                                                          {"title": "blog", "url": "https://randomblog.com/x", "snippet": ""}]
    web.fetch = lambda url, max_chars=20000, offline=False: {"url": url, "text": page * 3}

    def fake_pipeline_json(prompt, image_path=None, system=None):
        if "Build the applicant's profile" in prompt:
            return {"name": "Priya Ramesh Patil", "gender": "Female", "date_of_birth": "14/08/2007", "state": "Karnataka",
                    "district": "Vijayanagara", "category": "OBC", "annual_family_income": "Rs. 1,20,000",
                    "education_level": "class_12", "last_exam_percentage": "75.33", "course_type": None,
                    "owns_farmland": None, "evidence": {}}
        if "extract how to apply" in prompt:
            return {"facts": [
                {"kind": "portal", "text": "Apply online on the National Scholarship Portal", "source": 0,
                 "quote": "Apply online on the National Scholarship Portal at scholarships.gov.in."},
                {"kind": "deadline", "text": "Deadline is 31 October", "source": 0, "quote": "The last date is 31 October."}]}
        if "Write an action plan" in prompt:
            return {"summary": "You qualify.", "steps": [
                {"title": "Fix surname", "detail": "Get Patel corrected to Patil", "scheme_id": None, "fact_ids": []},
                {"title": "Apply on NSP", "detail": "Upload documents", "scheme_id": "post_matric_scholarship",
                 "fact_ids": ["post_matric_scholarship#1", "made_up#9"]}]}
        return fake_chat_json(prompt, image_path, system)
    pipeline.chat_json = fake_pipeline_json

    photos = sorted(os.path.join(ROOT, "samples", "photos", n) for n in os.listdir(os.path.join(ROOT, "samples", "photos"))
                    if n.startswith("case_c_"))
    rec = CaseRecord("pc", language="hi")
    for p in photos:
        rec.add_photo(p)
    agent.save(rec, [], 0, "running")
    out = pipeline.run("pc")
    assert out["status"] == "needs_photo", out
    rec, _, _, _ = agent.load("pc")
    assert rec.photo_requests and "bottom" in rec.photo_requests[0]["advice_en"], rec.photo_requests
    assert rec.doc("d2")["rejected"]

    q = lambda d, k: next(f["quote"] for f in DOCS[d]["fields"] if f["key"] == k)
    entries = [{"field_id": f, "value": v, "doc_id": d, "quote": q(dt, k)} for f, v, d, dt, k in [
        ("applicant_name", "Priya Ramesh Patil", "d1", "identity_card", "Name"),
        ("father_name", "Ramesh Patil", "d1", "identity_card", "Father"),
        ("date_of_birth", "14/08/2007", "d1", "identity_card", "DOB"),
        ("gender", "Female", "d1", "identity_card", "Gender"),
        ("aadhaar_number", "9999 0000 1231", "d1", "identity_card", "Aadhaar No"),
        ("address", "H.No 12, Ward 3, Shivaji Nagar, Hosapete, Karnataka", "d1", "identity_card", "Address"),
        ("pin_code", "583201", "d1", "identity_card", "PIN"),
        ("previous_exam", "II PUC (Class 12)", "d3", "marksheet", "Exam"),
        ("previous_marks_obtained", "452", "d3", "marksheet", "Grand Total"),
        ("previous_marks_max", "600", "d3", "marksheet", "Grand Total"),
        ("previous_percentage", "75.33", "d3", "marksheet", "Percentage"),
        ("category", "OBC", "d4", "income_certificate", "Category"),
        ("annual_family_income", "120000", "d4", "income_certificate", "Income"),
        ("bank_name", "SAMPLE GRAMEENA BANK", "d5", "bank_passbook", "Bank"),
        ("bank_account_holder", "PRIYA R PATIL", "d5", "bank_passbook", "Account Holder"),
        ("bank_account_number", "30412345678", "d5", "bank_passbook", "A/c No"),
        ("ifsc_code", "SMPL0001234", "d5", "bank_passbook", "IFSC")]]
    agent.chat = Script([("fill_fields", {"entries": entries}), ("check_eligibility", {}),
                         ("ask_applicant", {"question_en": "Mobile, course, college?",
                                            "field_ids": ["mobile_number", "current_course", "institution_name"]})])
    retake = os.path.join(ROOT, "samples", "retakes", "case_c_passbook_retake.jpg")
    out = pipeline.add_photos("pc", [retake])
    assert out["status"] == "needs_input", out
    rec, _, _, _ = agent.load("pc")
    r = rec.research["post_matric_scholarship"]
    assert len(r["facts"]) == 1 and r["dropped"] == 1, r            # the made-up deadline is thrown out
    assert all("randomblog" not in u for u in r["sources"]), r       # non-government site never used
    assert {v["id"]: v["verdict"] for v in rec.schemes}["post_matric_scholarship"] == "eligible"
    agent.chat = Script([
        ("fill_fields", {"entries": [{"field_id": "mobile_number", "value": "9845012345", "utterance_id": "u1"},
                                     {"field_id": "current_course", "value": "B.Sc first year", "utterance_id": "u1"},
                                     {"field_id": "institution_name", "value": "GFGC Hosapete", "utterance_id": "u1"}]}),
        ("flag_discrepancy", {"target": "doc:d4", "detail": "Patel vs Patil"}),
        ("submit_form", {})])
    out = pipeline.answer("pc", "98450 12345, B.Sc first year, GFGC Hosapete")
    rec, _, _, status = agent.load("pc")
    assert status == "awaiting_signoff" and rec.stage == "done", (status, rec.stage)
    assert rec.plan["steps"][1]["fact_ids"] == ["post_matric_scholarship#1"], rec.plan   # made-up citation removed
    assert rec.plan["local"].startswith("[hi]")
    shutil.rmtree(tmp)
    print("pipeline ok: coach rejected cut-off passbook -> retake -> profile -> scout -> research (1 fact kept, 1 dropped) -> form -> plan")


if __name__ == "__main__":
    test_checks()
    test_rules_catch_bad_values()
    run_case()
    run_pipeline_case_c()
    print("ALL OFFLINE TESTS PASSED")
