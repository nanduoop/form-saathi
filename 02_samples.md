# Task 2: fictional sample documents

Create `samples/make_samples.py` (Pillow only) that draws FICTIONAL documents, each watermarked "SAMPLE - FICTIONAL - FOR DEMO", photographed on a wood-texture table (slight rotation + soft shadow), saved as JPEG in samples/photos/:
- Applicant: Priya Ramesh Patil, father Ramesh Patil, DOB 14/08/2007, Female, Aadhaar 9999 0000 1231 (valid Verhoeff checksum), address "H.No 12, Ward 3, Shivaji Nagar, Hosapete, Karnataka", PIN 583201.
- Documents: identity card ("IDENTITY CARD (Aadhaar details)" — no government logos), savings passbook ("SAMPLE GRAMEENA BANK", branch Hosapete Main, holder "PRIYA R PATIL", A/c 30412345678, IFSC SMPL0001234), II PUC marks card (6 subjects, Grand Total 452 / 600, Percentage 75.33%), income and caste certificate from "Office of the Tahsildar, Hosapete Taluk" (OBC, annual family income Rs. 1,20,000).
- case_a: photo 1 = identity card + passbook together; photo 2 = marksheet; photo 3 = income certificate where the name is misspelt "Priya Ramesh Patel, D/o Ramesh Patel" (a real-world discrepancy the agent must flag).
- case_b: same but income Rs. 3,10,000 and correct spelling (applicant NOT eligible).
- case_c: photo 1 where the passbook runs off the bottom edge of the frame (capture coach must ask for a retake), plus copies of the marksheet and income certificate; and samples/retakes/case_c_passbook_retake.jpg with the passbook fully in frame.
Use DejaVuSans or macOS Arial fonts (/System/Library/Fonts/Supplemental), falling back to the default font. Files: case_a_1_id_and_passbook.jpg, case_a_2_marksheet.jpg, case_a_3_income_certificate.jpg, same pattern for b, and case_c_1_passbook_cut_off.jpg.

Acceptance: `python samples/make_samples.py` writes 9 photos + 1 retake; then `python app/smoke_test.py` shows OK for the vision read (must return 999900001231) and SAM (two boxes).
