"""Plan/act/observe loop for the FormSaathi field agent.

Each turn the model sees a compact case summary plus the last 12 turns, and
makes exactly one tool call. State (record + history) is saved atomically to
app/state/<case_id>.json every turn. The loop stops on needs_input,
awaiting_signoff, escalated or ineligible, or after max_turns (default 40).

run() looks tools up through tools.DISPATCH at call time, so offline tests
can stub tool functions or meta_client.chat and script full runs.
"""
import json
import os
from typing import Any, Dict, List, Optional, Tuple

import meta_client
import tools
from case_record import CaseRecord, state_dir

HERE = os.path.dirname(os.path.abspath(__file__))

TERMINAL = ("needs_input", "awaiting_signoff", "escalated", "ineligible")

MAX_TURNS = 40
HISTORY_TAIL = 12
REMINDER = ("Reminder: reply with exactly one tool call now "
            "(no text-only reply).")


def _playbook():
    # type: () -> str
    with open(os.path.join(HERE, "playbook.md"), "r",
              encoding="utf-8") as f:
        return f.read()


def state_path(case_id):
    # type: (str) -> str
    return os.path.join(state_dir(str(case_id)), "case.json")


def save(record, history):
    # type: (CaseRecord, List[Dict[str, Any]]) -> str
    """Atomically save record + history; return the state file path."""
    path = state_path(record.case_id)
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    payload = {"record": record.to_dict(), "history": list(history)}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


def load(case_id):
    # type: (str) -> Tuple[CaseRecord, List[Dict[str, Any]]]
    """Load record + history saved by save()."""
    with open(state_path(case_id), "r", encoding="utf-8") as f:
        payload = json.load(f)
    return (CaseRecord.from_dict(payload.get("record", {})),
            list(payload.get("history", [])))


def build_summary(record):
    # type: (CaseRecord) -> str
    """Compact case summary sent to the model every turn."""
    form = tools.load_form(record.form_id)
    lines = []  # type: List[str]
    lines.append("Form: %s (%s)" %
                 (form.get("title"), form.get("form_id")))
    lines.append("Eligibility rules: %s" %
                 json.dumps(form.get("eligibility"), ensure_ascii=False))
    lines.append("Fields (id | voice_ok | check | allowed docs):")
    for f in form.get("fields", []):
        lines.append("  %s | voice=%s | check=%s | docs=%s" %
                     (f["id"], f.get("voice_ok"), f.get("check"),
                      ",".join(f.get("doc_types", []))))
    lines.append("Documents (rejected ones excluded):")
    for d in record.documents:
        if d.get("rejected"):
            continue
        lines.append("  %s photo=%s doc_type=%s holder=%s sam=%s cut=%s "
                     "area=%s unreadable=%s quality=%s fields=%s" % (
                         d.get("id"), d.get("photo_index"),
                         d.get("doc_type"), d.get("holder_name"),
                         d.get("sam_found"), d.get("cut_edges"),
                         d.get("area_ratio"),
                         json.dumps(d.get("unreadable"),
                                    ensure_ascii=False),
                         json.dumps(d.get("quality"), ensure_ascii=False),
                         json.dumps(d.get("fields"), ensure_ascii=False)))
    lines.append("Filled fields (value + source):")
    for fid, v in record.fields.items():
        lines.append("  %s = %r via %s" %
                     (fid, v.get("value"),
                      json.dumps(v.get("source"), ensure_ascii=False)))
    empty = [f["id"] for f in form.get("fields", [])
             if f["id"] not in record.fields]
    lines.append("Empty fields: %s" % ", ".join(empty))
    lines.append("Questions: %s" %
                 json.dumps(record.questions, ensure_ascii=False))
    lines.append("Utterances: %s" %
                 json.dumps(record.utterances, ensure_ascii=False))
    lines.append("Discrepancies: %s" %
                 json.dumps(record.discrepancies, ensure_ascii=False))
    lines.append("Eligibility: %s" %
                 json.dumps(record.eligibility, ensure_ascii=False))
    lines.append("Status: %s  Language: %s  Refusals: %d" %
                 (record.status, record.language, len(record.refusals)))
    return "\n".join(lines)


def _tail(history):
    # type: (List[Dict[str, Any]]) -> str
    lines = []  # type: List[str]
    for h in history[-HISTORY_TAIL:]:
        lines.append("turn %s: %s(%s) -> %s" %
                     (h.get("turn"), h.get("tool"),
                      json.dumps(h.get("args"), ensure_ascii=False),
                      json.dumps(h.get("result"), ensure_ascii=False)))
    if not lines:
        return "(no turns yet)"
    return "\n".join(lines)


def run(record, history=None, turn=0, max_turns=MAX_TURNS):
    # type: (CaseRecord, Optional[List[Dict[str, Any]]], int, int) -> Tuple[CaseRecord, List[Dict[str, Any]]]
    """Run the plan/act/observe loop; return (record, history)."""
    history = list(history or [])
    system = _playbook()
    while turn < max_turns:
        if record.status in TERMINAL:
            break
        prompt = (build_summary(record) +
                  "\n\nLast %d turns:\n%s" % (HISTORY_TAIL, _tail(history)))
        msg = meta_client.chat(prompt, tools=tools.TOOLS, system=system)
        calls = list(getattr(msg, "tool_calls", None) or [])
        if not calls:
            msg = meta_client.chat(prompt + "\n\n" + REMINDER,
                                   tools=tools.TOOLS, system=system)
            calls = list(getattr(msg, "tool_calls", None) or [])
        if not calls:
            turn += 1
            history.append({"turn": turn, "tool": None, "args": {},
                            "result": {"ok": False,
                                       "error": "no tool call returned"}})
            save(record, history)
            break
        first = calls[0]
        name = first.function.name
        try:
            args = json.loads(first.function.arguments or "{}")
        except ValueError:
            args = {}
        fn = tools.DISPATCH.get(name)
        if fn is None:
            result = {"ok": False,
                      "error": "unknown tool %r" % (name,)}  # type: Dict[str, Any]
        else:
            try:
                result = fn(record, **args)
            except TypeError as e:
                result = {"ok": False, "error": "bad tool args: %s" % (e,)}
            except Exception as e:
                result = {"ok": False,
                          "error": "%s: %s" % (type(e).__name__, e)}
        turn += 1
        history.append({"turn": turn, "tool": name, "args": args,
                        "result": result})
        save(record, history)
        if record.status in TERMINAL:
            break
    return record, history
