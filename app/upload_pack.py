"""Upload-ready document pack: resize and compress SAM crops for portals.

make_pack(record, scheme_id) builds one portal-ready file per non-rejected
document cited by a filled field (or by the profile): straighten small
tilts, shrink the long side to max_px, and binary-search the JPEG quality
until the file fits under max_kb. Each output is verified deterministically
(size, format, dimensions) plus one independent Spark readability check.

Run from the repo root:  python app/upload_pack.py <case_id>
"""
import io
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageOps

import meta_client
import web
from case_record import CaseRecord, state_dir

HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULT_RULE = {"formats": ["jpg", "pdf"], "max_kb": 200, "min_kb": 10,
                "max_px": 1200, "min_dpi_hint": 150}  # type: Dict[str, Any]

MAX_TILT_DEG = 10
MIN_QUALITY = 35
MAX_QUALITY = 92
SHRINK_STEP = 0.85


def default_upload():
    # type: () -> Dict[str, Any]
    """Fresh copy of the demo upload section (source: default)."""
    return {"default": dict(DEFAULT_RULE),
            "per_doc": {},
            "source": "default"}


def scheme_upload_section(scheme_id):
    # type: (str) -> Dict[str, Any]
    """Upload section for a scheme id (defaults when the catalog lacks one)."""
    try:
        path = os.path.join(HERE, "schemes", "catalog.json")
        with open(path, "r", encoding="utf-8") as f:
            catalog = json.load(f)
        for s in catalog.get("schemes", []):
            if s.get("scheme_id") == scheme_id and s.get("upload"):
                return s["upload"]
    except (ValueError, OSError):
        pass
    return default_upload()


def rule_for_doc(upload, doc_type, facts):
    # type: (Dict[str, Any], str, List[Dict[str, Any]]) -> Tuple[Dict[str, Any], str]
    """Resolve the rule for one document type.

    A verified upload_limit fact overrides the defaults (source: fact id);
    otherwise the per_doc override or default applies (source: default).
    """
    default = dict((upload or {}).get("default") or DEFAULT_RULE)
    for key in ("formats", "max_kb", "min_kb", "max_px", "min_dpi_hint"):
        if key not in default and key in DEFAULT_RULE:
            default[key] = DEFAULT_RULE[key]
    per_doc = (upload or {}).get("per_doc") or {}
    if doc_type in per_doc:
        rule = dict(default)
        rule.update(per_doc[doc_type])
        return rule, "default"
    for f in facts or []:
        if (f or {}).get("kind") != "upload_limit":
            continue
        parsed = web.parse_upload_rule((f or {}).get("text"))
        if not parsed:
            continue
        rule = dict(default)
        if parsed.get("max_kb"):
            rule["max_kb"] = parsed["max_kb"]
        if parsed.get("formats"):
            rule["formats"] = parsed["formats"]
        return rule, str((f or {}).get("id") or "official")
    return default, str((upload or {}).get("source") or "default")


def _norm(text):
    # type: (Any) -> str
    return re.sub(r"\s+", " ",
                  re.sub(r"[^a-z0-9]", " ", str(text).lower())).strip()


def cited_doc_ids(record):
    # type: (CaseRecord) -> List[str]
    """Ids of non-rejected documents cited by a filled field or the profile."""
    ids = []  # type: List[str]
    for fid, filled in (record.fields or {}).items():
        src = (filled or {}).get("source") or {}
        if src.get("type") == "document" and src.get("doc_id"):
            if src["doc_id"] not in ids:
                ids.append(src["doc_id"])
    profile = record.profile or {}
    bits = [_norm(v) for v in profile.values()
            if v is not None and str(v).strip()]
    digits = [re.sub(r"\D", "", b) for b in bits]
    for d in record.documents:
        if d.get("rejected") or d.get("id") in ids:
            continue
        for f in d.get("fields") or []:
            v = _norm((f or {}).get("value"))
            dv = re.sub(r"\D", "", v)
            if (v and v in bits) or (dv and dv in digits):
                ids.append(d["id"])
                break
    return ids


