"""Pure format validators for FormSaathi fields. No API calls here."""
import datetime
import difflib
import re
from typing import Any, List, Optional

# ---------------------------------------------------------- Verhoeff ---

_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]

_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]

_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def _verhoeff_ok(digits):
    # type: (str) -> bool
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def verhoeff_valid(value):
    # type: (Any) -> bool
    """Pure Verhoeff checksum over the digit string (no leading-digit rule)."""
    d = _digits(value)
    if not d:
        return False
    return _verhoeff_ok(d)


def aadhaar_check_digit(base11):
    # type: (str) -> str
    """Check digit completing an 11-digit base into a Verhoeff number."""
    base = re.sub(r"\D", "", str(base11))
    if len(base) != 11 or base[0] in ("0", "1"):
        raise ValueError("need 11 digits not starting 0/1")
    c = 0
    for i, ch in enumerate(reversed(base)):
        c = _D[c][_P[(i + 1) % 8][int(ch)]]
    return str(_INV[c])


def _digits(value):
    # type: (Any) -> str
    return re.sub(r"\D", "", "" if value is None else str(value))


def valid_aadhaar(value):
    # type: (Any) -> bool
    d = _digits(value)
    if not re.fullmatch(r"[2-9]\d{11}", d):
        return False
    return _verhoeff_ok(d)


def valid_ifsc(value):
    # type: (Any) -> bool
    if value is None:
        return False
    s = re.sub(r"\s", "", str(value)).upper()
    return bool(re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", s))


def valid_pin(value):
    # type: (Any) -> bool
    if value is None:
        return False
    return bool(re.fullmatch(r"[1-9]\d{5}", str(value).strip()))


def valid_mobile(value):
    # type: (Any) -> bool
    d = _digits(value)
    if len(d) == 12 and d.startswith("91"):
        d = d[2:]
    return bool(re.fullmatch(r"[6-9]\d{9}", d))


def valid_date(value):
    # type: (Any) -> bool
    """DD/MM/YYYY with a plausible birth year (1900..today, not future)."""
    if value is None:
        return False
    s = str(value).strip()
    parsed = None  # type: Optional[datetime.date]
    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            parsed = datetime.datetime.strptime(s, fmt).date()
            break
        except ValueError:
            continue
    if parsed is None:
        return False
    today = datetime.date.today()
    return (1900 <= parsed.year <= today.year) and (parsed <= today)


def valid_account(value):
    # type: (Any) -> bool
    if value is None:
        return False
    return bool(re.fullmatch(r"\d{9,18}", re.sub(r"\s", "", str(value))))


def valid_category(value):
    # type: (Any) -> bool
    if value is None:
        return False
    return str(value).strip().upper() in ("SC", "ST", "OBC", "GENERAL", "EWS")


def parse_income(value):
    # type: (Any) -> Optional[int]
    """Parse 'Rs. 1,20,000', '120000' or '1.2 lakh' to rupees."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    if not s:
        return None
    low = s.lower()
    if "lakh" in low or "lac" in low:
        m = re.search(r"(\d+(?:\.\d+)?)", low.replace(",", ""))
        if not m:
            return None
        try:
            return int(round(float(m.group(1)) * 100000))
        except ValueError:
            return None
    digits = re.sub(r"[^\d]", "", s)
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def valid_income(value):
    # type: (Any) -> bool
    return parse_income(value) is not None


def valid_int(value):
    # type: (Any) -> bool
    if value is None or isinstance(value, bool):
        return False
    try:
        int(str(value).replace(",", "").strip())
        return True
    except (ValueError, TypeError):
        return False


def valid_percentage(value):
    # type: (Any) -> bool
    if value is None or isinstance(value, bool):
        return False
    try:
        p = float(str(value).replace("%", "").strip())
    except (ValueError, TypeError):
        return False
    return 0.0 <= p <= 100.0


def valid_gender(value):
    # type: (Any) -> bool
    if value is None:
        return False
    return str(value).strip().lower() in ("male", "female", "other",
                                         "m", "f")


CHECKS = {
    "aadhaar": valid_aadhaar,
    "ifsc": valid_ifsc,
    "pin": valid_pin,
    "mobile": valid_mobile,
    "date": valid_date,
    "account": valid_account,
    "category": valid_category,
    "income": valid_income,
    "int": valid_int,
    "percentage": valid_percentage,
    "gender": valid_gender,
}


def _norm(text):
    # type: (Any) -> str
    s = "" if text is None else str(text).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]", " ", s)).strip()


def value_in_quote(value, quote):
    # type: (Any, Any) -> bool
    """True when a document quote supports the claimed value."""
    if value is None or quote is None:
        return False
    nv, nq = _norm(value), _norm(quote)
    if nv and nv in nq:
        return True
    dv, dq = _digits(value), _digits(quote)
    if dv:
        tokens = [_digits(t) for t in re.findall(r"\d[\d,]*", str(quote))]
        if dv in tokens or dv in dq:
            return True
    iv, iq = parse_income(value), parse_income(quote)
    if iv is not None and iq is not None and iv == iq:
        return True
    return False


def _name_tokens(name):
    # type: (Any) -> List[str]
    return [t.upper() for t in
            re.findall(r"[^\W\d_]+", "" if name is None else str(name))]


def _tok_match(short_tok, long_tok):
    # type: (str, str) -> float
    if short_tok == long_tok:
        return 1.0
    if len(short_tok) == 1 and long_tok.startswith(short_tok):
        return 1.0
    return difflib.SequenceMatcher(None, short_tok, long_tok).ratio()


def _ordered_match(shorter, longer):
    # type: (List[str], List[str]) -> Optional[List[int]]
    """Greedy in-order token match; None when a token has no partner."""
    idx = []  # type: List[int]
    j = 0
    for tok in shorter:
        found = None  # type: Optional[int]
        for k in range(j, len(longer)):
            if _tok_match(tok, longer[k]) >= 1.0:
                found = k
                break
        if found is None:
            return None
        idx.append(found)
        j = found + 1
    return idx


def name_similarity(a, b):
    # type: (Any, Any) -> float
    """0..1 name score. Initials match; one changed letter does not."""
    ta, tb = _name_tokens(a), _name_tokens(b)
    if not ta or not tb:
        return 0.0
    if ta == tb:
        return 1.0
    shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    idx = _ordered_match(shorter, longer)
    if (idx is not None and idx[0] == 0 and idx[-1] == len(longer) - 1
            and shorter[-1] == longer[idx[-1]]):
        # Ordered subset with the same first and last token, e.g.
        # "PRIYA R PATIL" against "Priya Ramesh Patil".
        return 0.95
    if len(ta) == len(tb):
        ratio = sum(_tok_match(x, y) for x, y in zip(ta, tb)) / len(ta)
        for x, y in zip(ta, tb):
            if x == y:
                continue
            if (len(x) == 1 and y.startswith(x)) or \
                    (len(y) == 1 and x.startswith(y)):
                continue
            return min(ratio, 0.8)
        return ratio
    total = 0.0
    j = 0
    for tok in shorter:
        best, best_k = 0.0, -1
        for k in range(j, len(longer)):
            s = _tok_match(tok, longer[k])
            if s > best:
                best, best_k = s, k
        total += best
        if best_k >= 0:
            j = best_k + 1
    return total / max(len(ta), len(tb))
