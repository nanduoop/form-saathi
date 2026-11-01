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


# Task 1: Meta client + live smoke test

Create `app/meta_client.py` with:
- `chat(prompt, image_path=None, tools=None, system=None, images=None)` returning the response message (tools => tool_choice="auto").
- `parse_json(text)` tolerant of ```json fences and text around one JSON object; `chat_json(prompt, image_path=None, system=None)`.
- `segment(image_path, prompt)` -> list of box dicts {x1,y1,x2,y2,w,h} (ints), using SAM 3.1 as described in 00_ground_rules.
- `transcribe(audio_path, language=None)` -> text.
- Model ids overridable by env vars CHAT_MODEL, SEGMENT_MODEL, VOICE_MODEL.

Create `app/smoke_test.py` that prints OK/FAIL with timing for: listing models, a one-word chat, a vision read of the Aadhaar number from samples/photos/case_a_1_id_and_passbook.jpg (skip if missing), SAM with "document" on that photo (skip if missing; print SKIP, not OK), and transcription if samples/answer_hi.m4a exists. Never print the key.

Create requirements.txt with the allowed dependencies.

Acceptance: `python app/smoke_test.py` shows OK for list models and chat.


Do this task now in the current workspace. Then run its Acceptance commands, fix until they pass, and commit locally with message 'Task 1: Meta client + live smoke test (built with Muse Code)'. Finish with a short report of files created and the acceptance output.
