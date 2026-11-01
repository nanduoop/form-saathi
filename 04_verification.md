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
