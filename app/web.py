"""Web researcher: DuckDuckGo search + official-page fetch + Spark facts.

Only .gov.in / .nic.in pages or a scheme's listed official domains are
ever fetched. Every search and page is cached as JSON under
app/research_cache/; with RESEARCH_OFFLINE=1 only the cache is used.
"""
import hashlib
import html as html_lib
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import meta_client

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, "research_cache")

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) FormSaathi/1.0"}

FACT_KINDS = ("portal", "deadline", "document", "step", "eligibility",
              "upload_limit")

EXTRACT_SYSTEM = (
    "You extract scholarship application facts from a web page. "
    "Reply with exactly one JSON object, no other text."
)

EXTRACT_PROMPT = """Read this web page about the scheme "%s" (source %d: %s).

Page text:
---
%s
---

Reply with exactly one JSON object:
{"facts": [{"kind": "portal|deadline|document|step|eligibility|upload_limit",
"text": "one short fact in plain words",
"quote": ">= 12 characters copied VERBATIM from the page text above"}]}
Only include facts stated on this page. Copy each quote word-for-word
from the page text. Skip anything you cannot quote verbatim.
When the page states an upload rule, capture it as kind "upload_limit",
for example "file size should not exceed 200 KB" or
"only PDF/JPG format is allowed"."""


def offline_only():
    # type: () -> bool
    return os.environ.get("RESEARCH_OFFLINE", "") == "1"


def _cache_path(kind, key):
    # type: (str, str) -> str
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, "%s_%s.json" % (kind, digest))


def cache_get(kind, key):
    # type: (str, str) -> Optional[Any]
    path = _cache_path(kind, key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return None


def cache_set(kind, key, value):
    # type: (str, str, Any) -> str
    if not os.path.isdir(CACHE_DIR):
        os.makedirs(CACHE_DIR)
    path = _cache_path(kind, key)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


def domain_of(url):
    # type: (str) -> str
    m = re.match(r"https?://([^/]+)", (url or "").strip().lower())
    if not m:
        return ""
    return m.group(1).split(":")[0]


def allowed(url, extra_domains=None):
    # type: (str, Optional[List[str]]) -> bool
    """True for .gov.in / .nic.in hosts or the scheme's official domains."""
    host = domain_of(url)
    if not host:
        return False
    if host.endswith(".gov.in") or host == "gov.in":
        return True
    if host.endswith(".nic.in") or host == "nic.in":
        return True
    for d in extra_domains or []:
        dom = (d or "").strip().lower()
        if dom and (host == dom or host.endswith("." + dom)):
            return True
    return False


def ddg_search(query, max_results=5):
    # type: (str, int) -> List[Dict[str, str]]
    """DuckDuckGo HTML search; results are cached as JSON."""
    cached = cache_get("search", query)
    if cached is not None:
        return list(cached)
    if offline_only() or requests is None:
        cache_set("search", query, [])
        return []
    results = []  # type: List[Dict[str, str]]
    try:
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers=HEADERS,
            timeout=20,
        )
        if resp.status_code == 200:
            results = _parse_ddg(resp.text)[:max_results]
    except Exception:
        results = []
    cache_set("search", query, results)
    return results


def _parse_ddg(html_text):
    # type: (str) -> List[Dict[str, str]]
    out = []  # type: List[Dict[str, str]]
    for m in re.finditer(
        r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
        r"([\s\S]{0,600}?)(?=result__a|<a[^>]+class=\"result__a\"|$)",
        html_text,
    ):
        href, title_html, rest = m.group(1), m.group(2), m.group(3)
        url = _unwrap_ddg_url(href)
        if not url.startswith("http"):
            continue
        title = strip_html(title_html)
        snip = ""
        sm = re.search(r'class="result__snippet"[^>]*>(.*?)</', rest, re.DOTALL)
        if sm:
            snip = strip_html(sm.group(1))
        out.append({"title": title, "url": url, "snippet": snip})
    return out


def _unwrap_ddg_url(href):
    # type: (str) -> str
    m = re.search(r"[?&]uddg=([^&]+)", html_lib.unescape(href))
    if m:
        try:
            from urllib.parse import unquote

            return unquote(m.group(1))
        except Exception:
            return m.group(1)
    return html_lib.unescape(href)


