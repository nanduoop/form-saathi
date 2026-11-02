# Ground rules for every FormSaathi task (read first)

You are building FormSaathi in this workspace: a Python 3.9 project (macOS, venv at .venv).
- NEVER open, print or commit `.env`. The key is MODEL_API_KEY, loaded with python-dotenv.
- Python 3.9 syntax only: no `match`, no `X | Y` type unions, use typing.Optional/List.
- Run scripts as `python app/x.py` from the repo root. app/ is not a package: each entry script adds app/ and the repo root to sys.path.
- Keep code small and readable. No new dependencies beyond: openai, python-dotenv, requests, fastapi, uvicorn, pillow, python-multipart.
- After writing code, RUN the acceptance commands in the task and fix until they pass. Report what you ran and the output.
- Do not `git push`. Commit locally with a clear message when the task's acceptance passes.

## Meta Model API facts (verified live on 1 Nov 2026)
- OpenAI-compatible. base_url https://api.meta.ai/v1, api_key = MODEL_API_KEY.
- Models: muse-spark-1.3 (chat, vision, tools), sam-3.1 (segmentation), muse-voice-transcribe-1.0 (speech to text), muse-image-1.0, muse-wonder-1.0.
- Chat tools: ONLY tool_choice="auto" works ("required", "none", named choice return HTTP 400). If the model returns no tool call, retry with a reminder; if it returns several, run only the first.
- Images in chat: content part {"type":"image_url","image_url":{"url":"data:image/jpeg;base64,..."}}.
- SAM 3.1: client.responses.create(model="sam-3.1", input=[{"role":"user","content":[{"type":"input_text","text":"<short noun>"},{"type":"input_image","image_url":"<data url>"}]}]).
  output_text contains entries like `<|box;x1=73;y1=123;x2=923;y2=692;w=1800;h=1250|>` (coordinates are source pixels; w,h = frame size). Parse every box with a regex.
  Works for concrete nouns: "document", "paper", "card" all return the same document boxes. Abstract words ("damage", "dent") return nothing.
- Transcription: client.audio.transcriptions.create(model="muse-voice-transcribe-1.0", file=<binary file>, language="hi").


# Task 10: engine fixes from the live review

A full live run of Sample A works. These are the engine problems it showed. (The web UI is redesigned in Task 11, so do NOT spend time on app/static/index.html here.)

1. Deadlines vs today. The planner wrote "submit before 31-10-2026" on 2 Nov 2026. Pass today's date (datetime.date.today()) to the planner and the researcher. Any deadline fact earlier than today must be marked closed, and the plan must say, in the applicant's language, that this window has closed and to watch for the next one or check for an extension on the official portal. Never tell the user to submit before a past date. Offline test: a deadline fact of yesterday produces a plan step marked closed, and no step says "before <that date>".
2. Live progress from the first second. Add a short, friendly, applicant-language progress line at the start of every stage and for each document as it is found or read (e.g. "Looking at photo 1 of 3", "Reading your Aadhaar card", "Checking which schemes fit you"). Store them in the case record as record.progress (list of {time, text_en, text}) where text is in the applicant's language (translate with one cheap Spark call per line, or a small built-in phrase table for the fixed lines; the phrase table is preferred: no extra latency). Expose them in GET /cases/{id}.
3. Plain labels in the API. Add to GET /cases/{id}: "status_label" and "stage_label" (plain words in the applicant's language, e.g. needs_input -> "We need one answer from you", awaiting_signoff -> "Ready. Please check and confirm", needs_photo -> "Please retake a photo", ineligible -> "Not eligible", escalated -> "A helper will check this"), and for each filled field its human "label" from the form JSON.
4. Filled form page (render.py): explicit white background and dark text (readable in dark mode), print-friendly, one compact table: Field | Value | Proof (document name + exact quote). Crops as small thumbnails (max 120 px tall) linking to the full crop. Discrepancies in a red box at the top.
5. Portal-ready images (upload_pack.py): before resizing, crop each document tightly to the SAM box, then deskew with PIL only (test rotations between -15 and +15 degrees in 0.5 steps and pick the one that maximises horizontal-row projection variance of the edge/threshold image), rotate to straight, and trim leftover background and black corners. Offline test: a synthetic document rotated 8 degrees on a wood-coloured background comes out within 1 degree of straight with no black corners.
6. Hide schemes that clearly do not fit. For a student profile with no farmland evidence, mark PM-KISAN (and other farmer schemes) as "unlikely" with one reason and the single question that would change it; the API lists them under "unlikely_schemes" instead of the main list.
7. Do not re-read documents. The form agent must reuse the intake reads stored in the case record and call read_document only for a document with no stored read. Offline test: on case A with stored reads, read_document is called 0 times by the form agent.
8. Goal hint. POST /cases accepts an optional "goal" form field (free text in any language, e.g. "मुझे पढ़ाई के लिए छात्रवृत्ति चाहिए" or "crop insurance"). Store it on the record; the scheme scout uses it to rank schemes (still deterministic rules for eligibility).

Acceptance:
- python tests/test_offline.py passes, including the new tests for items 1, 5 and 7.
- Start the server, then with Python requests drive Sample A through the API (start case with goal="scholarship", poll, answer the question with a typed answer, confirm). It must reach awaiting_signoff, record.progress must have entries within 5 seconds of starting, and the plan must contain no past-date "submit before".
Commit 'Task 10: engine fixes from live review (built with Muse Code)'.

The code from earlier tasks is in this workspace; read the relevant files first and change only what this task needs. Then run the Acceptance commands, fix until they pass, and commit locally. Finish with a short report.
