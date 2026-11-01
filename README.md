# FormSaathi

Voice-first agent that fills Indian scholarship forms from document photos
and proves every field. An applicant photographs their documents, answers
one spoken question at a time, and gets a filled form where each value
carries its evidence: a verbatim document quote or a recorded utterance.

The problem: scholarship applications ask for exact numbers (Aadhaar,
income, marks, IFSC) copied across certificates, and a small copying slip
can cost a student the scholarship. FormSaathi never invents a value and
never hides a mismatch: anything it cannot prove becomes a question, a
photo retake, or an openly flagged discrepancy.

## The agent team

One pipeline runs six agents in order: intake, profile, scout, research,
form, plan. Each one is kept honest by a mechanism, not by prompting.

| Agent | Job | How it is kept honest |
|---|---|---|
| Intake coach | Finds documents in each photo, reads them, asks for retakes | Deterministic photo rules: cut-off edges, tiny crops, unreadable labels, unusable quality each force a retake with concrete advice |
| Profiler | Builds the applicant profile from the reads | Any profile value not literally present in the documents is reset to null |
| Scout | Matches the profile against the scheme catalog | Pure rule evaluation: eligible, not eligible, or needs info, with reasons |
| Researcher | Gathers scheme facts from official pages | Fetches government domains only; keeps a fact only with a 12+ character verbatim quote from the page |
| Form agent | Fills the form, asks questions, checks eligibility, submits | Playbook order plus the verification gate below; mismatches are flagged, never silently fixed |
| Planner | Writes the next-steps plan | May cite only verified fact ids; unknown citations are stripped; output is translated to the applicant's language |
| Spark judge | Re-checks claimed values against crops and transcripts | Runs only after the deterministic rules pass, so the model judges evidence instead of replacing the rules |

## The verification gate

`submit_form` runs `app/verification/gate.py`: deterministic rules in
`app/verification/rules.py` first (missing fields, bad or missing sources,
quotes that are not on the cited document, format checks such as
INVALID_AADHAAR, voice answers on document-only fields, percentage and
name mismatches, stale eligibility), and only when those are clean does
the Spark judge re-verify claims against the crops and transcripts.
A refusal lists every problem; three refusals escalate to a human helper.
A flagged discrepancy suppresses exactly its own mismatch so the applicant
signs off with eyes open. A clean gate leaves the case awaiting signoff,
rendered as a printable page with every value, quote, and warning.

## Meta models used

| Model | Used for |
|---|---|
| muse-spark-1.3 | Chat, document reads, profile, planning, translations, judge |
| sam-3.1 | Document segmentation (finds and crops each document) |
| muse-voice-transcribe-1.0 | Speech-to-text answers in the applicant's language |

API: OpenAI-compatible at `https://api.meta.ai/v1` with `MODEL_API_KEY`.

## How to run

Setup (Python 3.9, macOS):

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
echo 'MODEL_API_KEY=...' > .env   # never commit this file
```

Smoke-test the API, then run a case:

```
python app/smoke_test.py
python app/run_agent.py samples/photos/case_a_*.jpg --lang hi
python app/run_agent.py --case <id> --answer "..."
python app/run_agent.py --case <id> --photos samples/retakes/case_c_passbook_retake.jpg
```

Web console and offline tests:

```
uvicorn app.server:app --reload
python tests/test_offline.py   # no API key, fully stubbed
```

## Sample data

Every name, number, and document in `samples/` is fictional, drawn by
`python samples/make_samples.py` and watermarked SAMPLE - FICTIONAL -
FOR DEMO. Case A is clean, case B has a name mismatch, case C starts
with a cut-off passbook photo that needs a retake.

Built with Muse Code plus Meta models during the hackathon.
