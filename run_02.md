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


# Task 2: fictional sample documents

Create `samples/make_samples.py` (Pillow only) that draws FICTIONAL documents, each watermarked "SAMPLE - FICTIONAL - FOR DEMO", photographed on a wood-texture table (slight rotation + soft shadow), saved as JPEG in samples/photos/:
- Applicant: Priya Ramesh Patil, father Ramesh Patil, DOB 14/08/2007, Female, Aadhaar 9999 0000 1231 (valid Verhoeff checksum), address "H.No 12, Ward 3, Shivaji Nagar, Hosapete, Karnataka", PIN 583201.
- Documents: identity card ("IDENTITY CARD (Aadhaar details)" — no government logos), savings passbook ("SAMPLE GRAMEENA BANK", branch Hosapete Main, holder "PRIYA R PATIL", A/c 30412345678, IFSC SMPL0001234), II PUC marks card (6 subjects, Grand Total 452 / 600, Percentage 75.33%), income and caste certificate from "Office of the Tahsildar, Hosapete Taluk" (OBC, annual family income Rs. 1,20,000).
- case_a: photo 1 = identity card + passbook together; photo 2 = marksheet; photo 3 = income certificate where the name is misspelt "Priya Ramesh Patel, D/o Ramesh Patel" (a real-world discrepancy the agent must flag).
- case_b: same but income Rs. 3,10,000 and correct spelling (applicant NOT eligible).
- case_c: photo 1 where the passbook runs off the bottom edge of the frame (capture coach must ask for a retake), plus copies of the marksheet and income certificate; and samples/retakes/case_c_passbook_retake.jpg with the passbook fully in frame.
Use DejaVuSans or macOS Arial fonts (/System/Library/Fonts/Supplemental), falling back to the default font. Files: case_a_1_id_and_passbook.jpg, case_a_2_marksheet.jpg, case_a_3_income_certificate.jpg, same pattern for b, and case_c_1_passbook_cut_off.jpg.

Acceptance: `python samples/make_samples.py` writes 9 photos + 1 retake; then `python app/smoke_test.py` shows OK for the vision read (must return 999900001231) and SAM (two boxes).


Do this task now in the current workspace. Then run its Acceptance commands, fix until they pass, and commit locally with message 'Task 2: fictional sample documents (built with Muse Code)'. Finish with a short report of files created and the acceptance output.
