"""Live check of every Meta model we use. Never prints the API key.

    python app/smoke_test.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from meta_client import CHAT_MODEL, SEGMENT_MODEL, VOICE_MODEL, chat, client, segment, transcribe  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHOTO = os.path.join(ROOT, "samples", "photos", "case_a_1_id_and_passbook.jpg")


def step(name, fn):
    t = time.time()
    try:
        out = fn()
        print(f"OK   {name} ({time.time() - t:.1f}s): {str(out)[:400]}")
    except Exception as e:
        print(f"FAIL {name} ({time.time() - t:.1f}s): {type(e).__name__}: {str(e)[:400]}")


step("list models", lambda: sorted(m.id for m in client.models.list().data))
step(f"chat {CHAT_MODEL}", lambda: chat("Reply with the single word: ready").content)
step("vision read", lambda: chat("What is the Aadhaar No printed on the left card? Reply with digits only.", image_path=PHOTO).content)
for p in ("document", "paper", "card"):
    step(f"{SEGMENT_MODEL} '{p}'", lambda p=p: segment(PHOTO, p))
audio = os.path.join(ROOT, "samples", "answer_hi.m4a")
if os.path.exists(audio):
    step(f"transcribe {VOICE_MODEL}", lambda: transcribe(audio, language="hi"))
else:
    print(f"SKIP transcribe: record a short Hindi answer to {audio} to test {VOICE_MODEL}")
