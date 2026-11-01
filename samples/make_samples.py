"""Draw FICTIONAL sample documents and photograph them for FormSaathi demos.

Pillow only. Run from the repo root:  python samples/make_samples.py

Writes 9 photos into samples/photos/ and 1 retake into samples/retakes/.
Every document is watermarked "SAMPLE - FICTIONAL - FOR DEMO".
"""
import math
import os
import random
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
PHOTOS = os.path.join(HERE, "photos")
RETAKES = os.path.join(HERE, "retakes")

WATERMARK = "SAMPLE - FICTIONAL - FOR DEMO"

# ---------------------------------------------------------------- fonts ---

REGULAR_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]
BOLD_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Arial Bold.ttf",
]


def load_font(size, bold=False):
    # type: (int, bool) -> ImageFont.FreeTypeFont
    cands = BOLD_CANDIDATES if bold else REGULAR_CANDIDATES
    cands = cands + REGULAR_CANDIDATES
    for path in cands:
        if path and os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def centered(draw, img_w, y, text, font, fill=(20, 20, 20)):
    # type: (ImageDraw.ImageDraw, int, int, str, ImageFont.FreeTypeFont, Tuple[int, int, int]) -> int
    w, h = draw.textsize(text, font=font) if hasattr(draw, "textsize") else (0, 0)
    try:
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        w, h = r - l, b - t
    except Exception:
        pass
    draw.text(((img_w - w) // 2, y), text, font=font, fill=fill)
    return y + h + 6


def add_watermark(doc):
    # type: (Image.Image) -> Image.Image
    """Diagonal semi-transparent watermark; light so key fields stay readable."""
    w, h = doc.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    font = load_font(max(28, w // 22), bold=True)
    try:
        l, t, r, b = d.textbbox((0, 0), WATERMARK, font=font)
        tw, th = r - l, b - t
    except Exception:
        tw, th = (w // 2, 40)
    band = Image.new("RGBA", (tw + 60, th + 30), (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    bd.text((30, 15), WATERMARK, font=font, fill=(178, 30, 30, 70))
    band = band.rotate(28, expand=True, resample=Image.BICUBIC)
    layer.alpha_composite(band, (w // 2 - band.size[0] // 2, h // 2 - band.size[1] // 2))
    out = doc.convert("RGBA")
    out.alpha_composite(layer)
    return out.convert("RGB")


def new_doc(w, h):
    # type: (int, int) -> Tuple[Image.Image, ImageDraw.ImageDraw]
    img = Image.new("RGB", (w, h), (252, 252, 250))
    d = ImageDraw.Draw(img)
    d.rectangle([6, 6, w - 7, h - 7], outline=(40, 40, 40), width=3)
    return img, d


# ------------------------------------------------------- document art ---

def make_identity_card():
    # type: () -> Image.Image
    img, d = new_doc(1000, 640)
    y = 28
    y = centered(d, 1000, y, "IDENTITY CARD (Aadhaar details)", load_font(40, True))
    y = centered(d, 1000, y, "FICTIONAL - NOT A GOVERNMENT DOCUMENT", load_font(24))
    y += 8
    f_label = load_font(28, True)
    f_val = load_font(30)
    rows = [
        ("Name:", "Priya Ramesh Patil"),
        ("Father:", "Ramesh Patil"),
        ("DOB:", "14/08/2007"),
        ("Gender:", "Female"),
    ]
    for k, v in rows:
        d.text((70, y), k, font=f_label, fill=(20, 20, 20))
        d.text((230, y), v, font=f_val, fill=(20, 20, 20))
        y += 46
    addr = "H.No 12, Ward 3, Shivaji Nagar,"
    addr2 = "Hosapete, Karnataka - 583201"
    d.text((70, y), "Address:", font=f_label, fill=(20, 20, 20))
    d.text((230, y), addr, font=load_font(26), fill=(20, 20, 20))
    y += 38
    d.text((230, y), addr2, font=load_font(26), fill=(20, 20, 20))
    y += 48
    d.text((70, y), "Aadhaar No:", font=load_font(30, True), fill=(20, 20, 20))
    d.text((330, y - 8), "9999 0000 1231", font=load_font(62, True), fill=(10, 10, 10))
    return add_watermark(img)


def make_passbook():
    # type: () -> Image.Image
    img, d = new_doc(1000, 700)
    y = 26
    y = centered(d, 1000, y, "SAMPLE GRAMEENA BANK", load_font(46, True))
    y = centered(d, 1000, y, "Savings Passbook  -  Branch: Hosapete Main", load_font(28))
    y += 10
    d.line([(60, y), (940, y)], fill=(60, 60, 60), width=2)
    y += 18
    f_label = load_font(30, True)
    f_val = load_font(34)
    d.text((80, y), "Account Holder:", font=f_label, fill=(20, 20, 20))
    d.text((420, y), "PRIYA R PATIL", font=load_font(36, True), fill=(10, 10, 10))
    y += 56
    d.text((80, y), "Account No:", font=f_label, fill=(20, 20, 20))
    d.text((420, y), "30412345678", font=f_val, fill=(10, 10, 10))
    y += 56
    d.text((80, y), "IFSC:", font=f_label, fill=(20, 20, 20))
    d.text((420, y), "SMPL0001234", font=f_val, fill=(10, 10, 10))
    y += 56
    d.text((80, y), "Branch:", font=f_label, fill=(20, 20, 20))
    d.text((420, y), "Hosapete Main", font=f_val, fill=(10, 10, 10))
    y += 62
    d.line([(60, y), (940, y)], fill=(60, 60, 60), width=2)
    y += 14
    y = centered(d, 1000, y, "FICTIONAL PASSBOOK FOR DEMO ONLY", load_font(24))
    return add_watermark(img)


MARKS = [
    ("Kannada", 100, 78),
    ("English", 100, 72),
    ("Physics", 100, 76),
    ("Chemistry", 100, 74),
    ("Mathematics", 100, 75),
    ("Biology", 100, 77),
]


def make_marksheet():
    # type: () -> Image.Image
    img, d = new_doc(1100, 1500)
    y = 34
    y = centered(d, 1100, y, "II PUC MARKS CARD (SAMPLE)", load_font(44, True))
    y = centered(d, 1100, y, "Fictional Board of Demo Examinations", load_font(28))
    y += 8
    f = load_font(30)
    fb = load_font(30, True)
    d.text((90, y), "Name:", font=fb, fill=(20, 20, 20))
    d.text((230, y), "Priya Ramesh Patil", font=fb, fill=(10, 10, 10))
    y += 50
    d.text((90, y), "DOB: 14/08/2007", font=f, fill=(20, 20, 20))
    d.text((620, y), "Reg No: SAMPLEPUC001", font=f, fill=(20, 20, 20))
    y += 56
    # table
    x0, x1, x2, x3 = 90, 560, 760, 1010
    d.line([(x0, y), (x3, y)], fill=(20, 20, 20), width=3)
    y += 10
    d.text((x0 + 10, y), "Subject", font=fb, fill=(20, 20, 20))
    d.text((x1 + 10, y), "Max", font=fb, fill=(20, 20, 20))
    d.text((x2 + 10, y), "Obtained", font=fb, fill=(20, 20, 20))
    y += 46
    d.line([(x0, y), (x3, y)], fill=(20, 20, 20), width=2)
    y += 10
    for subj, mx, ob in MARKS:
        d.text((x0 + 10, y), subj, font=f, fill=(20, 20, 20))
        d.text((x1 + 10, y), str(mx), font=f, fill=(20, 20, 20))
        d.text((x2 + 10, y), str(ob), font=load_font(30, True), fill=(10, 10, 10))
        y += 48
    d.line([(x0, y), (x3, y)], fill=(20, 20, 20), width=3)
    y += 18
    d.text((x0 + 10, y), "Grand Total: 452 / 600", font=load_font(36, True), fill=(10, 10, 10))
    y += 56
    d.text((x0 + 10, y), "Percentage: 75.33%", font=load_font(36, True), fill=(10, 10, 10))
    y += 56
    d.text((x0 + 10, y), "Result: PASS", font=load_font(34, True), fill=(10, 10, 10))
    return add_watermark(img)


def make_income_cert(name, father, income, caste="OBC"):
    # type: (str, str, str, str) -> Image.Image
    img, d = new_doc(1100, 1500)
    y = 36
    y = centered(d, 1100, y, "Office of the Tahsildar, Hosapete Taluk", load_font(38, True))
    y = centered(d, 1100, y, "Income and Caste Certificate (SAMPLE - FICTIONAL)", load_font(28))
    y += 10
    d.line([(70, y), (1030, y)], fill=(60, 60, 60), width=2)
    y += 26
    fb = load_font(32, True)
    f = load_font(30)
    lines = [
        "Cert No: SAMPLE-INC-2026-001",
        "Name: " + name,
        "Daughter of: " + father,
        "Address: H.No 12, Ward 3, Shivaji Nagar,",
        "Hosapete, Karnataka - 583201",
        "Caste / Category: " + caste,
        "Annual Family Income: " + income,
    ]
    for i, line in enumerate(lines):
        font = fb if line.startswith(("Name:", "Annual", "Caste")) else f
        d.text((90, y), line, font=font, fill=(10, 10, 10))
        y += 52
    y += 10
    body = [
        "This is to certify that the above person belongs",
        "to " + caste + " category and the annual family",
        "income stated above is as per records furnished",
        "for demo purposes. Fictional certificate.",
    ]
    for line in body:
        d.text((90, y), line, font=f, fill=(30, 30, 30))
        y += 46
    y += 30
    d.rectangle([700, y, 1000, y + 160], outline=(60, 60, 60), width=2)
    d.text((730, y + 50), "SAMPLE SEAL", font=load_font(30, True), fill=(120, 30, 30))
    d.text((730, y + 100), "Tahsildar", font=f, fill=(30, 30, 30))
    return add_watermark(img)


# ------------------------------------------------- photo composition ---

def make_wood(w, h, seed=7):
    # type: (int, int, int) -> Image.Image
    rnd = random.Random(seed)
    base = Image.new("RGB", (w, h), (164, 126, 82))
    d = ImageDraw.Draw(base)
    # planks
    plank_h = 220
    y = 0
    while y < h:
        shade = rnd.randint(-12, 12)
        d.rectangle([0, y, w, min(y + plank_h, h)], fill=(164 + shade, 126 + shade, 82 + shade))
        d.line([(0, y), (w, y)], fill=(110, 80, 50), width=4)
        y += plank_h
    # grain lines
    for _ in range(140):
        gy = rnd.randint(0, h)
        amp = rnd.uniform(2, 9)
        per = rnd.uniform(180, 520)
        ph = rnd.uniform(0, 6)
        col = (rnd.randint(95, 130), rnd.randint(65, 95), rnd.randint(40, 62))
        prev = None  # type: Optional[Tuple[int, float]]
        for x in range(0, w, 14):
            yy = gy + amp * math.sin(x / per * 6.28 + ph)
            if prev is not None:
                d.line([prev, (x, yy)], fill=col, width=2)
            prev = (x, yy)
    # speckle noise
    px = base.load()
    for _ in range(w * h // 90):
        x = rnd.randint(0, w - 1)
        yy = rnd.randint(0, h - 1)
        r, g, b = px[x, yy]
        n = rnd.randint(-14, 14)
        px[x, yy] = (max(0, min(255, r + n)), max(0, min(255, g + n)), max(0, min(255, b + n)))
    return base


def paste_clipped(base, overlay, pos):
    # type: (Image.Image, Image.Image, Tuple[int, int]) -> None
    """Paste RGBA overlay onto RGB base, clipping at the frame edges."""
    x, y = pos
    bw, bh = base.size
    ow, oh = overlay.size
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + ow, bw), min(y + oh, bh)
    if x1 <= x0 or y1 <= y0:
        return
    crop = overlay.crop((x0 - x, y0 - y, x0 - x + (x1 - x0), y0 - y + (y1 - y0)))
    bg = base.crop((x0, y0, x1, y1)).convert("RGBA")
    bg.alpha_composite(crop)
    base.paste(bg.convert("RGB"), (x0, y0))


def place_doc(base, doc, center, angle):
    # type: (Image.Image, Image.Image, Tuple[int, int], float) -> None
    rot = doc.convert("RGBA").rotate(angle, expand=True, resample=Image.BICUBIC)
    alpha = rot.split()[3].filter(ImageFilter.GaussianBlur(16))
    shadow = Image.new("RGBA", rot.size, (0, 0, 0, 0))
    black = Image.new("RGBA", rot.size, (25, 18, 12, 130))
    shadow.paste(black, (0, 0), alpha)
    paste_clipped(base, shadow, (int(center[0] - rot.size[0] / 2 + 20), int(center[1] - rot.size[1] / 2 + 24)))
    paste_clipped(base, rot, (int(center[0] - rot.size[0] / 2), int(center[1] - rot.size[1] / 2)))


def fit_doc(doc, max_w, max_h):
    # type: (Image.Image, int, int) -> Image.Image
    """Scale down only, so every document stays fully readable."""
    w, h = doc.size
    scale = min(float(max_w) / w, float(max_h) / h, 1.0)
    if scale >= 1.0:
        return doc
    return doc.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)


def photo_two_docs(doc_left, doc_right, seed=11):
    # type: (Image.Image, Image.Image, int) -> Image.Image
    """Two documents side by side with a clear wood gap (SAM: two boxes)."""
    base = make_wood(1800, 1350, seed=seed)
    left = fit_doc(doc_left, 800, 1050)
    right = fit_doc(doc_right, 800, 1050)
    place_doc(base, left, (440, 675), -3.0)
    place_doc(base, right, (1360, 675), 2.5)
    return base


def photo_single(doc, seed=21, angle=2.0):
    # type: (Image.Image, int, float) -> Image.Image
    base = make_wood(1800, 1350, seed=seed)
    place_doc(base, fit_doc(doc, 1500, 1150), (900, 675), angle)
    return base


def photo_cut_off(doc, seed=31):
    # type: (Image.Image, int) -> Image.Image
    """Passbook runs off the bottom edge: bottom ~200px stays outside."""
    base = make_wood(1800, 1350, seed=seed)
    place_doc(base, fit_doc(doc, 1300, 1000), (900, 1180), 1.5)
    return base


def save_jpg(img, path):
    # type: (Image.Image, str) -> None
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    img.save(path, "JPEG", quality=92)
    print("wrote %s" % path)


def main():
    # type: () -> None
    id_card = make_identity_card()
    passbook = make_passbook()
    marksheet = make_marksheet()
    income_a = make_income_cert("Priya Ramesh Patel", "Ramesh Patel", "Rs. 1,20,000")
    income_b = make_income_cert("Priya Ramesh Patil", "Ramesh Patil", "Rs. 3,10,000")
    income_c = make_income_cert("Priya Ramesh Patil", "Ramesh Patil", "Rs. 1,20,000")

    save_jpg(photo_two_docs(id_card, passbook, seed=11), os.path.join(PHOTOS, "case_a_1_id_and_passbook.jpg"))
    save_jpg(photo_single(marksheet, seed=21), os.path.join(PHOTOS, "case_a_2_marksheet.jpg"))
    save_jpg(photo_single(income_a, seed=22, angle=-2.0), os.path.join(PHOTOS, "case_a_3_income_certificate.jpg"))

    save_jpg(photo_two_docs(id_card, passbook, seed=12), os.path.join(PHOTOS, "case_b_1_id_and_passbook.jpg"))
    save_jpg(photo_single(marksheet, seed=23), os.path.join(PHOTOS, "case_b_2_marksheet.jpg"))
    save_jpg(photo_single(income_b, seed=24, angle=-2.0), os.path.join(PHOTOS, "case_b_3_income_certificate.jpg"))

    save_jpg(photo_cut_off(passbook, seed=31), os.path.join(PHOTOS, "case_c_1_passbook_cut_off.jpg"))
    save_jpg(photo_single(marksheet, seed=25), os.path.join(PHOTOS, "case_c_2_marksheet.jpg"))
    save_jpg(photo_single(income_c, seed=26, angle=-2.0), os.path.join(PHOTOS, "case_c_3_income_certificate.jpg"))

    save_jpg(photo_single(passbook, seed=32, angle=1.0), os.path.join(RETAKES, "case_c_passbook_retake.jpg"))


if __name__ == "__main__":
    main()
