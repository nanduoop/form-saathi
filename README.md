# FormSaathi

**A voice-first agent that fills Indian government forms from photos of your documents, and proves every field.**

Many Indian families miss scholarships and benefits they qualify for, or pay a middleman to fill the form, because the forms are in English and need a dozen documents. FormSaathi lets the applicant show their documents to a phone camera and answer questions by voice in their own language (Hindi, Kannada, Marathi, Telugu, Tamil, Bengali). It returns a filled form where every value is traced to the exact document crop or the exact words that prove it.

Built for the Meta Global AI Developer Hackathon (Oct–Nov 2026).

## How it works

```
photos ──► SAM 3.1 finds and crops every document in each photo
        ──► Muse Spark reads each crop: type, holder, every printed field, verbatim
        ──► agent fills the form; each value must cite doc_id + exact quote, or the applicant's utterance
        ──► fields no document proves → ONE question, in the applicant's language, read aloud
        ──► applicant answers by voice → Muse Voice Transcribe → agent fills those fields
        ──► eligibility checked by deterministic scheme rules
        ──► submit_form ─► verification gate
                           1. hard rules: every field has evidence; value is inside the quote; Aadhaar
                              Verhoeff checksum, IFSC, PIN, mobile, date formats; percentage = marks / max;
                              the same person on every document; eligibility not stale
                           2. independent judge: a fresh Muse Spark call re-reads each document crop
                              and the transcript and confirms each value
                           refused → the agent fixes and resubmits; 3 refusals → a human helper
        ──► filled form + evidence report ──► the applicant confirms
```

The agent runs a plan → act → observe loop with one tool per turn, saving state every turn. Tools: `find_documents`, `read_document`, `fill_fields`, `clear_field`, `check_eligibility`, `ask_applicant`, `flag_discrepancy`, `declare_ineligible`, `submit_form`.

**It does not hide real-world problems.** In the sample, the income certificate spells the surname *Patel* while every other document says *Patil*. The gate refuses with `NAME_MISMATCH`, and the agent has to flag it so the applicant gets it corrected before the office rejects the application.

## Meta models used

| Model | Used for |
|---|---|
| `sam-3.1` | locating and cropping each document in a phone photo (several per photo) |
| `muse-spark-1.3` | the agent itself, reading documents, translating questions, the independent judge |
| Muse Voice Transcribe | the applicant's spoken answers in Indian languages |

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
echo "MODEL_API_KEY=..." > .env       # never commit this
python app/smoke_test.py               # checks every model live
uvicorn app.server:app --reload        # http://127.0.0.1:8000
```

Click **case a** for the eligible sample (with the name mismatch) or **case b** for an applicant whose income is above the limit. In the terminal: `python app/run_agent.py samples/photos/case_a_*.jpg --lang hi`.

Offline tests (no API key needed): `python tests/test_offline.py`

## Sample data

All documents in `samples/photos` are **fictional and generated** by `samples/make_samples.py`. No real person's data is used. The form and its eligibility limits are a demo modelled on Indian post-matric scholarship schemes, not an official form.

## License

MIT
