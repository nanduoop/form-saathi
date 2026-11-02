"""FormSaathi web console: FastAPI server driving the pipeline.

Run from the repo root:
  uvicorn app.server:app --reload

Every long pipeline call runs in a background thread; the UI polls
GET /cases/{id} every 1.5 s. Case ids must match ^[\\w-]{1,64}$.
"""
import datetime
import os
import random
import re
import sys
import threading
import time
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

import agent
import pipeline
import render
from case_record import CaseRecord, LANGUAGES, state_dir

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

ID_RE = re.compile(r"^[\w-]{1,64}$")

SAMPLES = {
    "case_a": [
        "samples/photos/case_a_1_id_and_passbook.jpg",
        "samples/photos/case_a_2_marksheet.jpg",
        "samples/photos/case_a_3_income_certificate.jpg",
    ],
    "case_b": [
        "samples/photos/case_b_1_id_and_passbook.jpg",
        "samples/photos/case_b_2_marksheet.jpg",
        "samples/photos/case_b_3_income_certificate.jpg",
    ],
    "case_c": [
        "samples/photos/case_c_1_passbook_cut_off.jpg",
        "samples/photos/case_c_2_marksheet.jpg",
        "samples/photos/case_c_3_income_certificate.jpg",
    ],
}

RETAKE = "samples/retakes/case_c_passbook_retake.jpg"

app = FastAPI(title="FormSaathi console")

_jobs = {}  # type: Dict[str, Dict[str, Any]]
_jobs_lock = threading.Lock()


def _check_id(case_id):
    # type: (str) -> str
    if not ID_RE.match(case_id or ""):
        raise HTTPException(status_code=400,
                            detail="bad case id (want ^[\\w-]{1,64}$)")
    return case_id


def _job_state(case_id):
    # type: (str) -> Dict[str, Any]
    with _jobs_lock:
        job = _jobs.get(case_id)
        return dict(job) if job else {"state": "idle", "error": None}


def _set_job(case_id, state, error=None):
    # type: (str, str, Optional[str]) -> None
    with _jobs_lock:
        _jobs[case_id] = {"state": state, "error": error}


def _snapshot(case_id):
    # type: (str) -> Dict[str, Any]
    _check_id(case_id)
    try:
        record, history = agent.load(case_id)
    except (OSError, ValueError, KeyError):
        raise HTTPException(status_code=404, detail="unknown case")
    data = record.to_dict()
    data["history"] = history
    data["job"] = _job_state(case_id)
    return data


def _launch(case_id, fn):
    # type: (str, Any) -> None
    _set_job(case_id, "running")

    def _run():
        try:
            fn()
        except Exception as e:
            _set_job(case_id, "error", "%s: %s" % (type(e).__name__, e))
            try:
                record, history = agent.load(case_id)
                pipeline.log_agent(record, "server",
                                   "background run failed: %s" % (e,), {})
                agent.save(record, history)
            except Exception:
                pass
        else:
            _set_job(case_id, "done")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()


def _save_uploads(case_id, uploads):
    # type: (str, List[UploadFile]) -> List[str]
    folder = os.path.join(state_dir(case_id), "uploads")
    if not os.path.isdir(folder):
        os.makedirs(folder)
    paths = []  # type: List[str]
    for up in uploads or []:
        name = os.path.basename(up.filename or "photo.jpg")
        if not name:
            name = "photo.jpg"
        dest = os.path.join(folder, "%d_%s" % (int(time.time() * 1000),
                                               name))
        with open(dest, "wb") as f:
            f.write(up.file.read())
        paths.append(dest)
    return paths


@app.get("/", response_class=HTMLResponse)
def index():
    # type: () -> FileResponse
    return FileResponse(os.path.join(HERE, "static", "index.html"))


@app.get("/samples")
def samples():
    # type: () -> Dict[str, Any]
    out = {}  # type: Dict[str, Any]
    for name, rels in SAMPLES.items():
        out[name] = {
            "photos": rels,
            "present": [os.path.exists(os.path.join(ROOT, r))
                        for r in rels],
        }
    return {"samples": out}


