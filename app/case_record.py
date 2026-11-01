"""Case record: the single state object the FormSaathi agent works on.

JSON-serialisable via to_dict/from_dict. The agent persists the record plus
its turn history to app/state/<case_id>.json after every turn.
"""
import os
from typing import Any, Dict, List, Optional

STATUSES = ("open", "needs_input", "awaiting_signoff", "escalated", "ineligible")

LANGUAGES = ("hi", "kn", "mr", "te", "ta", "bn", "en")


def state_dir(case_id):
    # type: (str) -> str
    """Absolute directory for a case's runtime state (state file + crops)."""
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
    return os.path.join(base, str(case_id))


class CaseRecord(object):
    """One scholarship application case."""

    def __init__(self, case_id="case", language="hi",
                 form_id="post_matric_scholarship"):
        # type: (str, str, str) -> None
        self.case_id = case_id
        self.language = language
        self.form_id = form_id
        self.photos = []  # type: List[str]
        self.scanned_photos = []  # type: List[str]
        # documents: [{id d1.., photo, photo_index, box, crop, doc_type,
        #   holder_name, fields:[{key,value,quote}], quality, unreadable,
        #   sam_found, cut_edges, area_ratio, rejected}]
        self.documents = []  # type: List[Dict[str, Any]]
        # utterances: [{id u1.., text, audio, question_id}]
        self.utterances = []  # type: List[Dict[str, Any]]
        # questions: [{id q1.., field_ids, question_en, question_local,
        #   answered}]
        self.questions = []  # type: List[Dict[str, Any]]
        # fields: {field_id: {value, source:{type:"document",doc_id,quote} |
        #   {type:"applicant",utterance_id}}}
        self.fields = {}  # type: Dict[str, Dict[str, Any]]
        # discrepancies: [{id, field_id (a field id or "doc:<id>"), detail}]
        self.discrepancies = []  # type: List[Dict[str, Any]]
        self.eligibility = None  # type: Optional[Dict[str, Any]]
        self.status = "open"
        self.refusals = []  # type: List[Dict[str, Any]]
        # pipeline fields (later stages own most of these)
        self.stage = "collect"
        self.log = []  # type: List[str]
        self.profile = None  # type: Optional[Dict[str, Any]]
        self.schemes = []  # type: List[Any]
        self.research = None  # type: Optional[Dict[str, Any]]
        self.plan = None  # type: Optional[Dict[str, Any]]
        self.photo_requests = []  # type: List[Any]

    def add_log(self, message):
        # type: (str) -> None
        self.log.append(str(message))

    def doc(self, doc_id):
        # type: (str) -> Optional[Dict[str, Any]]
        for d in self.documents:
            if d.get("id") == doc_id:
                return d
        return None

    def to_dict(self):
        # type: () -> Dict[str, Any]
        return {
            "case_id": self.case_id,
            "language": self.language,
            "form_id": self.form_id,
            "photos": list(self.photos),
            "scanned_photos": list(self.scanned_photos),
            "documents": [dict(d) for d in self.documents],
            "utterances": [dict(u) for u in self.utterances],
            "questions": [dict(q) for q in self.questions],
            "fields": {k: dict(v) for k, v in self.fields.items()},
            "discrepancies": [dict(d) for d in self.discrepancies],
            "eligibility": dict(self.eligibility) if self.eligibility else None,
            "status": self.status,
            "refusals": [dict(r) for r in self.refusals],
            "stage": self.stage,
            "log": list(self.log),
            "profile": self.profile,
            "schemes": list(self.schemes),
            "research": self.research,
            "plan": self.plan,
            "photo_requests": list(self.photo_requests),
        }

    @classmethod
    def from_dict(cls, data):
        # type: (Dict[str, Any]) -> "CaseRecord"
        rec = cls(
            case_id=str(data.get("case_id", "case")),
            language=str(data.get("language", "hi")),
            form_id=str(data.get("form_id", "post_matric_scholarship")),
        )
        rec.photos = list(data.get("photos") or [])
        rec.scanned_photos = list(data.get("scanned_photos") or [])
        rec.documents = [dict(d) for d in (data.get("documents") or [])]
        rec.utterances = [dict(u) for u in (data.get("utterances") or [])]
        rec.questions = [dict(q) for q in (data.get("questions") or [])]
        rec.fields = {k: dict(v) for k, v in
                      ((data.get("fields") or {}).items())}
        rec.discrepancies = [dict(d) for d in
                             (data.get("discrepancies") or [])]
        elig = data.get("eligibility")
        rec.eligibility = dict(elig) if elig else None
        rec.status = str(data.get("status", "open"))
        rec.refusals = [dict(r) for r in (data.get("refusals") or [])]
        rec.stage = str(data.get("stage", "collect"))
        rec.log = list(data.get("log") or [])
        rec.profile = data.get("profile")
        rec.schemes = list(data.get("schemes") or [])
        rec.research = data.get("research")
        rec.plan = data.get("plan")
        rec.photo_requests = list(data.get("photo_requests") or [])
        return rec
