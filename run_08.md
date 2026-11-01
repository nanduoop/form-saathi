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


# Task 8: upload-ready document pack (resize and compress for the portal)

Government portals reject uploads that are too large, the wrong format or the wrong size. Applicants then give up or pay a cyber café. FormSaathi makes every proven document upload-ready.

## Upload rules
- Add an "upload" section to each scheme in app/schemes/catalog.json and to app/forms/post_matric_scholarship.json:
  {"default": {"formats": ["jpg", "pdf"], "max_kb": 200, "min_kb": 10, "max_px": 1200, "min_dpi_hint": 150},
   "per_doc": {"identity_card": {...optional overrides...}}}
  These are DEMO defaults. Mark them "source": "default".
- Web researcher (Task 5): add fact kind "upload_limit" to the extraction prompt (for example "file size should not exceed 200 KB", "only PDF/JPG"). If a verified upload_limit fact exists for the scheme, parse max_kb and formats from its text (simple regex: number + KB/MB, the words pdf/jpg/jpeg/png). Use those instead of the defaults, with "source": <fact id>.

## app/upload_pack.py: make_pack(record, scheme_id) -> list of results
For every non-rejected document that is cited by a filled field (or by the profile):
1. Start from the SAM crop (already tight around the document). Straighten small tilts: estimate the skew from the SAM box versus the content, or skip if unsure. Never rotate more than 10 degrees. Convert to RGB and remove EXIF.
2. Resize so the long side is <= max_px (keep the aspect ratio, LANCZOS).
3. Compress: binary-search the JPEG quality between 35 and 92 until the size is <= max_kb. If quality 35 is still too big, shrink by 0.85 and retry. If it is under min_kb, raise the quality.
4. If "pdf" is required, save a single-page PDF with Pillow (img.save(path, "PDF", resolution=150)) and check its size the same way.
5. Name files for humans: <applicant>_<doc_type>.jpg or .pdf, for example Priya_Patil_income_certificate.jpg.
6. Verify each output deterministically: format is allowed, min_kb <= size <= max_kb, long side <= max_px. Then run ONE independent Spark check per file: "Is every value we filled from this document still clearly readable in this compressed image?" Give it the list of field values. If it says no, raise the quality / max_px within limits and retry once. Otherwise mark it "needs_manual_check".
Return [{doc_id, doc_type, path, format, kb, px, rule_source, checks: {size_ok, format_ok, readable}}].

## Pipeline + UI
- Pipeline: after the form agent reaches awaiting_signoff (and before the planner), run make_pack for the eligible scheme with a form. Log "Upload pack: 4 files ready, all under 200 KB, still readable." The planner may say "upload the files from your pack" in the steps.
- Server: GET /cases/{id}/pack lists the files; GET /cases/{id}/pack/{name} downloads one; GET /cases/{id}/pack.zip downloads all (zipfile from the standard library).
- UI: an "Upload pack" card with each file's thumbnail, format, size (e.g. "184 KB, under the 200 KB limit"), its rule source (default or a link to the official fact), a readable tick, and a "Download all" button.
- CLI: run_agent.py prints the pack table at the end.

## Tests (add to tests/test_offline.py)
- Make a 3000x2000 noisy test image. Pack it with max_kb 200 and max_px 1200: the output is <= 200 KB and <= 1200 px, and the format is allowed.
- A pdf-only rule produces a valid PDF under the limit.
- Parsing "The file size should not exceed 100 KB. Only PDF format is allowed." gives max_kb 100 and formats ["pdf"].
- Stub the Spark readability check.

Acceptance: `python tests/test_offline.py` prints ALL OFFLINE TESTS PASSED. A live run of case_a then shows the pack with every file under its limit.


The existing code from Tasks 1-7 is in this workspace: read app/pipeline.py, app/web.py, app/server.py, app/static/index.html and tests/test_offline.py first and extend them; do not rewrite working parts. Then run the Acceptance commands, fix until they pass, and commit locally with message 'Task 8: upload-ready document pack (built with Muse Code)'. Finish with a short report.
