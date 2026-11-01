"""Printable filled-form renderer for the FormSaathi web console.

render_form_html(record) returns a standalone HTML page: status banner,
every field with its evidence crop + quote (or "applicant said ..."),
discrepancy warnings, eligibility and scheme verdicts.
"""
import os
from typing import Any, Dict, List, Optional

try:
    from html import escape as _escape
except ImportError:
    from cgi import escape as _escape  # type: ignore

import tools


def _esc(value):
    # type: (Any) -> str
    return _escape("" if value is None else str(value), quote=True)


def _utterance_text(record, utterance_id):
    # type: (Any, str) -> Optional[str]
    for u in record.utterances or []:
        if u.get("id") == utterance_id:
            return u.get("text")
    return None


def _doc_label(record, doc_id):
    # type: (Any, str) -> str
    doc = record.doc(doc_id)
    if doc is None:
        return doc_id
    return "%s (%s)" % (doc_id, doc.get("doc_type") or "unread")


def render_form_html(record):
    # type: (Any) -> str
    """Render a printable filled-form page for a case record."""
    form = tools.load_form(record.form_id)
    if record.confirmed:
        banner = ("<div class='banner ok'>Confirmed by applicant%s</div>"
                  % (" on " + _esc(record.confirmed_at)
                     if record.confirmed_at else ""))
    elif record.status == "awaiting_signoff":
        banner = ("<div class='banner warn'>Awaiting applicant sign-off: "
                  "please review every field below.</div>")
    elif record.status == "ineligible":
        banner = ("<div class='banner bad'>Ineligible: %s</div>"
                  % _esc("; ".join((record.eligibility or {}).get(
                      "reasons", []))))
    else:
        banner = ("<div class='banner info'>Status: %s &middot; stage: %s "
                  "(not yet ready for sign-off)</div>"
                  % (_esc(record.status), _esc(record.stage)))
    rows = []  # type: List[str]
    for spec in form.get("fields", []):
        fid = spec.get("id")
        label = spec.get("label", fid)
        filled = (record.fields or {}).get(fid)
        if not filled:
            rows.append("<section class='field missing'><h3>%s</h3>"
                        "<p class='novalue'>Not filled yet</p></section>"
                        % _esc(label))
            continue
        value = filled.get("value")
        source = filled.get("source") or {}
        if source.get("type") == "document":
            doc_id = str(source.get("doc_id", ""))
            quote = _esc(source.get("quote", ""))
            rows.append(
                "<section class='field'><h3>%s</h3>"
                "<p class='value'>%s</p>"
                "<p class='src'>Document %s &mdash; quote: &ldquo;%s&rdquo;</p>"
                "%s</section>" % (
                    _esc(label), _esc(value), _esc(_doc_label(record, doc_id)),
                    quote,
                    ("<img class='crop' loading='lazy' alt='evidence crop' "
                     "src='/cases/%s/crop/%s'>" % (
                         _esc(record.case_id), _esc(doc_id)))
                    if record.doc(doc_id) and
                    (record.doc(doc_id) or {}).get("crop") else ""))
        else:
            uid = str(source.get("utterance_id", ""))
            text = _utterance_text(record, uid)
            rows.append(
                "<section class='field'><h3>%s</h3>"
                "<p class='value'>%s</p>"
                "<p class='src'>applicant said &ldquo;%s&rdquo;</p></section>"
                % (_esc(label), _esc(value), _esc(text or uid)))
    discs = []  # type: List[str]
    for d in record.discrepancies or []:
        discs.append("<li><strong>%s</strong>: %s</li>"
                     % (_esc(d.get("field_id")), _esc(d.get("detail"))))
    schemes = []  # type: List[str]
    for s in record.schemes or []:
        schemes.append("<li><strong>%s</strong> (%s): %s</li>"
                       % (_esc(s.get("scheme_id")), _esc(s.get("status")),
                          _esc("; ".join(s.get("reasons") or []))))
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FormSaathi filled form &mdash; %s</title>
<style>
body{font-family:Georgia,'Times New Roman',serif;color:#1a1a1a;margin:0 auto;
max-width:760px;padding:16px;line-height:1.5}
.banner{padding:12px 16px;border:2px solid #333;margin:0 0 16px}
.banner.ok{background:#e6f4ea}.banner.warn{background:#fef7e0}
.banner.bad{background:#fce8e6}.banner.info{background:#e8f0fe}
h1{font-size:1.5rem;margin:0 0 4px}h2{font-size:1.15rem;margin:24px 0 8px}
h3{font-size:1rem;margin:0 0 4px}
.field{border-top:1px solid #999;padding:10px 0}
.field.missing{color:#555}.novalue{font-style:italic}
.value{font-size:1.1rem;font-weight:bold;margin:4px 0}
.src{font-size:.9rem;color:#222}.crop{max-width:100%%;border:1px solid #666;
margin-top:8px}
ul.warn{background:#fef7e0;padding:12px 12px 12px 28px}
@media print{.noprint{display:none}}
</style>
</head>
<body>
<p class="noprint"><a href="/">Back to console</a></p>
<h1>%s</h1>
<p>Case %s &middot; language %s</p>
%s
<h2>Filled fields</h2>
%s
<h2>Discrepancies</h2>
%s
<h2>Scheme verdicts</h2>
<ul>%s</ul>
</body>
</html>""" % (
        _esc(record.case_id), _esc(form.get("title", record.form_id)),
        _esc(record.case_id), _esc(record.language), banner,
        "\n".join(rows) or "<p>No fields filled yet.</p>",
        ("<ul class='warn'>%s</ul>" % "\n".join(discs)) if discs
        else "<p>None flagged.</p>",
        "\n".join(schemes) or "<li>No scheme verdicts yet.</li>",
    )