def strip_html(html_text):
    # type: (str) -> str
    """Remove tags, scripts and styles; collapse whitespace."""
    s = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1\s*>", " ", html_text)
    s = re.sub(r"(?s)<!--.*?-->", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html_lib.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def fetch_page(url, extra_domains=None, max_chars=8000):
    # type: (str, Optional[List[str]], int) -> Optional[Dict[str, str]]
    """Fetch one page when its domain is allowed; cached as JSON."""
    if not allowed(url, extra_domains):
        return None
    cached = cache_get("page", url)
    if cached is not None:
        return dict(cached)
    if offline_only() or requests is None:
        return None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return None
        text = strip_html(resp.text)[:max_chars]
        if not text:
            return None
        payload = {"url": url, "text": text}
        cache_set("page", url, payload)
        return payload
    except Exception:
        return None


def _norm(text):
    # type: (Any) -> str
    s = "" if text is None else str(text).lower()
    return re.sub(r"\s+", " ", s).strip()


def verify_facts(facts, page_text):
    # type: (List[Dict[str, Any]], str) -> Tuple[List[Dict[str, Any]], int]
    """Keep facts whose quote is literally on the page (>= 12 chars)."""
    kept = []  # type: List[Dict[str, Any]]
    dropped = 0
    norm_page = _norm(page_text)
    for f in facts or []:
        if not isinstance(f, dict):
            dropped += 1
            continue
        if f.get("kind") not in FACT_KINDS:
            dropped += 1
            continue
        if not f.get("text"):
            dropped += 1
            continue
        quote = _norm(f.get("quote"))
        if len(quote) < 12 or quote not in norm_page:
            dropped += 1
            continue
        kept.append({"kind": f["kind"], "text": str(f["text"]),
                     "quote": str(f.get("quote"))})
    return kept, dropped


def parse_upload_rule(text):
    # type: (str) -> Optional[Dict[str, Any]]
    """Parse an upload_limit fact text into {"max_kb", "formats"}.

    Finds the first "<number> KB/MB" size and the words pdf/jpg/jpeg/png.
    Returns None when the text states neither a size nor a format.
    """
    s = "" if text is None else str(text)
    max_kb = None  # type: Optional[int]
    m = re.search(r"(\d+(?:\.\d+)?)\s*(MB|KB)", s, re.IGNORECASE)
    if m:
        try:
            val = float(m.group(1))
        except ValueError:
            val = 0.0
        if m.group(2).upper() == "MB":
            max_kb = int(val * 1024)
        else:
            max_kb = int(val)
    found = []  # type: List[Any]
    for name, canon in (("pdf", "pdf"), ("jpg", "jpg"), ("jpeg", "jpg"),
                        ("png", "png")):
        mm = re.search(r"\b%s\b" % name, s, re.IGNORECASE)
        if mm:
            found.append((mm.start(), canon))
    found.sort()
    formats = []  # type: List[str]
    for _, canon in found:
        if canon not in formats:
            formats.append(canon)
    if max_kb is None and not formats:
        return None
    return {"max_kb": max_kb, "formats": formats}


def extract_facts(page_text, scheme_title, source_index, url):
    # type: (str, str, int, str) -> Tuple[List[Dict[str, Any]], int]
    """Ask Spark for facts, then keep only literally quoted ones."""
    try:
        data = meta_client.chat_json(
            EXTRACT_PROMPT % (scheme_title, source_index, url,
                              (page_text or "")[:6000]),
            system=EXTRACT_SYSTEM,
        )
    except Exception:
        return [], 1
    raw = (data.get("facts") or []) if isinstance(data, dict) else []
    kept, dropped = verify_facts(raw, page_text)
    out = []  # type: List[Dict[str, Any]]
    for f in kept:
        item = dict(f)
        item["source"] = source_index
        out.append(item)
    return out, dropped


def research_scheme(scheme, max_pages=6):
    # type: (Dict[str, Any]) -> Dict[str, Any]
    """Research one scheme: search its queries, fetch seeds + hits.

    Returns {"scheme_id", "facts", "sources", "dropped"}.
    """
    scheme_id = str(scheme.get("scheme_id"))
    title = str(scheme.get("title", scheme_id))
    extra = list(scheme.get("official_domains") or [])
    urls = []  # type: List[str]
    for seed in scheme.get("seed_urls") or []:
        if seed not in urls:
            urls.append(seed)
    for query in scheme.get("search_queries") or []:
        try:
            hits = ddg_search(query)
        except Exception:
            hits = []
        for h in hits:
            u = (h or {}).get("url")
            if u and u not in urls:
                urls.append(u)
    facts = []  # type: List[Dict[str, Any]]
    sources = []  # type: List[str]
    dropped = 0
    for url in urls[:max_pages]:
        try:
            page = fetch_page(url, extra_domains=extra)
        except Exception:
            page = None
        if not page:
            continue
        sources.append(url)
        try:
            items, lost = extract_facts(page["text"], title, len(sources) - 1,
                                        url)
        except Exception:
            items, lost = [], 1
        facts.extend(items)
        dropped += lost
    return {"scheme_id": scheme_id, "facts": facts, "sources": sources,
            "dropped": dropped}