def applicant_slug(record):
    # type: (CaseRecord) -> str
    """Filesystem-safe applicant name, e.g. Priya_Patil."""
    name = ((record.profile or {}).get("name")
            or ((record.fields.get("applicant_name") or {}).get("value"))
            or "applicant")
    slug = re.sub(r"[^\w-]+", "_", str(name).strip()).strip("_")
    return slug or "applicant"


def estimate_skew(img):
    # type: (Image.Image) -> float
    """Estimate tilt in degrees from dark-pixel row profiles (0 = unsure).

    Tries -10..+10 degrees on a small thumbnail and keeps the angle with
    the peakier row profile. Never returns more than 10 degrees.
    """
    try:
        w, h = img.size
        tw = 300
        th = max(1, int(round(h * tw / max(1, w))))
        g = img.convert("L").resize((tw, th))
        vals = list(g.getdata())
        if not vals:
            return 0.0
        dark = [1 if v < 150 else 0 for v in vals]
        frac = sum(dark) / len(dark)
        if frac < 0.01 or frac > 0.50:
            return 0.0  # too blank or too dark to judge; skip

        def peakiness(angle):
            # type: (float) -> float
            r = g.rotate(angle, expand=True)
            rw, rh = r.size
            px = list(r.getdata())
            rows = [0.0] * rh
            for y in range(rh):
                rows[y] = sum(1 for v in px[y * rw:(y + 1) * rw] if v < 150)
            mean = sum(rows) / max(1, len(rows))
            return sum((c - mean) ** 2 for c in rows) / max(1, len(rows))

        base = peakiness(0.0)
        if base <= 0:
            return 0.0
        best, best_score = 0.0, base
        angle = -10.0
        while angle <= 10.0:
            s = peakiness(angle)
            if s > best_score:
                best, best_score = angle, s
            angle += 2.0
        if best == 0.0 or best_score < base * 1.05:
            return 0.0
        return max(-MAX_TILT_DEG, min(MAX_TILT_DEG, best))
    except Exception:
        return 0.0


def straighten(img):
    # type: (Image.Image) -> Image.Image
    """RGB + EXIF-stripped image with small tilts (<= 10 deg) corrected."""
    flat = ImageOps.exif_transpose(img).convert("RGB")
    angle = estimate_skew(flat)
    if not angle:
        return flat
    return flat.rotate(angle, expand=True, resample=Image.BICUBIC)


def fit_long_side(img, max_px):
    # type: (Image.Image, int) -> Image.Image
    """Shrink so the long side is <= max_px (aspect kept, LANCZOS)."""
    w, h = img.size
    long_side = max(w, h)
    if long_side <= max_px or long_side <= 0:
        return img
    scale = max_px / float(long_side)
    return img.resize((max(1, int(round(w * scale))),
                       max(1, int(round(h * scale)))), Image.LANCZOS)


def jpg_bytes(img, quality):
    # type: (Image.Image, int) -> bytes
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=int(quality))
    return buf.getvalue()


def encode_fit(img, rule, floor_quality=MIN_QUALITY):
    # type: (Image.Image, Dict[str, Any], int) -> Tuple[Image.Image, int, bytes]
    """Highest JPEG quality in [floor, 92] fitting max_kb; else shrink 0.85.

    Returns (image_used, quality, jpeg_bytes). Shrinking repeats until the
    floor quality fits or the long side drops below 200 px.
    """
    max_bytes = int(rule.get("max_kb", 200)) * 1024
    work = img
    for _ in range(12):
        lo, hi = int(floor_quality), MAX_QUALITY
        best = None  # type: Optional[Tuple[int, bytes]]
        while lo <= hi:
            mid = (lo + hi) // 2
            data = jpg_bytes(work, mid)
            if len(data) <= max_bytes:
                best = (mid, data)
                lo = mid + 1
            else:
                hi = mid - 1
        if best is not None:
            quality, data = best
            if (len(data) < int(rule.get("min_kb", 0)) * 1024
                    and quality < MAX_QUALITY):
                up = jpg_bytes(work, MAX_QUALITY)
                if len(up) <= max_bytes:
                    return work, MAX_QUALITY, up
            return work, quality, data
        w, h = work.size
        nw, nh = int(w * SHRINK_STEP), int(h * SHRINK_STEP)
        if max(nw, nh) < 200 or nw < 1 or nh < 1:
            data = jpg_bytes(work, MIN_QUALITY)
            return work, MIN_QUALITY, data
        work = work.resize((nw, nh), Image.LANCZOS)
    data = jpg_bytes(work, MIN_QUALITY)
    return work, MIN_QUALITY, data


