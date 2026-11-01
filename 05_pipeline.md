# Task 5: the multi-agent pipeline (app/pipeline.py, app/web.py, app/schemes/catalog.json)

Stages saved in record.stage: intake -> profile -> scout -> research -> form -> plan -> done. Every agent appends {agent, message, data} to record.log (and prints it).

1. Intake + capture coach: find_documents, read every unread document. Coach each new document: reject it (doc.rejected = True) when the raw SAM box touches 1-2 frame edges (cut off), when it covers < 5% of the photo, when Spark says quality.usable is false or lists unreadable fields, or, for crop_field_photo, when SAM "plant" boxes cover < 20% of the frame. Each rejection becomes a photo_request with plain advice ("Part of the bank passbook is cut off at the bottom. Step back and keep all four corners inside the photo.") translated into the applicant's language. Status needs_photo; pipeline pauses until add_photos.
2. Profile agent: Spark builds {name, gender, date_of_birth, state, district, category, annual_family_income, education_level, last_exam_percentage, course_type, owns_farmland} from the documents only; any income/percentage/category/date value not literally present in the document text is set to null.
3. Scheme scout: deterministic rules from catalog.json (post_matric_scholarship with form_id, central_sector_scholarship, pm_vidyalaxmi, pragati_scholarship, pm_kisan; each has rules, search queries, seed_urls, extra official domains) -> eligible / not_eligible / needs_info, with reasons.
4. Web researcher (parallel per eligible/needs_info scheme): DuckDuckGo HTML search + seed URLs; ONLY fetch .gov.in / .nic.in or the scheme's listed official domains; strip HTML; cache every search and page as JSON in app/research_cache/ (env RESEARCH_OFFLINE=1 = cache only). Spark extracts facts {kind: portal|deadline|document|step|eligibility, text, source index, quote}. Keep a fact only if its quote is literally on that page (normalised match, >= 12 chars); count the dropped ones.
5. Form agent: run Task 3's loop only if the form's scheme is eligible; pause on needs_input; answer(case_id, text) resumes.
6. Planner: Spark writes {summary, steps[{title, detail, scheme_id, fact_ids}]} using ONLY verified facts (discrepancy fixes first, max 7 steps); strip fact ids that do not exist; attach source URLs; translate the whole plan into the applicant's language.
Functions: run(case_id) (resumes from record.stage), start, add_photos, answer.

Acceptance: offline scripted test of case_c (Task 7) passes; then live: `python app/run_agent.py samples/photos/case_a_*.jpg --lang hi`.