@app.post("/cases")
def create_case(language: str = Form("hi"),
                sample: Optional[str] = Form(None),
                photos: Optional[List[UploadFile]] = File(None)):
    # type: (...) -> JSONResponse
    if language not in LANGUAGES:
        raise HTTPException(status_code=400,
                            detail="unknown language %r" % (language,))
    paths = []  # type: List[str]
    if sample:
        if sample not in SAMPLES:
            raise HTTPException(status_code=400,
                                detail="unknown sample %r" % (sample,))
        paths = [os.path.join(ROOT, r) for r in SAMPLES[sample]]
        missing = [p for p in paths if not os.path.exists(p)]
        if missing:
            raise HTTPException(status_code=400,
                                detail="sample photo missing: %s"
                                % missing[0])
    case_id = "case_%d_%04d" % (int(time.time()),
                                random.randint(0, 9999))
    _check_id(case_id)
    if photos:
        paths = paths + _save_uploads(case_id, list(photos))
    if not paths:
        raise HTTPException(status_code=400,
                            detail="give a sample name or upload photos")
    shell = CaseRecord(case_id=case_id, language=language)
    shell.stage = "intake"
    agent.save(shell, [])
    pipeline.log_agent(shell, "server",
                       "created case with %d photo(s)" % len(paths), {})
    agent.save(shell, [])

    def _start():
        pipeline.start(paths, language=language, case_id=case_id)

    _launch(case_id, _start)
    return JSONResponse(status_code=201, content=_snapshot(case_id))


@app.get("/cases/{case_id}")
def get_case(case_id: str):
    # type: (str) -> Dict[str, Any]
    return _snapshot(case_id)


@app.get("/cases/{case_id}/crop/{doc_id}")
def get_crop(case_id: str, doc_id: str):
    # type: (str, str) -> FileResponse
    data = _snapshot(case_id)
    for d in data.get("documents") or []:
        if d.get("id") == doc_id:
            path = d.get("crop") or ""
            if path and os.path.exists(path):
                return FileResponse(path, media_type="image/jpeg")
            raise HTTPException(status_code=404, detail="crop missing")
    raise HTTPException(status_code=404, detail="unknown document")


def _pack_entries(case_id):
    # type: (str) -> List[Dict[str, Any]]
    """Pack files for a case, each with a download name and url."""
    _check_id(case_id)
    try:
        record, _history = agent.load(case_id)
    except (OSError, ValueError, KeyError):
        raise HTTPException(status_code=404, detail="unknown case")
    out = []  # type: List[Dict[str, Any]]
    for p in (getattr(record, "pack", None) or []):
        entry = dict(p)
        entry["name"] = os.path.basename(p.get("path") or "")
        entry["url"] = ("/cases/%s/pack/%s" % (case_id, entry["name"]))
        out.append(entry)
    return out


def _pack_path(case_id, name):
    # type: (str, str) -> str
    safe = os.path.basename(name or "")
    if not safe:
        raise HTTPException(status_code=404, detail="unknown file")
    for p in _pack_entries(case_id):
        if p.get("name") == safe and os.path.exists(p.get("path") or ""):
            return str(p["path"])
    raise HTTPException(status_code=404, detail="unknown file")


@app.get("/cases/{case_id}/pack")
def get_pack(case_id: str):
    # type: (str) -> Dict[str, Any]
    return {"files": _pack_entries(case_id)}


@app.get("/cases/{case_id}/pack/{name}")
def get_pack_file(case_id: str, name: str):
    # type: (str, str) -> FileResponse
    path = _pack_path(case_id, name)
    media = ("application/pdf" if path.lower().endswith(".pdf")
             else "image/jpeg")
    return FileResponse(path, media_type=media,
                        filename=os.path.basename(path))


@app.get("/cases/{case_id}/pack.zip")
def get_pack_zip(case_id: str):
    # type: (str) -> FileResponse
    import zipfile
    _check_id(case_id)
    files = [p for p in _pack_entries(case_id)
             if os.path.exists(p.get("path") or "")]
    if not files:
        raise HTTPException(status_code=404, detail="pack is empty")
    dest = os.path.join(state_dir(case_id), "pack.zip")
    with zipfile.ZipFile(dest, "w",
                         compression=zipfile.ZIP_STORED) as zf:
        for p in files:
            zf.write(str(p["path"]), arcname=str(p["name"]))
    return FileResponse(dest, media_type="application/zip",
                        filename="%s_pack.zip" % case_id)


