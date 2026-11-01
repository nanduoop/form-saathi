# Task 7: offline tests + README

tests/test_offline.py (no API key): stub meta calls by monkeypatching module attributes (tools.segment, tools.chat_json, judge.chat_json, pipeline.chat_json, pipeline.segment, web.search, web.fetch, agent.chat with a scripted list of tool calls). Cover:
1. checks (Aadhaar good/one-digit-wrong, IFSC with letter O instead of zero, mobile, PIN, date, money-in-quote, name similarity Patil/Patel).
2. rules catch INVALID_AADHAAR, NEEDS_DOCUMENT, BAD_SOURCE, MISSING_FIELD, ELIGIBILITY_NOT_CHECKED.
3. case_a scripted form run: needs_input -> answer -> submit refused with NAME_MISMATCH -> flag_discrepancy -> awaiting_signoff; render_form contains "Patel" and the Aadhaar.
4. case_c pipeline: needs_photo (bottom edge) -> retake -> research keeps the quoted fact and drops the invented one, ignores non-government URLs -> form -> plan strips the invented citation and is translated.

README: problem, the agent team table (job + how each is kept honest), the verification gate, Meta models used, how to run, sample data is fictional, built with Muse Code + Meta models during the hackathon.

Acceptance: `python tests/test_offline.py` prints ALL OFFLINE TESTS PASSED.
