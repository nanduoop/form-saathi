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


# Task 3: case record, tools and the form agent loop

## app/forms/post_matric_scholarship.json
Demo form (note that limits are illustrative). eligibility: categories SC/ST/OBC, max_annual_income 250000, min_previous_percentage 50.
Fields (id, label, doc_types allowed as proof, voice_ok, check): applicant_name [identity_card, marksheet] no; father_name [identity_card, income_certificate, marksheet] yes; date_of_birth [identity_card, marksheet] no, date; gender [identity_card] yes, gender; aadhaar_number [identity_card] no, aadhaar; address [identity_card, income_certificate] yes; pin_code same, pin; mobile_number [] yes, mobile; category [income_certificate, caste_certificate] no, category; annual_family_income [income_certificate] no, income; previous_exam [marksheet] no; previous_marks_obtained no, int; previous_marks_max no, int; previous_percentage no, percentage; current_course [] yes; institution_name [] yes; bank_account_holder [bank_passbook] no; bank_account_number [bank_passbook] no, account; ifsc_code [bank_passbook] no, ifsc; bank_name [bank_passbook] no. name_fields: applicant_name, bank_account_holder.

## app/case_record.py — CaseRecord (JSON-serialisable via to_dict/from_dict)
photos, scanned_photos, documents [{id d1.., photo, photo_index, box, crop, doc_type, holder_name, fields:[{key,value,quote}], quality, unreadable, sam_found, cut_edges, area_ratio, rejected}], utterances [{id u1.., text, audio, question_id}], questions [{id q1.., field_ids, question_en, question_local, answered}], fields {field_id: {value, source:{type:"document", doc_id, quote} | {type:"applicant", utterance_id}}}, discrepancies [{id, field_id (a field id or "doc:<id>"), detail}], eligibility, status, refusals, language (hi/kn/mr/te/ta/bn/en), plus pipeline fields stage, log, profile, schemes, research, plan, photo_requests.

## app/tools.py — tool functions (record, ...) -> dict, plus TOOLS (OpenAI tool schemas) and DISPATCH
- find_documents: for each unscanned photo, try SAM prompts document/paper/card until boxes are found; drop boxes < 3% of the image, dedupe IoU > 0.6; crop with 3% padding to state/<case>/crops/dN.jpg; if SAM finds nothing use the whole photo. Store sam_found, cut_edges (raw box within 0.6% of a frame edge) and area_ratio.
- read_document(doc_id): Spark reads the crop; returns doc_type (identity_card, marksheet, income_certificate, caste_certificate, bank_passbook, land_record, crop_field_photo, other), holder_name, fields with VERBATIM quotes, unreadable labels, and quality {usable, issues, advice}.
- fill_fields(entries): each entry = field_id + value + (doc_id + quote) OR utterance_id. Reject speech for fields with voice_ok false. Return per-entry warnings from the format checks, plus still_empty.
- clear_field, check_eligibility (deterministic from the form's rules; stores checked_values), ask_applicant(question_en, field_ids) (Spark translates to the applicant's language; status needs_input), flag_discrepancy(target, detail), declare_ineligible(reason) (only after a failed eligibility check; translated), submit_form (runs the verification gate from Task 4).

## app/agent.py — plan/act/observe loop
System prompt from app/playbook.md (write it: find docs, read each, fill everything provable with quotes in ONE fill_fields call, ask the applicant ONE question for the rest, check eligibility, flag discrepancies instead of hiding them, submit, fix every refusal). Each turn: send the case summary (form spec, documents excluding rejected ones, filled fields, empty fields, questions, utterances, discrepancies, eligibility) + the last 12 turns; one tool per turn; save state JSON atomically every turn to app/state/<case_id>.json; stop on needs_input / awaiting_signoff / escalated / ineligible; max 40 turns. Functions: run(record, history, turn, max_turns), save, load, state_path.

Acceptance: an offline test (Task 7) can script tool calls through run(); a live `python app/run_agent.py` comes later.


Do this task now in the current workspace. Then run its Acceptance commands, fix until they pass, and commit locally with message 'Task 3: case record, tools and form agent (built with Muse Code)'. Finish with a short report of files created and the acceptance output.
