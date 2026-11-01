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


# Task 6: web console (app/server.py + app/static/index.html + app/render.py) and CLI (app/run_agent.py)

FastAPI (run: `uvicorn app.server:app --reload`): GET / ; GET /samples (case_a/b/c); POST /cases (language + sample name or uploaded photos; runs pipeline in a background thread); GET /cases/{id}; GET /cases/{id}/crop/{doc}; POST /cases/{id}/answer (text, or audio -> transcribe); POST /cases/{id}/photos; POST /cases/{id}/sample_retake; POST /cases/{id}/confirm (applicant sign-off); GET /cases/{id}/form (printable filled form: every field with its evidence crop + quote or "applicant said ...", discrepancy warnings, status banner). Validate ids with ^[\w-]{1,64}$.

Single-page UI (no framework, polls every 1.5 s): language picker; upload or sample buttons; stage tracker; agent log; scheme cards with verdicts and verified facts linking to sources; documents found by SAM with crops; filled fields with sources; question card that speaks the question (speechSynthesis, lang hi-IN/kn-IN/...) with hold-to-record (MediaRecorder) and typed fallback; capture-coach retake card; plan card (local language, read aloud, numbered steps with source links); result card with link to the filled form and "I confirm these details are true". Mobile friendly.

CLI: run_agent.py <photos> --lang hi | --case X --answer "..." | --case X --photos <retake>; prints the agent log, the form-agent turns, the plan, and the next command.

Acceptance: server starts; all three samples run in the browser.


Do this task now in the current workspace. Then run its Acceptance commands, fix until they pass, and commit locally with message 'Task 6: web console and CLI (built with Muse Code)'. Finish with a short report of files created and the acceptance output.
