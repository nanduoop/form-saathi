"""Run the full multi-agent pipeline from the terminal.

    python app/run_agent.py samples/photos/case_a_*.jpg --lang hi
    python app/run_agent.py --case c1234abcd --answer "mera number 98450 12345 hai ..."
    python app/run_agent.py --case c1234abcd --photos samples/retakes/case_c_passbook_retake.jpg
"""

import argparse
import json
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import agent  # noqa: E402
import pipeline  # noqa: E402


def report(case_id, t0):
    rec, history, _, status = agent.load(case_id)
    print("\n=== AGENTS ===")
    for l in rec.log:
        print(f"[{l['agent']}] {l['message']}")
    print("\n=== FORM AGENT TURNS ===")
    for h in history:
        print(f"[{h['turn']}] {h['plan'][:200]}\n   -> {h['act'][:250]}\n   <- {json.dumps(h['observe'], ensure_ascii=False)[:500]}")
    if rec.plan:
        print("\n=== PLAN ===\n" + rec.plan.get("local", ""))
        for i, s in enumerate(rec.plan.get("steps", []), 1):
            print(f"{i}. {s['title']}: {s['detail']} {s.get('sources', [])}")
    print(f"\nSTATUS: {status} | stage: {rec.stage} | case: {case_id} | {time.time() - t0:.0f}s")
    if status == "needs_photo":
        for r in rec.photo_requests:
            if not r.get("answered"):
                print(f"RETAKE: {r['advice_local']}\n({r['advice_en']})")
        print(f"Send with: python app/run_agent.py --case {case_id} --photos <new photo>")
    q = rec.open_question()
    if status == "needs_input" and q:
        print(f"\nQUESTION ({rec.language}): {q['question_local']}\n({q['question_en']})")
        print(f'Answer with: python app/run_agent.py --case {case_id} --answer "..."')


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("start_photos", nargs="*")
    ap.add_argument("--lang", default="hi")
    ap.add_argument("--case")
    ap.add_argument("--answer")
    ap.add_argument("--photos", nargs="*")
    a = ap.parse_args()
    t0 = time.time()
    if a.case and a.answer:
        out = pipeline.answer(a.case, a.answer)
    elif a.case and a.photos:
        out = pipeline.add_photos(a.case, a.photos)
    elif a.start_photos:
        out = pipeline.start("c" + uuid.uuid4().hex[:8], a.start_photos, a.lang)
    else:
        ap.error("give photos, or --case with --answer/--photos")
    report(out["case_id"], t0)
