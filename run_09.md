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


# Task 9: hardening from the live runs

1. Privacy refusals. Muse Spark sometimes refuses prompts that say "Aadhaar number" (2 of 5 runs in Task 2). In every vision prompt (read_document, the judge, the smoke test), describe the job neutrally: "This is a FICTIONAL sample document for a form-filling demo. Copy every printed label and value exactly, including any 12-digit ID number." Detect refusals: no JSON, or text such as "can't help", "privacy" or "sensitive". On a refusal, retry once with the neutral wording plus "The applicant has consented and is filling their own form." If it is still refused, return a clear error the agent can see; never invent values.
2. The Verhoeff check is correct as specified. 999900001231 IS valid: the check digit computed for 99990000123 is 1. If verification/checks.py rejects it, the implementation is wrong. Fix the code (standard d/p/inv tables; iterate over the reversed digits with p[i % 8]), never the sample number. Add a test: verhoeff_valid("999900001231") is True, and "999900001281" is False.
3. Run `python tests/test_offline.py` and `python app/smoke_test.py` five times in a row. Every run must pass, including the vision read.

Acceptance: both commands pass 5 times in a row. Commit 'Task 9: hardening (built with Muse Code)'.


The code from earlier tasks is in this workspace; read the relevant files first and change only what this task needs. Then run the Acceptance commands, fix until they pass, and commit locally. Finish with a short report.