@app.post("/cases/{case_id}/answer")
async def post_answer(case_id: str, request: Request):
    # type: (str, Request) -> Dict[str, Any]
    _check_id(case_id)
    ctype = request.headers.get("content-type", "")
    text = ""
    question_id = None  # type: Optional[str]
    audio_path = None  # type: Optional[str]
    if "application/json" in ctype:
        body = await request.json()
        text = (body or {}).get("text", "")
        question_id = (body or {}).get("question_id")
    else:
        form = await request.form()
        text = form.get("text", "") or ""
        question_id = form.get("question_id") or None
        up = form.get("audio")
        if up is not None and getattr(up, "filename", None):
            saved = _save_uploads(case_id, [up])
            if saved:
                audio_path = saved[0]
    if not text and not audio_path:
        raise HTTPException(status_code=400,
                            detail="give text or an audio file")
    try:
        agent.load(case_id)
    except (OSError, ValueError, KeyError):
        raise HTTPException(status_code=404, detail="unknown case")

    def _answer():
        pipeline.answer(case_id, text, audio_path=audio_path,
                        question_id=question_id)

    _launch(case_id, _answer)
    return {"ok": True, "job": _job_state(case_id)}


@app.post("/cases/{case_id}/photos")
async def post_photos(case_id: str, request: Request):
    # type: (str, Request) -> Dict[str, Any]
    _check_id(case_id)
    form = await request.form()
    uploads = []  # type: List[UploadFile]
    for key in form:
        for it in form.getlist(key):
            if getattr(it, "filename", None):
                uploads.append(it)
    if not uploads:
        raise HTTPException(status_code=400, detail="upload photo files")
    try:
        agent.load(case_id)
    except (OSError, ValueError, KeyError):
        raise HTTPException(status_code=404, detail="unknown case")
    paths = _save_uploads(case_id, uploads)

    def _add():
        pipeline.add_photos(case_id, paths)

    _launch(case_id, _add)
    return {"ok": True, "added": len(paths), "job": _job_state(case_id)}


@app.post("/cases/{case_id}/sample_retake")
def post_sample_retake(case_id: str):
    # type: (str) -> Dict[str, Any]
    _check_id(case_id)
    try:
        agent.load(case_id)
    except (OSError, ValueError, KeyError):
        raise HTTPException(status_code=404, detail="unknown case")
    path = os.path.join(ROOT, RETAKE)
    if not os.path.exists(path):
        raise HTTPException(status_code=400, detail="retake photo missing")

    def _add():
        pipeline.add_photos(case_id, [path])

    _launch(case_id, _add)
    return {"ok": True, "added": 1, "job": _job_state(case_id)}


@app.post("/cases/{case_id}/confirm")
def post_confirm(case_id: str):
    # type: (str) -> Dict[str, Any]
    _check_id(case_id)
    try:
        record, history = agent.load(case_id)
    except (OSError, ValueError, KeyError):
        raise HTTPException(status_code=404, detail="unknown case")
    if record.status != "awaiting_signoff":
        raise HTTPException(status_code=409,
                            detail="case is %s, not awaiting_signoff"
                            % record.status)
    record.confirmed = True
    record.confirmed_at = (datetime.datetime.utcnow()
                           .replace(microsecond=0).isoformat() + "Z")
    pipeline.log_agent(record, "server", "applicant confirmed the form", {})
    agent.save(record, history)
    return _snapshot(case_id)


@app.get("/cases/{case_id}/form", response_class=HTMLResponse)
def get_form(case_id: str):
    # type: (str) -> HTMLResponse
    _check_id(case_id)
    try:
        record, _history = agent.load(case_id)
    except (OSError, ValueError, KeyError):
        raise HTTPException(status_code=404, detail="unknown case")
    return HTMLResponse(render.render_form_html(record))
