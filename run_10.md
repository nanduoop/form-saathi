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


# Task 10: make it usable by a real applicant (UX review fixes)

A full live run of Sample A works, but a first-time user (or a judge) gets lost. Fix these, most important first.

1. Deadlines vs today. The planner wrote "submit before 31-10-2026" on 2 Nov 2026. Pass today's date (datetime.date.today()) to the planner and the researcher. Any deadline fact earlier than today must be labelled "closed" and the plan must say, in the applicant's language, that this window has closed and to watch for the next one / check for an extension on the official portal. Never tell the user to submit before a past date. Offline test: a deadline fact of yesterday produces a plan step marked closed, and no step says "before <that date>".
2. The question must be impossible to miss. When status is needs_input, show the "Question for you" card at the TOP of the page (directly under the case header), highlighted, and scroll it into view once (only when a new question arrives). Same for "Photo help" (needs_photo) and the Result/confirm card when awaiting_signoff.
3. Simple view first. Order the page for the applicant: status line, then question / photo help, then plan, then result + upload pack. Put Documents, Filled fields, Schemes and Agent log inside a collapsed <details> "Show proof and details" section. Collapse each document's crop image to a thumbnail (max 160 px) that expands on click.
4. Plain words, in the chosen language. Replace raw codes in the UI with plain labels: needs_input -> "We need one answer from you", awaiting_signoff -> "Ready - please check and confirm", needs_photo -> "Please retake a photo", ineligible/not_eligible -> "Not eligible", escalated -> "A helper will check this", needs_info -> "Need more info". Stage pills: Photos, Your details, Schemes, How to apply, Form, Plan, Done. Show form field labels (from the form JSON), never raw field ids. Translate the fixed UI headings and these labels for hi, kn, mr, te, ta, bn with a small static dictionary in index.html (English fallback).
5. Live progress from the first second. Write a log entry at the start of every stage and for each document as it is found/read ("Looking for documents in photo 1 of 3...", "Reading Aadhaar card..."). The UI shows the latest entry as a friendly status line under the stage pills, plus a spinner while job.state is running.
6. Filled form page (render.py): set an explicit white background and dark text (readable in dark mode), print-friendly, one compact table: Field | Value | Proof (doc name + exact quote). Crops as small thumbnails (max 120 px tall) linking to the full crop. Discrepancies in a red box at the top.
7. Portal-ready images (upload_pack.py): before resizing, crop each document tightly to the SAM box, then deskew: find the document's dominant edge angle (PIL only: e.g. threshold + find the min-area bounding rectangle of the largest bright/dark region, or test rotations between -15 and +15 degrees in 0.5 steps and pick the one that maximises horizontal-row variance), rotate to straight, and trim the remaining background/black corners. Offline test: a synthetic document rotated 8 degrees on a wood-coloured background comes out within 1 degree of straight with no black corners.
8. Hide schemes that clearly do not fit. If the profile shows a student with no farmland evidence, do not list every PM-KISAN fact: show PM-KISAN collapsed as "Probably not for you (for farmer families with land)" with the one question that would change it. Only fully show schemes that are eligible or need one fact.
9. Do not re-read documents. The form agent must reuse the intake reads stored in the case record (doc type, fields, quotes) and only call read_document for a document that has no stored read. Offline test: on case A with stored reads, read_document is called 0 times by the form agent.

Acceptance:
- python tests/test_offline.py passes, including the new tests for items 1, 7 and 9.
- Start the server, then with Python requests drive Sample A through the API (start case, poll, answer the question with a typed answer, confirm). It must reach awaiting_signoff with no past-date "submit before" in the plan.
- Load / in a headless check (fetch the HTML) and confirm the question card, plain labels and the details section exist in the markup.
Commit 'Task 10: usability fixes from live review (built with Muse Code)'.

The code from earlier tasks is in this workspace; read the relevant files first and change only what this task needs. Then run the Acceptance commands, fix until they pass, and commit locally. Finish with a short report.
