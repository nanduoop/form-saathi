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


# Task 4: verification gate (the heart of the project)

## verification/checks.py (pure functions, no API)
Verhoeff validation for Aadhaar (12 digits, cannot start with 0/1); IFSC ^[A-Z]{4}0[A-Z0-9]{6}$; PIN 6 digits not starting 0; mobile 10 digits starting 6-9 (allow +91); date DD/MM/YYYY with plausible birth year; account 9-18 digits; category SC/ST/OBC/General/EWS; income parses "Rs. 1,20,000", "120000", "1.2 lakh"; int; percentage 0-100; gender.
value_in_quote(value, quote): normalised substring, or digits match, or parsed money match.
name_similarity(a, b): initials allowed ("PRIYA R PATIL" == "Priya Ramesh Patil" -> >= 0.9) but a changed letter is not ("Patil" vs "Patel" -> < 0.9); shorter name that is an ordered subset with same first and last token -> 0.95.

## verification/rules.py — check_rules(record) -> list of {code, field_id, detail}
ELIGIBILITY_NOT_CHECKED / NOT_ELIGIBLE; per field: MISSING_FIELD, BAD_SOURCE (unknown or rejected document / utterance), WRONG_DOC_TYPE, QUOTE_MISMATCH (value not in quote), QUOTE_NOT_ON_DOC (quote never read from that document), NEEDS_DOCUMENT (speech used where voice_ok is false), NO_SOURCE, INVALID_<CHECK>; PERCENT_MISMATCH (obtained/max*100 vs percentage, tolerance 0.5); NAME_MISMATCH for name_fields and for every non-rejected document's holder_name, unless a discrepancy was flagged for that field or "doc:<id>"; STALE_ELIGIBILITY when income/category changed after the check.

## verification/judge.py — judge_fields(record)
Independent Spark call per document crop: "check each claimed value against this image", JSON results per field; one text call for all speech-sourced fields comparing value with the transcript (numbers may be spoken in Hindi/Kannada words). Unsupported -> UNSUPPORTED problem.

## verification/gate.py — run_gate(record)
Rules first; only if clean, the judge. Problems -> refusals += 1 -> "refused"; at 3 refusals -> "escalated" (human helper). Clean -> "awaiting_signoff".

Acceptance: unit tests in Task 7 show a misread Aadhaar digit, speech used for income, and the Patil/Patel mismatch are all caught.


Do this task now in the current workspace. Then run its Acceptance commands, fix until they pass, and commit locally with message 'Task 4: verification gate (built with Muse Code)'. Finish with a short report of files created and the acceptance output.
