"""Web search + fetch for the research agent. Results are cached on disk so a demo never depends on a slow site."""

import hashlib
import html
import json
import os
import re
from urllib.parse import parse_qs, unquote, urlparse

import requests

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(APP_DIR, "research_cache")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 FormSaathi/1.0"}
OFFICIAL_SUFFIXES = (".gov.in", ".nic.in")


def is_official(url, extra_domains=()):
    host = (urlparse(url).hostname or "").lower()
    return host.endswith(OFFICIAL_SUFFIXES) or any(host == d or host.endswith("." + d) for d in extra_domains)


def _cache_path(kind, key):
    h = hashlib.sha1(key.encode()).hexdigest()[:16]
    return os.path.join(CACHE_DIR, f"{kind}_{h}.json")


def _cached(kind, key, fn, offline=False):
    path = _cache_path(kind, key)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)["data"]
    if offline:
        raise RuntimeError(f"not in cache (offline mode): {key}")
    data = fn()
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, "w") as f:
        json.dump({"key": key, "data": data}, f, ensure_ascii=False, indent=1)
    return data


def search(query, max_results=8, offline=False):
    """DuckDuckGo HTML results: [{title, url, snippet}]."""
    def go():
        r = requests.post("https://html.duckduckgo.com/html/", data={"q": query}, headers=UA, timeout=20)
        r.raise_for_status()
        out = []
        for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a[^>]+class="result__a"|$)',
                             r.text, re.S):
            href = html.unescape(m.group(1))
            if "uddg=" in href:
                href = unquote(parse_qs(urlparse(href).query).get("uddg", [href])[0])
            snip = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', m.group(3), re.S)
            out.append({"title": _strip(m.group(2)), "url": href, "snippet": _strip(snip.group(1)) if snip else ""})
            if len(out) >= max_results:
                break
        return out
    return _cached("search", query, go, offline)


def _strip(s):
    s = re.sub(r"(?is)<(script|style|noscript|svg|header|footer|nav)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?s)<br\s*/?>|</p>|</li>|</h\d>|</tr>|</div>", "\n", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()


def fetch(url, max_chars=20000, offline=False):
    """Page text (HTML stripped). PDFs are skipped."""
    def go():
        r = requests.get(url, headers=UA, timeout=25)
        r.raise_for_status()
        ctype = r.headers.get("content-type", "")
        if "pdf" in ctype or url.lower().endswith(".pdf"):
            return {"url": url, "text": "", "note": "pdf skipped"}
        return {"url": r.url, "text": _strip(r.text)[:max_chars]}
    return _cached("page", url, go, offline)


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def quote_on_page(quote, page_text):
    """Deterministic: the quoted sentence must really be on the fetched page."""
    q = norm(quote)
    return len(q) >= 12 and q in norm(page_text)
