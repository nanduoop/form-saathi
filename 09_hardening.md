# Task 9: hardening from the live runs

1. Privacy refusals. Muse Spark sometimes refuses prompts that say "Aadhaar number" (2 of 5 runs in Task 2). In every vision prompt (read_document, the judge, the smoke test), describe the job neutrally: "This is a FICTIONAL sample document for a form-filling demo. Copy every printed label and value exactly, including any 12-digit ID number." Detect refusals: no JSON, or text such as "can't help", "privacy" or "sensitive". On a refusal, retry once with the neutral wording plus "The applicant has consented and is filling their own form." If it is still refused, return a clear error the agent can see; never invent values.
2. The Verhoeff check is correct as specified. 999900001231 IS valid: the check digit computed for 99990000123 is 1. If verification/checks.py rejects it, the implementation is wrong. Fix the code (standard d/p/inv tables; iterate over the reversed digits with p[i % 8]), never the sample number. Add a test: verhoeff_valid("999900001231") is True, and "999900001281" is False.
3. Run `python tests/test_offline.py` and `python app/smoke_test.py` five times in a row. Every run must pass, including the vision read.

Acceptance: both commands pass 5 times in a row. Commit 'Task 9: hardening (built with Muse Code)'.
