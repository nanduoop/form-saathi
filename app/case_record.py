"""Everything the agent knows about one application. Saved to disk every turn."""

import json
import os

FORMS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "forms")


def load_form(form_id="post_matric_scholarship"):
    with open(os.path.join(FORMS_DIR, f"{form_id}.json")) as f:
        return json.load(f)


class CaseRecord:
    def __init__(self, case_id="case1", form_id="post_matric_scholarship", language="hi"):
        self.case_id = case_id
        self.form_id = form_id
        self.language = language
        self.photos = []           # uploaded photo paths
        self.scanned_photos = []   # photo indices already segmented
        self.documents = []        # {id, photo, box, crop, doc_type, holder_name, fields:[{key,value,quote}]}
        self.utterances = []       # {id, text, audio, question_id}
        self.questions = []        # {id, field_ids, question_en, question_local, answered}
        self.fields = {}           # field_id -> {value, source:{type, doc_id|utterance_id, quote}}
        self.discrepancies = []    # {id, field_id, detail}
        self.eligibility = None    # {eligible, reasons, checked_values}
        self.status = "open"
        self.refusals = 0
        self.ineligible_reason = None
        # multi-agent pipeline
        self.stage = "intake"      # intake -> profile -> scout -> research -> form -> plan -> done
        self.log = []              # [{agent, message, data}]
        self.profile = None
        self.schemes = []          # scout verdicts
        self.research = {}         # scheme_id -> verified facts
        self.plan = None
        self.photo_requests = []   # capture coach: {doc_id, advice_en, advice_local, answered}
        self._n = {"doc": 0, "utt": 0, "q": 0, "disc": 0}

    @property
    def form(self):
        return load_form(self.form_id)

    def _next(self, kind, prefix):
        self._n[kind] += 1
        return f"{prefix}{self._n[kind]}"

    def add_photo(self, path):
        self.photos.append(path)
        return len(self.photos) - 1

    def add_document(self, photo, box, crop):
        doc = {"id": self._next("doc", "d"), "photo": photo, "box": box, "crop": crop,
               "doc_type": None, "holder_name": None, "fields": []}
        self.documents.append(doc)
        return doc["id"]

    def doc(self, doc_id):
        return next((d for d in self.documents if d["id"] == doc_id), None)

    def add_question(self, field_ids, question_en, question_local):
        q = {"id": self._next("q", "q"), "field_ids": list(field_ids), "question_en": question_en,
             "question_local": question_local, "answered": False}
        self.questions.append(q)
        return q["id"]

    def open_question(self):
        return next((q for q in self.questions if not q["answered"]), None)

    def add_utterance(self, text, audio=None):
        q = self.open_question()
        u = {"id": self._next("utt", "u"), "text": text, "audio": audio,
             "question_id": q["id"] if q else None}
        if q:
            q["answered"] = True
        self.utterances.append(u)
        return u["id"]

    def utterance(self, utt_id):
        return next((u for u in self.utterances if u["id"] == utt_id), None)

    def add_discrepancy(self, field_id, detail):
        d = {"id": self._next("disc", "x"), "field_id": field_id, "detail": detail}
        self.discrepancies.append(d)
        return d["id"]

    def to_dict(self):
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d):
        r = cls(d["case_id"], d.get("form_id", "post_matric_scholarship"), d.get("language", "hi"))
        for k, v in d.items():  # unknown keys from older states are kept too
            setattr(r, k, v)
        return r
