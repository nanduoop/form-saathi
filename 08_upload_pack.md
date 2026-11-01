# Task 8: upload-ready document pack (resize and compress for the portal)

Government portals reject uploads that are too large, the wrong format or the wrong size. Applicants then give up or pay a cyber café. FormSaathi makes every proven document upload-ready.

## Upload rules
- Add an "upload" section to each scheme in app/schemes/catalog.json and to app/forms/post_matric_scholarship.json:
  {"default": {"formats": ["jpg", "pdf"], "max_kb": 200, "min_kb": 10, "max_px": 1200, "min_dpi_hint": 150},
   "per_doc": {"identity_card": {...optional overrides...}}}
  These are DEMO defaults. Mark them "source": "default".
- Web researcher (Task 5): add fact kind "upload_limit" to the extraction prompt (for example "file size should not exceed 200 KB", "only PDF/JPG"). If a verified upload_limit fact exists for the scheme, parse max_kb and formats from its text (simple regex: number + KB/MB, the words pdf/jpg/jpeg/png). Use those instead of the defaults, with "source": <fact id>.

## app/upload_pack.py: make_pack(record, scheme_id) -> list of results
For every non-rejected document that is cited by a filled field (or by the profile):
1. Start from the SAM crop (already tight around the document). Straighten small tilts: estimate the skew from the SAM box versus the content, or skip if unsure. Never rotate more than 10 degrees. Convert to RGB and remove EXIF.
2. Resize so the long side is <= max_px (keep the aspect ratio, LANCZOS).
3. Compress: binary-search the JPEG quality between 35 and 92 until the size is <= max_kb. If quality 35 is still too big, shrink by 0.85 and retry. If it is under min_kb, raise the quality.
4. If "pdf" is required, save a single-page PDF with Pillow (img.save(path, "PDF", resolution=150)) and check its size the same way.
5. Name files for humans: <applicant>_<doc_type>.jpg or .pdf, for example Priya_Patil_income_certificate.jpg.
6. Verify each output deterministically: format is allowed, min_kb <= size <= max_kb, long side <= max_px. Then run ONE independent Spark check per file: "Is every value we filled from this document still clearly readable in this compressed image?" Give it the list of field values. If it says no, raise the quality / max_px within limits and retry once. Otherwise mark it "needs_manual_check".
Return [{doc_id, doc_type, path, format, kb, px, rule_source, checks: {size_ok, format_ok, readable}}].

## Pipeline + UI
- Pipeline: after the form agent reaches awaiting_signoff (and before the planner), run make_pack for the eligible scheme with a form. Log "Upload pack: 4 files ready, all under 200 KB, still readable." The planner may say "upload the files from your pack" in the steps.
- Server: GET /cases/{id}/pack lists the files; GET /cases/{id}/pack/{name} downloads one; GET /cases/{id}/pack.zip downloads all (zipfile from the standard library).
- UI: an "Upload pack" card with each file's thumbnail, format, size (e.g. "184 KB, under the 200 KB limit"), its rule source (default or a link to the official fact), a readable tick, and a "Download all" button.
- CLI: run_agent.py prints the pack table at the end.

## Tests (add to tests/test_offline.py)
- Make a 3000x2000 noisy test image. Pack it with max_kb 200 and max_px 1200: the output is <= 200 KB and <= 1200 px, and the format is allowed.
- A pdf-only rule produces a valid PDF under the limit.
- Parsing "The file size should not exceed 100 KB. Only PDF format is allowed." gives max_kb 100 and formats ["pdf"].
- Stub the Spark readability check.

Acceptance: `python tests/test_offline.py` prints ALL OFFLINE TESTS PASSED. A live run of case_a then shows the pack with every file under its limit.
