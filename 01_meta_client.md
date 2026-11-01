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
