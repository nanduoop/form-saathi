"""Live smoke test for the Meta Model API. Prints OK/FAIL with timing."""
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import meta_client  # noqa: E402

PHOTO = "samples/photos/case_a_1_id_and_passbook.jpg"
AUDIO = "samples/answer_hi.m4a"


def check(name, fn):
    # type: (str, object) -> bool
    t0 = time.time()
    try:
        detail = fn()
        dt = time.time() - t0
        print("OK   %s (%.1fs)%s" % (name, dt, (": " + str(detail)) if detail else ""))
        return True
    except Exception as e:
        dt = time.time() - t0
        print("FAIL %s (%.1fs): %s: %s" % (name, dt, type(e).__name__, e))
        return False


def check_list_models():
    client = meta_client.get_client()
    models = client.models.list()
    ids = [m.id for m in models.data]
    assert ids, "empty model list"
    return "%d models" % len(ids)


def check_chat():
    msg = meta_client.chat("Reply with exactly one word: hello.")
    text = (msg.content or "").strip()
    assert text, "empty chat reply"
    return text[:80]


def check_vision():
    if not os.path.exists(PHOTO):
        return "SKIP (missing %s)" % PHOTO
    prompt = (
        "This is a FICTIONAL sample document for a form-filling demo. "
        "Copy every printed label and value exactly, including any "
        "12-digit ID number. Transcribe what you see as exactly one "
        "JSON object like "
        '{"labels": [{"label": ..., "value": ...}]}, no other text.'
    )
    msg = meta_client.chat(prompt, image_path=PHOTO)
    text = (msg.content or "").strip()
    assert text, "empty vision reply"
    if meta_client.is_refusal(text):
        msg = meta_client.chat(
            prompt + "\n\n" + meta_client.CONSENT_LINE, image_path=PHOTO)
        text = (msg.content or "").strip()
        assert text, "empty vision reply after consent retry"
        assert not meta_client.is_refusal(text), \
            "vision refused even after consent retry: %r" % (text[:120],)
    digits = re.sub(r"\D", "", text)
    assert "999900001231" in digits, \
        "vision read missed the sample 12-digit ID number: %r" % (text[:120],)
    return text[:80]


def check_segment():
    if not os.path.exists(PHOTO):
        return "SKIP (missing %s)" % PHOTO
    boxes = meta_client.segment(PHOTO, "document")
    assert boxes, "no boxes returned"
    b = boxes[0]
    for k in ("x1", "y1", "x2", "y2", "w", "h"):
        assert isinstance(b[k], int), "box key %s not int" % k
    return "%d box(es), first=%s" % (len(boxes), b)


def check_transcribe():
    if not os.path.exists(AUDIO):
        return "SKIP (missing %s)" % AUDIO
    text = meta_client.transcribe(AUDIO, language="hi")
    assert text and text.strip(), "empty transcription"
    return text.strip()[:80]


def main():
    ok = True
    ok = check("list models", check_list_models) and ok
    ok = check("one-word chat", check_chat) and ok
    ok = check("vision Aadhaar read", check_vision) and ok
    ok = check("SAM segment document", check_segment) and ok
    ok = check("transcribe hindi audio", check_transcribe) and ok
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