def pdf_bytes(img, quality):
    # type: (Image.Image, int) -> bytes
    """Single-page PDF bytes rendered from the JPEG at this quality."""
    data = jpg_bytes(img, quality)
    flat = Image.open(io.BytesIO(data)).convert("RGB")
    buf = io.BytesIO()
    flat.save(buf, "PDF", resolution=150.0)
    return buf.getvalue()


def encode_pdf_fit(img, rule, floor_quality=MIN_QUALITY):
    # type: (Image.Image, Dict[str, Any], int) -> Tuple[Image.Image, int, bytes]
    """Fit like encode_fit but verify the PDF size the same way."""
    max_bytes = int(rule.get("max_kb", 200)) * 1024
    work = img
    for _ in range(12):
        _w, quality, _d = encode_fit(work, rule,
                                     floor_quality=floor_quality)
        data = pdf_bytes(work, quality)
        if len(data) <= max_bytes:
            return work, quality, data
        w, h = work.size
        nw, nh = int(w * SHRINK_STEP), int(h * SHRINK_STEP)
        if max(nw, nh) < 200 or nw < 1 or nh < 1:
            return work, MIN_QUALITY, pdf_bytes(work, MIN_QUALITY)
        work = work.resize((nw, nh), Image.LANCZOS)
    return work, MIN_QUALITY, pdf_bytes(work, MIN_QUALITY)


def readability_check(path, values):
    # type: (str, List[str]) -> Optional[bool]
    """One independent Spark check: is every filled value still readable?

    Returns True (yes), False (no) or None (unsure / check failed).
    """
    listed = "\n".join("- %s" % v for v in values) or "- (no values)"
    prompt = ("Is every value we filled from this document still clearly "
              "readable in this compressed image?\n%s\n"
              "Answer with exactly one word: YES or NO." % listed)
    try:
        msg = meta_client.chat(prompt, image_path=path)
    except Exception:
        return None
    text = ((msg.content if msg is not None else "") or "").strip().lower()
    if text.startswith("y"):
        return True
    if text.startswith("n"):
        return False
    return None


def doc_values(record, doc_id):
    # type: (CaseRecord, str) -> List[str]
    """Filled field values sourced from one document (for the read check)."""
    out = []  # type: List[str]
    for _fid, filled in (record.fields or {}).items():
        src = (filled or {}).get("source") or {}
        if src.get("type") == "document" and src.get("doc_id") == doc_id:
            v = filled.get("value")
            if v is not None and str(v).strip() and str(v) not in out:
                out.append(str(v))
    doc = record.doc(doc_id)
    for f in ((doc or {}).get("fields") or []):
        v = (f or {}).get("value")
        if v is not None and str(v).strip() and str(v) not in out:
            out.append(str(v))
    return out


