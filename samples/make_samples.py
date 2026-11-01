"""Generate FICTIONAL sample documents photographed on a table. No real person's data.

    python samples/make_samples.py

Case A (eligible): identity card + bank passbook in one photo, a marksheet, and an income certificate
whose surname is misspelt ("Patel" instead of "Patil"), a real-world discrepancy the agent must flag.
Case B (not eligible): same applicant, but the family income is above the limit.
"""

import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "photos")
FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "/System/Library/Fonts/Supplemental", "/Library/Fonts"]


def font(size, bold=False):
    names = ["DejaVuSans-Bold.ttf", "Arial Bold.ttf"] if bold else ["DejaVuSans.ttf", "Arial.ttf"]
    for d in FONT_DIRS:
        for n in names:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def paper(w, h, color, lines, title, title_color=(20, 40, 90), stamp=None):
    img = Image.new("RGB", (w, h), color)
    d = ImageDraw.Draw(img)
    d.rectangle([8, 8, w - 9, h - 9], outline=(90, 90, 90), width=3)
    d.text((30, 24), title, fill=title_color, font=font(30, True))
    d.line([30, 70, w - 30, 70], fill=(120, 120, 120), width=2)
    y = 90
    for ln in lines:
        if ln == "":
            y += 14
            continue
        bold = ln.startswith("**")
        d.text((34, y), ln.strip("*"), fill=(15, 15, 15), font=font(24, bold))
        y += 38
    wm = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(wm).text((w * 0.12, h * 0.42), "SAMPLE - FICTIONAL - FOR DEMO",
                            fill=(200, 30, 30, 70), font=font(int(w / 17), True))
    img = Image.alpha_composite(img.convert("RGBA"), wm.rotate(18, center=(w / 2, h / 2)))
    if stamp:
        s = ImageDraw.Draw(img)
        x, y0 = w - 230, h - 170
        s.ellipse([x, y0, x + 170, y0 + 130], outline=(40, 60, 160, 200), width=4)
        s.text((x + 22, y0 + 50), stamp, fill=(40, 60, 160, 200), font=font(20, True))
    return img


def table(w, h, seed):
    rnd = random.Random(seed)
    base = Image.new("RGB", (w, h), (120, 82, 50))
    d = ImageDraw.Draw(base)
    for i in range(0, h, 3):
        c = 100 + rnd.randint(0, 40)
        d.line([0, i, w, i + rnd.randint(-6, 6)], fill=(c + 20, int(c * 0.7), int(c * 0.42)), width=2)
    return base.filter(ImageFilter.GaussianBlur(1.2))


def place(bg, doc, xy, angle):
    doc = doc.convert("RGBA").rotate(angle, expand=True, resample=Image.BICUBIC)
    shadow = Image.new("RGBA", doc.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 110), mask=doc.split()[3])
    shadow = shadow.filter(ImageFilter.GaussianBlur(10))
    bg.paste(shadow, (xy[0] + 14, xy[1] + 16), shadow)
    bg.paste(doc, xy, doc)


def identity_card(p):
    return paper(820, 520, (236, 242, 250), [
        f"**Name: {p['name']}",
        f"Father: {p['father']}",
        f"DOB: {p['dob']}      Gender: {p['gender']}",
        f"**Aadhaar No: {p['aadhaar']}",
        f"Address: {p['address']}",
        f"PIN: {p['pin']}",
    ], "IDENTITY CARD (Aadhaar details)")


def passbook(p):
    return paper(760, 520, (250, 246, 232), [
        "**SAMPLE GRAMEENA BANK",
        f"Branch: {p['branch']}",
        f"Account Holder: {p['holder']}",
        f"**A/c No: {p['account']}",
        f"IFSC: {p['ifsc']}",
        "Account type: Savings",
    ], "SAVINGS PASSBOOK", title_color=(10, 90, 60))


def marksheet(p):
    return paper(980, 1180, (252, 252, 246), [
        "State Board of Pre-University Examination",
        "**Statement of Marks - II PUC (Class 12)  March 2026",
        "",
        f"Candidate: {p['name'].upper()}",
        f"Father: {p['father'].upper()}",
        f"Date of Birth: {p['dob']}",
        "Register No: 2026PU118842",
        "",
        "**Subject                Max   Obtained",
        "Kannada                  100      78",
        "English                  100      71",
        "Physics                  100      74",
        "Chemistry                100      69",
        "Mathematics              100      82",
        "Biology                  100      78",
        "",
        f"**Grand Total: {p['marks']} / {p['marks_max']}",
        f"**Percentage: {p['pct']}%",
        "Result: PASSED - FIRST CLASS",
    ], "MARKS CARD", stamp="BOARD SEAL")


def income_cert(p):
    return paper(980, 1080, (247, 250, 244), [
        "Office of the Tahsildar, Hosapete Taluk",
        "**Income and Caste Certificate",
        "Certificate No: RD-INC-2026-004417",
        "",
        f"This is to certify that {p['cert_name']},",
        f"D/o {p['cert_father']}, resident of",
        f"{p['address']}, PIN {p['pin']},",
        f"belongs to the {p['category']} category.",
        "",
        f"**Annual family income from all sources: Rs. {p['income']}",
        "",
        "Valid for: Education / Scholarship purposes",
        "Date of issue: 12/06/2026",
    ], "GOVERNMENT CERTIFICATE (SAMPLE)", stamp="TAHSILDAR")


BASE = {
    "name": "Priya Ramesh Patil", "father": "Ramesh Patil", "dob": "14/08/2007", "gender": "Female",
    "aadhaar": "9999 0000 1231", "address": "H.No 12, Ward 3, Shivaji Nagar, Hosapete, Karnataka",
    "pin": "583201", "branch": "Hosapete Main", "holder": "PRIYA R PATIL", "account": "30412345678",
    "ifsc": "SMPL0001234", "marks": "452", "marks_max": "600", "pct": "75.33",
    "cert_name": "Priya Ramesh Patel", "cert_father": "Ramesh Patel", "category": "OBC", "income": "1,20,000",
}


def make_case(prefix, p, seed):
    os.makedirs(OUT, exist_ok=True)
    bg = table(1800, 1250, seed)
    place(bg, identity_card(p), (70, 120), 4)
    place(bg, passbook(p), (960, 420), -6)
    bg.convert("RGB").save(os.path.join(OUT, f"{prefix}_1_id_and_passbook.jpg"), quality=88)
    bg = table(1400, 1500, seed + 1)
    place(bg, marksheet(p), (180, 120), -3)
    bg.convert("RGB").save(os.path.join(OUT, f"{prefix}_2_marksheet.jpg"), quality=88)
    bg = table(1400, 1400, seed + 2)
    place(bg, income_cert(p), (170, 130), 2)
    bg.convert("RGB").save(os.path.join(OUT, f"{prefix}_3_income_certificate.jpg"), quality=88)


if __name__ == "__main__":
    make_case("case_a", BASE, 7)
    make_case("case_b", dict(BASE, income="3,10,000", cert_name="Priya Ramesh Patil", cert_father="Ramesh Patil"), 11)
    print("wrote", sorted(os.listdir(OUT)))
