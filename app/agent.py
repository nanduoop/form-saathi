"""Plan / act / observe loop. One tool per turn; state saved every turn."""

import json
import os

from case_record import CaseRecord
from meta_client import chat
from tools import DISPATCH, TOOLS

APP_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(APP_DIR, "state")
PLAYBOOK_PATH = os.path.join(APP_DIR, "playbook.md")
STOP_STATUSES = ("needs_input", "awaiting_signoff", "escalated", "ineligible")


def _playbook():
    with open(PLAYBOOK_PATH) as f:
        return f.read()


def state_path(case_id):
    return os.path.join(STATE_DIR, f"{case_id}.json")


def _summary(record):
    form = record.form
    return json.dumps({
        "form": {"title": form["title"], "eligibility": form["eligibility"],
                 "fields": [{"id": f["id"], "label": f["label"], "proven_by": f["doc_types"] or ["applicant"],
                             "applicant_may_say": f["voice_ok"]} for f in form["fields"]]},
        "applicant_language": record.language,
        "photos": len(record.photos), "photos_scanned": record.scanned_photos,
        "documents": [{"id": d["id"], "doc_type": d["doc_type"], "holder_name": d["holder_name"],
                       "fields": d["fields"]} for d in record.documents if not d.get("rejected")],
        "filled": record.fields,
        "empty": [f["id"] for f in form["fields"] if f["id"] not in record.fields],
        "questions": record.questions, "utterances": [{k: u[k] for k in ("id", "text", "question_id")} for u in record.utterances],
        "discrepancies": record.discrepancies, "eligibility": record.eligibility, "refusals": record.refusals,
    }, ensure_ascii=False, indent=1)


def _history_text(history, keep=12):
    lines = []
    for t in history[-keep:]:
        obs = json.dumps(t["observe"], ensure_ascii=False)[:1500]
        lines.append(f"Turn {t['turn']}\nPLAN: {t['plan']}\nACT: {t['act']}\nOBSERVE: {obs}")
    return "\n".join(lines)


def save(record, history, turn, status):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = state_path(record.case_id) + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"case_id": record.case_id, "turn": turn, "status": status, "history": history,
                   "record": record.to_dict()}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, state_path(record.case_id))


def load(case_id):
    with open(state_path(case_id)) as f:
        d = json.load(f)
    return CaseRecord.from_dict(d["record"]), d.get("history", []), d.get("turn", 0), d.get("status")


def run(record, history=None, turn=0, max_turns=40, on_turn=None):
    history = history or []
    crop_dir = os.path.join(STATE_DIR, record.case_id, "crops")
    record.status = "running"
    status = "running"
    save(record, history, turn, status)
    while turn < max_turns:
        turn += 1
        prompt = (f"Case:\n{_summary(record)}\n\nRecent turns:\n{_history_text(history) or '(none)'}\n\n"
                  f"Turn {turn}/{max_turns}. One-line plan, then call exactly one tool.")
        if turn >= max_turns - 1:
            prompt += " You are out of turns: call submit_form now."
        msg, note = None, ""
        for _ in range(3):
            msg = chat(prompt + note, tools=TOOLS, system=_playbook())
            if msg.tool_calls:
                break
            note = "\nOBSERVATION: you must call exactly one tool."
        plan = (msg.content or "").strip()
        calls = list(msg.tool_calls or [])
        if not calls:
            act, observe = "none", {"error": "model called no tool"}
        else:
            call = calls[0]
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except Exception:
                args = {}
            act = f"{name}({json.dumps(args, ensure_ascii=False)})"
            if name not in DISPATCH:
                observe = {"error": f"unknown tool {name}; use one of {sorted(DISPATCH)}"}
            else:
                try:
                    if name == "find_documents":
                        observe = DISPATCH[name](record, crop_dir=crop_dir)
                    else:
                        observe = DISPATCH[name](record, **args)
                except TypeError as e:
                    observe = {"error": f"bad arguments for {name}: {e}"}
                except Exception as e:
                    observe = {"error": f"{name} failed: {e}"}
            if len(calls) > 1 and isinstance(observe, dict):
                observe["note"] = f"{len(calls)} tool calls returned; only the first ran."
        history.append({"turn": turn, "plan": plan, "act": act, "observe": observe})
        if on_turn:
            on_turn(turn, plan, act, observe)
        if record.status in STOP_STATUSES:
            status = record.status
            save(record, history, turn, status)
            break
        save(record, history, turn, status)
    else:
        status = "max_turns"
        record.status = status
        save(record, history, turn, status)
    return {"case_id": record.case_id, "status": status, "turn": turn}


def start(case_id, photos, language="hi", max_turns=40, on_turn=None):
    record = CaseRecord(case_id, language=language)
    for p in photos:
        record.add_photo(p)
    return run(record, max_turns=max_turns, on_turn=on_turn)


def answer(case_id, text, audio=None, max_turns=40, on_turn=None):
    record, history, turn, status = load(case_id)
    if status != "needs_input":
        raise ValueError(f"case is {status}, not waiting for an answer")
    uid = record.add_utterance(text, audio)
    history.append({"turn": turn, "plan": "Applicant answered", "act": "applicant_answer",
                    "observe": {"utterance_id": uid, "text": text}})
    return run(record, history, turn, max_turns + turn, on_turn)


def add_photos(case_id, photos, max_turns=40, on_turn=None):
    record, history, turn, status = load(case_id)
    for p in photos:
        record.add_photo(p)
    history.append({"turn": turn, "plan": "Applicant added photos", "act": "applicant_photos",
                    "observe": {"photos": len(record.photos)}})
    return run(record, history, turn, max_turns + turn, on_turn)
