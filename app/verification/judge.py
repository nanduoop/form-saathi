"""Spark judge: re-checks claimed values against crops and transcripts."""
import json
from typing import Any, Dict, List

import meta_client

DOC_SYSTEM = (
    "You verify scholarship form values against a document photo. "
    "Reply with exactly one JSON object, no other text."
)

SPEECH_SYSTEM = (
    "You verify scholarship form values against what the applicant said. "
    "Numbers may be spoken as Hindi or Kannada words "
    "(for example 'ek lakh bees hazaar' means 120000). "
    "Reply with exactly one JSON object, no other text."
)


def _verdict(item):
    # type: (Dict[str, Any]) -> str
    if not isinstance(item, dict):
        return "mismatch"
    v = item.get("verdict")
    if isinstance(v, bool):
        return "ok" if v else "mismatch"
    if v is None:
        for key in ("supported", "ok", "match"):
            if key in item and isinstance(item[key], bool):
                return "ok" if item[key] else "mismatch"
        return "mismatch"
    s = str(v).strip().lower()
    if s in ("ok", "match", "supported", "correct", "true"):
        return "ok"
    if s in ("unsupported", "unclear", "unverifiable", "not_visible"):
        return "unsupported"
    return "mismatch"


def _to_problems(data, origin):
    # type: (Any, str) -> List[Dict[str, Any]]
    problems = []  # type: List[Dict[str, Any]]
    results = (data.get("results") if isinstance(data, dict) else None) or []
    for item in results:
        if not isinstance(item, dict) or not item.get("field_id"):
            continue
        verdict = _verdict(item)
        if verdict == "ok":
            continue
        code = "UNSUPPORTED" if verdict == "unsupported" else "JUDGE_MISMATCH"
        detail = str(item.get("detail") or verdict)
        problems.append({"code": code, "field_id": item.get("field_id"),
                         "detail": "%s %s: %s"
                         % (origin, item.get("field_id"), detail)})
    return problems


def judge_documents(record):
    # type: (Any) -> List[Dict[str, Any]]
    """One Spark call per cited document crop; claims must match the image."""
    problems = []  # type: List[Dict[str, Any]]
    by_doc = {}  # type: Dict[str, List[Dict[str, Any]]]
    for fid, entry in (record.fields or {}).items():
        source = (entry or {}).get("source") or {}
        if source.get("type") == "document" and source.get("doc_id"):
            by_doc.setdefault(source["doc_id"], []).append({
                "field_id": fid, "value": entry.get("value"),
                "quote": source.get("quote")})
    for doc_id, claims in by_doc.items():
        doc = record.doc(doc_id)
        if doc is None or doc.get("rejected"):
            continue
        prompt = (
            "Check each claimed value against this document image.\n"
            "For every claim say whether the image shows that value "
            "(ok), shows a different value (mismatch), or the value "
            "cannot be verified from this image (unsupported).\n"
            "Claims: %s\n"
            "Reply with exactly one JSON object like "
            '{"results": [{"field_id": ..., "verdict": '
            '"ok"|"mismatch"|"unsupported", "detail": "..."}]}.'
            % json.dumps(claims, ensure_ascii=False))
        msg = meta_client.chat(prompt, image_path=doc.get("crop"),
                               system=DOC_SYSTEM)
        data = meta_client.parse_json(msg.content or "")
        problems.extend(_to_problems(data, "document %s" % doc_id))
    return problems


def judge_speech(record):
    # type: (Any) -> List[Dict[str, Any]]
    """One text call for all speech-sourced fields against the transcripts."""
    claims = []  # type: List[Dict[str, Any]]
    for fid, entry in (record.fields or {}).items():
        source = (entry or {}).get("source") or {}
        if source.get("type") != "applicant":
            continue
        said = [u.get("text", "") for u in record.utterances or []
                if u.get("id") == source.get("utterance_id")]
        claims.append({"field_id": fid, "value": entry.get("value"),
                       "transcript": " ".join(said)})
    if not claims:
        return []
    prompt = (
        "Compare each claimed field value with what the applicant said. "
        "Numbers may be spoken as Hindi or Kannada words.\n"
        "For every claim say whether the transcript supports that value "
        "(ok), contradicts it (mismatch), or does not mention it "
        "(unsupported).\n"
        "Claims: %s\n"
        "Reply with exactly one JSON object like "
        '{"results": [{"field_id": ..., "verdict": '
        '"ok"|"mismatch"|"unsupported", "detail": "..."}]}.'
        % json.dumps(claims, ensure_ascii=False))
    msg = meta_client.chat(prompt, system=SPEECH_SYSTEM)
    data = meta_client.parse_json(msg.content or "")
    return _to_problems(data, "speech")


def judge_fields(record):
    # type: (Any) -> List[Dict[str, Any]]
    """Judge every sourced field; return problems (empty when clean)."""
    problems = judge_documents(record)
    problems.extend(judge_speech(record))
    return problems
