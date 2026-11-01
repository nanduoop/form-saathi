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


# Task 7: offline tests + README

tests/test_offline.py (no API key): stub meta calls by monkeypatching module attributes (tools.segment, tools.chat_json, judge.chat_json, pipeline.chat_json, pipeline.segment, web.search, web.fetch, agent.chat with a scripted list of tool calls). Cover:
1. checks (Aadhaar good/one-digit-wrong, IFSC with letter O instead of zero, mobile, PIN, date, money-in-quote, name similarity Patil/Patel).
2. rules catch INVALID_AADHAAR, NEEDS_DOCUMENT, BAD_SOURCE, MISSING_FIELD, ELIGIBILITY_NOT_CHECKED.
3. case_a scripted form run: needs_input -> answer -> submit refused with NAME_MISMATCH -> flag_discrepancy -> awaiting_signoff; render_form contains "Patel" and the Aadhaar.
4. case_c pipeline: needs_photo (bottom edge) -> retake -> research keeps the quoted fact and drops the invented one, ignores non-government URLs -> form -> plan strips the invented citation and is translated.

README: problem, the agent team table (job + how each is kept honest), the verification gate, Meta models used, how to run, sample data is fictional, built with Muse Code + Meta models during the hackathon.

Acceptance: `python tests/test_offline.py` prints ALL OFFLINE TESTS PASSED.


Do this task now in the current workspace. Then run its Acceptance commands, fix until they pass, and commit locally with message 'Task 7: offline tests and README (built with Muse Code)'. Finish with a short report of files created and the acceptance output.
