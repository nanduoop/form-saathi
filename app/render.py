"""Printable filled form with an evidence trail for every field."""

import html

from case_record import load_form


def _e(s):
    return html.escape(str(s if s is not None else ""))


def render_form(state):
    rec = state["record"]
    form = load_form(rec.get("form_id", "post_matric_scholarship"))
    cid = rec["case_id"]
    docs = {d["id"]: d for d in rec.get("documents", [])}
    utts = {u["id"]: u for u in rec.get("utterances", [])}
    disc = {}
    for d in rec.get("discrepancies", []):
        disc.setdefault(d["field_id"], []).append(d["detail"])
    rows = []
    for f in form["fields"]:
        entry = rec.get("fields", {}).get(f["id"])
        if not entry:
            rows.append(f"<tr class='empty'><th>{_e(f['label'])}</th><td>—</td><td>not filled</td></tr>")
            continue
        src = entry.get("source", {})
        if src.get("type") == "document":
            d = docs.get(src.get("doc_id"), {})
            ev = (f"<img src='/cases/{_e(cid)}/crop/{_e(src.get('doc_id'))}' alt=''>"
                  f"<div><b>{_e(d.get('doc_type', '').replace('_', ' '))}</b> ({_e(src.get('doc_id'))})<br>"
                  f"<q>{_e(src.get('quote'))}</q></div>")
        else:
            u = utts.get(src.get("utterance_id"), {})
            ev = f"<div><b>applicant said</b> ({_e(src.get('utterance_id'))})<br><q>{_e(u.get('text'))}</q></div>"
        warn = "".join(f"<div class='warn'>⚠ {_e(x)}</div>" for x in disc.get(f["id"], []))
        rows.append(f"<tr><th>{_e(f['label'])}</th><td class='val'>{_e(entry['value'])}{warn}</td>"
                    f"<td class='ev'>{ev}</td></tr>")
    doc_warn = "".join(f"<li>{_e(x)}</li>" for k, v in disc.items() if k.startswith("doc:") for x in v)
    status = state.get("status")
    banner = {"awaiting_signoff": "Every field proven. Waiting for the applicant to confirm.",
              "confirmed": f"Confirmed by the applicant at {_e(rec.get('confirmed_at'))}.",
              "escalated": "Sent to a human helper after 3 refusals.",
              "ineligible": "Not eligible."}.get(status, f"Status: {_e(status)}")
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{_e(form['title'])} · {_e(cid)}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{font-family:system-ui,sans-serif;margin:24px auto;max-width:1000px;padding:0 16px;color:#111;background:#fff}}
h1{{font-size:22px;margin:0}} .note{{color:#666;font-size:12px}}
.banner{{padding:10px 14px;border-radius:8px;background:#eef6ee;margin:14px 0;font-weight:600}}
table{{border-collapse:collapse;width:100%}} th,td{{border-bottom:1px solid #ddd;padding:8px;vertical-align:top;text-align:left}}
th{{width:24%;font-weight:600}} .val{{font-family:ui-monospace,monospace;width:28%}}
.ev{{display:flex;gap:10px;align-items:flex-start;font-size:13px}} .ev img{{max-width:140px;max-height:90px;border:1px solid #ccc}}
q{{color:#333}} .warn{{color:#a15c00;font-family:system-ui;font-size:12px;margin-top:4px}} tr.empty td{{color:#b00}}
.docwarn{{background:#fff4e0;border-radius:8px;padding:8px 14px;margin:10px 0}}
@media print{{.ev img{{max-width:100px}}}}
</style></head><body>
<h1>{_e(form['title'])}</h1><div class="note">Case {_e(cid)} · prepared by FormSaathi · {_e(form['note'])}</div>
<div class="banner">{banner}</div>
{f'<div class="docwarn"><b>Fix before the office visit:</b><ul>{doc_warn}</ul></div>' if doc_warn else ''}
<table><tr><th>Field</th><th>Value</th><th>Evidence</th></tr>{''.join(rows)}</table>
</body></html>"""
