#!/usr/bin/env python
"""HTTP API for form fillers: send form fields, get back what to type or which options to click.

    python api.py                      # http://127.0.0.1:8765  (docs at /docs)
    JOBANSWER_PORT=9000 python api.py
    JOBANSWER_API_KEY=secret python api.py   # then send header  X-API-Key: secret

Endpoints
    GET  /health            liveness + which engines are on
    POST /answer            one field  -> one answer
    POST /answers           many fields (one form) -> answers, one jev call for all option fields

The request / response contract is documented in API.md and served live at /docs and /openapi.json.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jobanswer import Answer, Engine, Question  # noqa: E402

API_VERSION = "1.0.0"
DEFAULT_PORT = 8765

app = FastAPI(
    title="jobanswer API",
    version=API_VERSION,
    description="Answers job-application form fields from the applicant's profile. "
                "Free-text fields get a short answer to type; choice fields get the exact option string(s) to select.",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

ENGINES: dict[str, Engine] = {}


def get_engine(rules_only: bool = False) -> Engine:
    key = "rules" if rules_only else "full"
    if key not in ENGINES:
        ENGINES[key] = Engine(use_jev="never", use_llm="never") if rules_only else Engine()
    return ENGINES[key]


def require_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = os.environ.get("JOBANSWER_API_KEY", "").strip()
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="invalid or missing X-API-Key header")


# ---- schemas -------------------------------------------------------------------------------

class QuestionIn(BaseModel):
    """One form field as the form filler sees it."""

    id: str | int | None = Field(default=None, description="Your own id for the field (echoed back).")
    question: str = Field(description="The field's label / question text as shown on the form.")
    options: list[str] = Field(default_factory=list, description="Exact option strings for select / radio / checkbox fields.")
    multi: bool = Field(default=False, description="True when several options may be selected.")
    type: str | None = Field(default=None, description="Field type: text, textarea, select, radio, dropdown, multiselect, checkbox, boolean. Optional.")
    context: str | None = Field(default=None, description="Job context, e.g. 'Senior ML Engineer, Acme, Berlin'. Overrides the batch context.")

    @model_validator(mode="before")
    @classmethod
    def _accept_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict) and "question" not in data:
            for k in ("text", "label", "name"):
                if data.get(k):
                    data = {**data, "question": data[k]}
                    break
        return data


class AnswerRequest(QuestionIn):
    rules_only: bool = Field(default=False, description="Skip jev and Claude; deterministic rules only (offline).")


class BatchRequest(BaseModel):
    questions: list[QuestionIn] = Field(description="Every field of the form, in page order.")
    context: str | None = Field(default=None, description="Job context applied to every field: title, company, location.")
    rules_only: bool = False


class AnswerOut(BaseModel):
    id: str | None = None
    question: str
    action: Literal["type", "select", "check", "skip"] = Field(
        description="type: put `value` into the text field. select: choose the single option in `value`. "
                    "check: tick every option in `values`. skip: nothing to fill; see `reasoning`.")
    value: str = Field(default="", description="Text to type, or the chosen option (options joined by '; ' for check).")
    values: list[str] = Field(default_factory=list, description="Exact option strings to select (empty for text fields).")
    confidence: float
    needs_review: bool = Field(description="True when a human should look before submitting.")
    source: str = Field(description="rule | profile | jev | llm | none")
    rule: str = ""
    reasoning: str = ""
    probabilities: dict[str, float] = Field(default_factory=dict, description="Option -> probability when jev answered.")
    model: str = ""
    category: str | None = None
    subcategory: str | None = None


class BatchResponse(BaseModel):
    answers: list[AnswerOut]
    count: int
    review_count: int
    engine: str


class Health(BaseModel):
    status: str
    version: str
    engine: str
    auth_required: bool


# ---- helpers -------------------------------------------------------------------------------

def to_out(q: Question, a: Answer) -> AnswerOut:
    if q.choices:
        if a.selected_options:
            action = "check" if q.kind == "multi" else "select"
        else:
            action = "skip"
    else:
        action = "type" if a.answer else "skip"
    return AnswerOut(
        id=a.id, question=a.question, action=action,
        value=a.answer if action != "skip" else "",
        values=list(a.selected_options), confidence=round(a.confidence, 3), needs_review=a.needs_review,
        source=a.source, rule=a.rule, reasoning=a.reasoning, probabilities=a.probabilities, model=a.model,
        category=a.category, subcategory=a.subcategory,
    )


def _questions(items: list[QuestionIn], context: str | None) -> list[Question]:
    qs = [Question.from_dict(it.model_dump(), context=context) for it in items]
    for i, q in enumerate(qs):
        if not q.text:
            raise HTTPException(status_code=422, detail=f"questions[{i}] has no question text")
    return qs


# ---- routes --------------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def root() -> dict[str, Any]:
    return {"service": "jobanswer", "version": API_VERSION, "docs": "/docs", "endpoints": ["/health", "/answer", "/answers"]}


@app.get("/health", response_model=Health)
def health() -> Health:
    return Health(status="ok", version=API_VERSION, engine=get_engine().status(),
                  auth_required=bool(os.environ.get("JOBANSWER_API_KEY", "").strip()))


@app.post("/answer", response_model=AnswerOut, dependencies=[Depends(require_key)])
def answer(req: AnswerRequest) -> AnswerOut:
    q = _questions([req], None)[0]
    return to_out(q, get_engine(req.rules_only).answer(q))


@app.post("/answers", response_model=BatchResponse, dependencies=[Depends(require_key)])
def answers(req: BatchRequest) -> BatchResponse:
    if not req.questions:
        raise HTTPException(status_code=422, detail="questions is empty")
    qs = _questions(req.questions, req.context)
    engine = get_engine(req.rules_only)
    outs = [to_out(q, a) for q, a in zip(qs, engine.answer_many(qs))]
    return BatchResponse(answers=outs, count=len(outs), review_count=sum(o.needs_review for o in outs), engine=engine.status())


def main() -> None:
    import uvicorn

    host = os.environ.get("JOBANSWER_HOST", "127.0.0.1")
    port = int(os.environ.get("JOBANSWER_PORT", DEFAULT_PORT))
    print(f"jobanswer API on http://{host}:{port}  (docs: http://{host}:{port}/docs)")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
