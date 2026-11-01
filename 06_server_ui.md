# Task 6: web console (app/server.py + app/static/index.html + app/render.py) and CLI (app/run_agent.py)

FastAPI (run: `uvicorn app.server:app --reload`): GET / ; GET /samples (case_a/b/c); POST /cases (language + sample name or uploaded photos; runs pipeline in a background thread); GET /cases/{id}; GET /cases/{id}/crop/{doc}; POST /cases/{id}/answer (text, or audio -> transcribe); POST /cases/{id}/photos; POST /cases/{id}/sample_retake; POST /cases/{id}/confirm (applicant sign-off); GET /cases/{id}/form (printable filled form: every field with its evidence crop + quote or "applicant said ...", discrepancy warnings, status banner). Validate ids with ^[\w-]{1,64}$.

Single-page UI (no framework, polls every 1.5 s): language picker; upload or sample buttons; stage tracker; agent log; scheme cards with verdicts and verified facts linking to sources; documents found by SAM with crops; filled fields with sources; question card that speaks the question (speechSynthesis, lang hi-IN/kn-IN/...) with hold-to-record (MediaRecorder) and typed fallback; capture-coach retake card; plan card (local language, read aloud, numbered steps with source links); result card with link to the filled form and "I confirm these details are true". Mobile friendly.

CLI: run_agent.py <photos> --lang hi | --case X --answer "..." | --case X --photos <retake>; prints the agent log, the form-agent turns, the plan, and the next command.

Acceptance: server starts; all three samples run in the browser.
