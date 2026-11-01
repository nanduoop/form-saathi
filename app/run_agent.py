"""Run a case from the terminal.

    python app/run_agent.py samples/photos/case_a_*.jpg --lang hi
    python app/run_agent.py --case c1234abcd --answer "mera number 98450 12345 hai ..."
"""

import argparse
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import agent  # noqa: E402


def show(turn, plan, act, observe):
    print(f"\n[{turn}] {plan}\n  -> {act[:300]}\n  <- {json.dumps(observe, ensure_ascii=False)[:600]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("photos", nargs="*")
    ap.add_argument("--lang", default="hi")
    ap.add_argument("--case")
    ap.add_argument("--answer")
    ap.add_argument("--max-turns", type=int, default=40)
    a = ap.parse_args()
    if a.case and a.answer:
        out = agent.answer(a.case, a.answer, max_turns=a.max_turns, on_turn=show)
    elif a.photos:
        out = agent.start("c" + uuid.uuid4().hex[:8], a.photos, a.lang, a.max_turns, on_turn=show)
    else:
        ap.error("give photos, or --case and --answer")
    print("\nRESULT:", json.dumps(out))
    rec, _, _, status = agent.load(out["case_id"])
    q = rec.open_question()
    if status == "needs_input" and q:
        print(f"\nQUESTION ({rec.language}): {q['question_local']}\n({q['question_en']})")
        print(f'Answer with: python app/run_agent.py --case {rec.case_id} --answer "..."')
