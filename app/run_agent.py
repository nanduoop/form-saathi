"""FormSaathi CLI: run the pipeline from a terminal.

Run from the repo root:
  python app/run_agent.py samples/photos/case_a_*.jpg --lang hi
  python app/run_agent.py --case <id> --answer "..."
  python app/run_agent.py --case <id> --photos samples/retakes/....jpg

Prints the agent log, the form-agent turns, the plan, and the next command.
"""
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pipeline  # noqa: E402


def parse_args(argv):
    # type: (list) -> dict
    opts = {"photos": [], "language": "hi", "case_id": None,
            "answer": None, "retakes": []}  # type: dict
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--lang", "--language") and i + 1 < len(argv):
            opts["language"] = argv[i + 1]
            i += 2
        elif arg in ("--case", "--case-id") and i + 1 < len(argv):
            opts["case_id"] = argv[i + 1]
            i += 2
        elif arg == "--answer" and i + 1 < len(argv):
            opts["answer"] = argv[i + 1]
            i += 2
        elif arg == "--photos":
            i += 1
            while i < len(argv) and not argv[i].startswith("--"):
                opts["retakes"].extend(glob.glob(argv[i]) or [argv[i]])
                i += 1
        elif arg.startswith("--"):
            print("unknown flag: %s" % arg)
            i += 1
        else:
            opts["photos"].extend(glob.glob(arg) or [arg])
            i += 1
    return opts


def show(record, history=None):
    # type: (object, object) -> None
    print("case=%s stage=%s status=%s" % (record.case_id, record.stage,
                                          record.status))
    print("--- agent log ---")
    for entry in getattr(record, "log", []) or []:
        if isinstance(entry, dict):
            print("[%s] %s" % (entry.get("agent", "?"),
                                entry.get("message", "")))
        else:
            print("%s" % entry)
    print("--- form-agent turns ---")
    for h in history or []:
        result = h.get("result") or {}
        summary = ""
        if isinstance(result, dict):
            summary = str(result.get("error") or
                          ("ok" if result.get("ok", True) else result))[:120]
        print("turn %s: %s -> %s" % (h.get("turn"), h.get("tool"),
                                     summary))
    if getattr(record, "photo_requests", None):
        print("--- photo requests ---")
        for req in record.photo_requests:
            print("  - %s" % req.get("advice_local", req.get("advice_en")))
    if getattr(record, "profile", None):
        print("profile: %s" % (record.profile,))
    if getattr(record, "schemes", None):
        print("--- schemes ---")
        for s in record.schemes:
            print("scheme %s: %s (%s)" % (s.get("scheme_id"),
                                          s.get("status"),
                                          "; ".join(s.get("reasons") or [])))
    questions = getattr(record, "questions", []) or []
    pending = [q for q in questions if not q.get("answered")]
    if pending:
        print("question: %s" % pending[-1].get("question_local"))
    plan = getattr(record, "plan", None)
    if plan:
        print("--- plan ---")
        print("plan: %s" % plan.get("summary"))
        for step in plan.get("steps") or []:
            print("  - %s: %s" % (step.get("title"), step.get("detail")))
            for url in step.get("source_urls") or []:
                print("    src: %s" % url)
    pack = getattr(record, "pack", None) or []
    if pack:
        print("--- upload pack ---")
        for p in pack:
            checks = p.get("checks") or {}
            tick = ("readable" if checks.get("readable") is True
                    else "needs a manual check")
            src = p.get("rule_source") or "default"
            src_txt = ("default limits" if src == "default"
                       else "official fact %s" % src)
            print("  - %s (%s, %s KB of %s KB, long side %s px) %s [%s]"
                  % (p.get("path", "").split("/")[-1], p.get("format"),
                     p.get("kb"), p.get("max_kb"), p.get("px"), tick,
                     src_txt))
        print("  download: /cases/%s/pack.zip" % record.case_id)
    print("--- next ---")
    print(next_command(record))


def next_command(record):
    # type: (object) -> str
    cid = record.case_id
    if record.status == "needs_input":
        return ('python app/run_agent.py --case %s --answer "..."' % cid)
    if record.status == "needs_photo":
        return ('python app/run_agent.py --case %s --photos <retake.jpg>'
                % cid)
    if record.status == "awaiting_signoff":
        if getattr(record, "confirmed", False):
            return "confirmed. Printable form: /cases/%s/form" % cid
        return ("review /cases/%s/form, then confirm in the web console"
                % cid)
    if record.stage != "done":
        return "pipeline paused at stage %s" % record.stage
    return "case finished."


def main(argv):
    # type: (list) -> int
    opts = parse_args(argv)
    if opts["answer"] is not None and opts["case_id"]:
        record = pipeline.answer(opts["case_id"], opts["answer"])
        record, history = pipeline.load_case(opts["case_id"])
        show(record, history)
        return 0
    if opts["retakes"] and opts["case_id"]:
        record = pipeline.add_photos(opts["case_id"], opts["retakes"])
        record, history = pipeline.load_case(opts["case_id"])
        show(record, history)
        return 0
    if opts["case_id"] and not opts["photos"]:
        try:
            record, history = pipeline.load_case(opts["case_id"])
        except (OSError, ValueError):
            print("unknown case: %s" % opts["case_id"])
            return 1
        show(record, history)
        return 0
    if not opts["photos"]:
        print("usage: python app/run_agent.py <photos...> --lang hi")
        print("       python app/run_agent.py --case ID --answer TEXT")
        print("       python app/run_agent.py --case ID --photos RETAKE...")
        return 2
    if opts["case_id"]:
        try:
            pipeline.load_case(opts["case_id"])
            record = pipeline.add_photos(opts["case_id"], opts["photos"])
        except (OSError, ValueError):
            record = pipeline.start(opts["photos"],
                                    language=opts["language"],
                                    case_id=opts["case_id"])
    else:
        record = pipeline.start(opts["photos"], language=opts["language"])
    record, history = pipeline.load_case(record.case_id)
    show(record, history)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
