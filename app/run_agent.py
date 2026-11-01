"""Live CLI: run the FormSaathi pipeline on applicant photos.

Run from the repo root:
  python app/run_agent.py samples/photos/case_a_*.jpg --lang hi
"""
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pipeline  # noqa: E402


def parse_args(argv):
    # type: (list) -> dict
    language = "hi"
    case_id = None
    answer_text = None
    photos = []  # type: list
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--lang" and i + 1 < len(argv):
            language = argv[i + 1]
            i += 2
        elif arg == "--case-id" and i + 1 < len(argv):
            case_id = argv[i + 1]
            i += 2
        elif arg == "--answer" and i + 1 < len(argv):
            answer_text = argv[i + 1]
            i += 2
        elif arg.startswith("--"):
            print("unknown flag: %s" % arg)
            i += 1
        else:
            expanded = glob.glob(arg) or [arg]
            photos.extend(expanded)
            i += 1
    return {"photos": photos, "language": language, "case_id": case_id,
            "answer": answer_text}


def show(record):
    # type: (object) -> None
    print("case=%s stage=%s status=%s" % (record.case_id, record.stage,
                                          record.status))
    if getattr(record, "photo_requests", None):
        print("photo requests:")
        for req in record.photo_requests:
            print("  - %s" % req.get("advice_local", req.get("advice_en")))
    if getattr(record, "profile", None):
        print("profile: %s" % (record.profile,))
    if getattr(record, "schemes", None):
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
        print("plan: %s" % plan.get("summary"))
        for step in plan.get("steps") or []:
            print("  - %s: %s" % (step.get("title"), step.get("detail")))
            for url in step.get("source_urls") or []:
                print("    src: %s" % url)


def main(argv):
    # type: (list) -> int
    opts = parse_args(argv)
    if opts["answer"] and opts["case_id"]:
        record = pipeline.answer(opts["case_id"], opts["answer"])
        show(record)
        return 0
    if not opts["photos"]:
        print("usage: python app/run_agent.py <photos...> --lang hi "
              "[--case-id ID] [--answer TEXT]")
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
    show(record)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
