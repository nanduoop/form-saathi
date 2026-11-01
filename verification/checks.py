"""Deterministic format checks for Indian form fields."""

import re
from datetime import datetime
from difflib import SequenceMatcher

# Verhoeff tables (used by Aadhaar's check digit)
_D = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
      [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
      [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
      [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]]
_P = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
      [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
      [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]]
_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def digits(s):
    return re.sub(r"\D", "", str(s or ""))


def verhoeff_valid(num):
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def verhoeff_digit(num):
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = _D[c][_P[(i + 1) % 8][int(ch)]]
    return _INV[c]


def parse_money(s):
    t = str(s or "").lower().replace(",", "").replace("rs.", "").replace("rs", "").replace("₹", "").strip()
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(lakh|lakhs|lac)?$", t)
    if not m:
        return None
    v = float(m.group(1))
    return int(v * 100000) if m.group(2) else int(v)


def parse_date(s):
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(str(s).strip(), fmt)
        except ValueError:
            pass
    return None


def check_value(kind, value):
    """Return an error string, or None if the value passes."""
    v = str(value or "").strip()
    if kind == "aadhaar":
        d = digits(v)
        if len(d) != 12:
            return "Aadhaar must have 12 digits"
        if d[0] in "01":
            return "Aadhaar cannot start with 0 or 1"
        if not verhoeff_valid(d):
            return "Aadhaar check digit (Verhoeff) is wrong, likely a misread digit"
    elif kind == "ifsc":
        if not re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", v.upper()):
            return "IFSC must be 4 letters, then 0, then 6 letters/digits"
    elif kind == "pin":
        if not re.fullmatch(r"[1-9]\d{5}", digits(v)) or len(digits(v)) != 6:
            return "PIN code must be 6 digits and not start with 0"
    elif kind == "mobile":
        d = digits(v)
        if len(d) == 12 and d.startswith("91"):
            d = d[2:]
        if not re.fullmatch(r"[6-9]\d{9}", d):
            return "mobile must be 10 digits starting with 6-9"
    elif kind == "date":
        dt = parse_date(v)
        if not dt:
            return "date must be DD/MM/YYYY"
        if not (1950 <= dt.year <= datetime.now().year - 10):
            return "date of birth year is implausible"
    elif kind == "account":
        if not re.fullmatch(r"\d{9,18}", digits(v)) or digits(v) != re.sub(r"[\s-]", "", v):
            return "account number must be 9-18 digits"
    elif kind == "category":
        if v.upper() not in ("SC", "ST", "OBC", "GENERAL", "GEN", "EWS"):
            return "category must be SC, ST, OBC, General or EWS"
    elif kind == "income":
        if parse_money(v) is None:
            return "income must be a rupee amount"
    elif kind == "int":
        if not re.fullmatch(r"\d+", v):
            return "must be a whole number"
    elif kind == "percentage":
        try:
            p = float(v.rstrip("%"))
        except ValueError:
            return "percentage must be a number"
        if not 0 <= p <= 100:
            return "percentage must be 0-100"
    elif kind == "gender":
        if v.lower() not in ("male", "female", "transgender", "other"):
            return "gender must be Male, Female, Transgender or Other"
    return None


def norm_text(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def value_in_quote(value, quote):
    """Is the value literally supported by the quoted text on the document?"""
    nv, nq = norm_text(value), norm_text(quote)
    if not nv or not nq:
        return False
    if nv in nq:
        return True
    dv = digits(value)
    if dv and len(dv) >= 4 and dv in digits(quote):
        return True
    m = parse_money(value)
    if m is not None and str(m) in digits(quote):
        return True
    return False


def _tok_eq(x, y):
    return x == y or (len(x) == 1 and y.startswith(x)) or (len(y) == 1 and x.startswith(y))


def name_similarity(a, b):
    """0..1. Initials are fine ('Priya R. Patil' = 'Priya Ramesh Patil'); a changed letter is not ('Patil' vs 'Patel')."""
    ta = re.findall(r"[a-z]+", str(a or "").lower())
    tb = re.findall(r"[a-z]+", str(b or "").lower())
    if not ta or not tb:
        return 0.0
    full = SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio()
    if len(ta) == len(tb):
        return 0.99 if all(_tok_eq(x, y) for x, y in zip(ta, tb)) else min(full, 0.8)
    short, long_ = (ta, tb) if len(ta) < len(tb) else (tb, ta)
    i = 0
    for t in long_:
        if i < len(short) and _tok_eq(short[i], t):
            i += 1
    if i == len(short) and _tok_eq(short[0], long_[0]) and _tok_eq(short[-1], long_[-1]):
        return 0.95
    return min(full, 0.8)