def pack_one(record, doc, rule, source, pack_dir, slug):
    # type: (CaseRecord, Dict[str, Any], Dict[str, Any], str, str, str) -> Dict[str, Any]
    """Build, verify and readability-check one pack file."""
    doc_id = str(doc.get("id"))
    doc_type = str(doc.get("doc_type") or "document")
    src_path = doc.get("crop") or doc.get("photo") or ""
    formats = [str(f).lower() for f in (rule.get("formats") or ["jpg"])]
    if "jpg" in formats or "jpeg" in formats:
        fmt = "jpg"
    elif "pdf" in formats:
        fmt = "pdf"
    else:
        fmt = "jpg"
    name = "%s_%s.%s" % (slug, doc_type, fmt)
    path = os.path.join(pack_dir, name)
    values = doc_values(record, doc_id)
    max_px = int(rule.get("max_px", 1200))
    max_bytes = int(rule.get("max_kb", 200)) * 1024
    min_bytes = int(rule.get("min_kb", 0)) * 1024

    def build(floor):
        # type: (int) -> Tuple[int, int]
        base = Image.open(src_path)
        try:
            base.load()
            flat = fit_long_side(straighten(base), max_px)
        finally:
            base.close()
        if fmt == "pdf":
            used, _q, data = encode_pdf_fit(flat, rule,
                                           floor_quality=floor)
            long_side = max(used.size[0], used.size[1])
        else:
            _u, _q, data = encode_fit(flat, rule,
                                      floor_quality=floor)
            with open(path, "wb") as f:
                f.write(data)
            with Image.open(path) as check:
                long_side = max(check.size[0], check.size[1])
            return len(data), long_side
        with open(path, "wb") as f:
            f.write(data)
        return len(data), long_side

    nbytes, long_side = build(MIN_QUALITY)
    size_ok = min_bytes <= nbytes <= max_bytes
    format_ok = fmt in formats
    dim_ok = long_side <= max_px
    readable = readability_check(path, values)  # type: Any
    if readable is False:
        nbytes, long_side = build(80)
        size_ok = min_bytes <= nbytes <= max_bytes
        dim_ok = long_side <= max_px
        readable = readability_check(path, values)
    if readable is True:
        readable_out = True  # type: Any
    else:
        readable_out = "needs_manual_check"
    return {"doc_id": doc_id, "doc_type": doc_type, "path": path,
            "format": fmt, "kb": int(round(nbytes / 1024.0)),
            "px": int(long_side), "rule_source": source,
            "max_kb": int(rule.get("max_kb", 200)),
            "checks": {"size_ok": bool(size_ok and dim_ok),
                       "format_ok": bool(format_ok),
                       "readable": readable_out}}


def make_pack(record, scheme_id, upload=None):
    # type: (CaseRecord, str, Optional[Dict[str, Any]]) -> List[Dict[str, Any]]
    """Build the upload pack for one scheme; returns per-file results."""
    section = upload if upload is not None else scheme_upload_section(scheme_id)
    facts = ((record.research or {}).get(scheme_id) or {}).get("facts") or []
    pack_dir = os.path.join(state_dir(record.case_id), "pack")
    if not os.path.isdir(pack_dir):
        os.makedirs(pack_dir)
    slug = applicant_slug(record)
    results = []  # type: List[Dict[str, Any]]
    for doc_id in cited_doc_ids(record):
        doc = record.doc(doc_id)
        if doc is None or doc.get("rejected"):
            continue
        if not (doc.get("crop") or doc.get("photo")):
            continue
        src = doc.get("crop") or doc.get("photo") or ""
        if not os.path.exists(src):
            continue
        rule, source = rule_for_doc(section, str(doc.get("doc_type")),
                                    facts)
        try:
            results.append(pack_one(record, doc, rule, source, pack_dir,
                                    slug))
        except Exception:
            continue
    return results


def main(argv):
    # type: (List[str]) -> int
    """Print the pack table for a saved case (used by run_agent --case)."""
    if not argv:
        print("usage: python app/upload_pack.py <case_id> [scheme_id]")
        return 2
    import agent
    case_id = argv[0]
    record, history = agent.load(case_id)
    scheme_id = argv[1] if len(argv) > 1 else None
    if scheme_id is None:
        scheme_id = str(record.form_id or "post_matric_scholarship")
    pack = make_pack(record, scheme_id)
    record.pack = pack
    agent.save(record, history)
    for r in pack:
        print("%s | %s | %d KB | %d px | %s | %s"
              % (r["doc_id"], r["path"], r["kb"], r["px"],
                 r["rule_source"], r["checks"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
