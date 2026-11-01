"""FormSaathi web console. Run from the repo root: uvicorn app.server:app --reload"""

import json
import os
import re
import sys
import threading
import uuid
from datetime import datetime, timezone
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse  # noqa: E402

import agent  # noqa: E402
from meta_client import transcribe  # noqa: E402
from render import render_form  # noqa: E402

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(APP_DIR)
SAMPLES = os.path.join(ROOT, "samples", "photos")

app = FastAPI(title="FormSaathi")
_runs = {}
_ID = re.compile(r"^[\w-]{1,64}$")
_IMG = {".jpg", ".jpeg", ".png", ".webp"}


def _check(case_id):
    if not _ID.match(case_id or ""):
        raise HTTPException(400, "bad case id")
    return case_id


def _case_dir(case_id):
    return os.path.join(agent.STATE_DIR, case_id)


def _state(case_id):
    try:
        with open(agent.state_path(case_id)) as f:
            return json.load(f)
    except FileNotFoundError:
        raise HTTPException(404, "unknown case")


def _background(case_id, fn):
    if _runs.get(case_id, {}).get("running"):
        raise HTTPException(409, "agent is already working on this case")
    _runs[case_id] = {"running": True, "error": None}

    def go():
        try:
            fn()
        except Exception as e:  # surfaced to the UI
            _runs[case_id]["error"] = str(e)
        finally:
            _runs[case_id]["running"] = False

    threading.Thread(target=go, daemon=True).start()


def _save(case_id, upload, name):
    os.makedirs(_case_dir(case_id), exist_ok=True)
    path = os.path.join(_case_dir(case_id), name)
    with open(path, "wb") as out:
        out.write(upload.file.read())
    return path


def _save_photos(case_id, files, start=0):
    paths = []
    for i, f in enumerate(files):
        ext = os.path.splitext(f.filename or "")[1].lower()
        if ext not in _IMG:
            raise HTTPException(400, f"{f.filename}: photos only")
        paths.append(_save(case_id, f, f"photo_{start + i}{'.jpg' if ext == '.jpeg' else ext}"))
    return paths


@app.get("/")
def index():
    return FileResponse(os.path.join(APP_DIR, "static", "index.html"))


@app.get("/samples")
def samples():
    names = sorted(n for n in os.listdir(SAMPLES) if n.endswith(".jpg")) if os.path.isdir(SAMPLES) else []
    return {"cases": sorted({n.split("_")[0] + "_" + n.split("_")[1] for n in names}), "photos": names}


@app.post("/cases")
def start_case(language: str = Form("hi"), sample: str = Form(""), files: Optional[List[UploadFile]] = File(None)):
    case_id = "c" + uuid.uuid4().hex[:8]
    if sample:
        if not _ID.match(sample):
            raise HTTPException(400, "bad sample")
        photos = [os.path.join(SAMPLES, n) for n in sorted(os.listdir(SAMPLES)) if n.startswith(sample + "_")]
        if not photos:
            raise HTTPException(404, "no such sample")
    else:
        if not files:
            raise HTTPException(400, "upload at least one photo")
        photos = _save_photos(case_id, files)
    from case_record import CaseRecord
    rec = CaseRecord(case_id, language=language)
    for p in photos:
        rec.add_photo(p)
    agent.save(rec, [], 0, "running")
    _background(case_id, lambda: agent.run(rec))
    return {"case_id": case_id}


@app.get("/cases/{case_id}")
def get_case(case_id: str):
    s = _state(_check(case_id))
    info = _runs.get(case_id, {"running": False, "error": None})
    return {"running": info["running"], "error": info["error"], **s}


@app.get("/cases/{case_id}/crop/{doc_id}")
def get_crop(case_id: str, doc_id: str):
    rec = _state(_check(case_id))["record"]
    doc = next((d for d in rec["documents"] if d["id"] == doc_id), None)
    if not doc or not os.path.exists(doc["crop"]):
        raise HTTPException(404, "no crop")
    return FileResponse(doc["crop"])


@app.get("/cases/{case_id}/photo/{n}")
def get_photo(case_id: str, n: int):
    photos = _state(_check(case_id))["record"]["photos"]
    if n < 0 or n >= len(photos):
        raise HTTPException(404, "no photo")
    return FileResponse(photos[n])


@app.post("/cases/{case_id}/answer")
def answer(case_id: str, text: str = Form(""), audio: Optional[UploadFile] = File(None)):
    _check(case_id)
    s = _state(case_id)
    if s["status"] != "needs_input":
        raise HTTPException(400, f"case is {s['status']}")
    audio_path = None
    if audio is not None:
        ext = os.path.splitext(audio.filename or "")[1].lower() or ".webm"
        audio_path = _save(case_id, audio, f"answer_{len(s['record']['utterances'])}{ext}")
        try:
            text = transcribe(audio_path, language=s["record"].get("language"))
        except Exception as e:
            raise HTTPException(502, f"transcription failed: {e}. Type the answer instead.")
    if not text.strip():
        raise HTTPException(400, "empty answer")
    _background(case_id, lambda: agent.answer(case_id, text, audio_path))
    return {"status": "running", "transcript": text}


@app.post("/cases/{case_id}/photos")
def more_photos(case_id: str, files: List[UploadFile] = File(...)):
    _check(case_id)
    s = _state(case_id)
    if s["status"] not in ("needs_input", "escalated", "max_turns"):
        raise HTTPException(400, f"case is {s['status']}")
    paths = _save_photos(case_id, files, len(s["record"]["photos"]))
    _background(case_id, lambda: agent.add_photos(case_id, paths))
    return {"status": "running"}


@app.post("/cases/{case_id}/confirm")
def confirm(case_id: str):
    _check(case_id)
    rec, history, turn, status = agent.load(case_id)
    if status != "awaiting_signoff":
        raise HTTPException(400, f"case is {status}")
    rec.status = "confirmed"
    rec.confirmed_at = datetime.now(timezone.utc).isoformat()
    history.append({"turn": turn, "plan": "Applicant confirmed the details", "act": "applicant_confirm",
                    "observe": {"confirmed_at": rec.confirmed_at}})
    agent.save(rec, history, turn, "confirmed")
    return {"status": "confirmed"}


@app.get("/cases/{case_id}/form", response_class=HTMLResponse)
def form(case_id: str):
    return render_form(_state(_check(case_id)))
