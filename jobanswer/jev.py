"""jev (TypeSafe decision model) answers option questions straight from the profile.

The whole profile is the model's *state* together with a short answering policy. Every
single-choice question becomes one `Choice` (labels o0..oN -> option text); every
multi-choice question becomes one `Noul` per option, ticked when P(yes) >= 0.5.
Many questions go in one API call.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Sequence

from .models import Question

DEFAULT_MODEL = "jev-latest"
MODEL_ENV_VARS = ("JOBANSWER_JEV_MODEL", "CATEGORY_CLASSIFIER_MODEL", "TYPESAFE_DEFAULT_MODEL")
MAX_ITEMS = 24  # Choice + Noul questions per request

POLICY = [
    "Answer every form field exactly as the applicant described in 'applicant_profile' would.",
    "Pick the option that is TRUE for the applicant. Never pick 'decline to answer' / 'prefer not to say' style options.",
    "Work arrangement: remote. Hybrid or onsite only if the job is in Delhi NCR (Delhi, Gurugram, Noida, Ghaziabad, Faridabad) or Lucknow.",
    "Relocation: answer No to any relocation question, including a plain 'Are you willing to relocate?'. "
    "The only exception is when the question itself names Delhi NCR or Lucknow; then answer Yes.",
    "Authorized to work only in India. Any role outside India needs visa sponsorship (answer Yes to sponsorship questions).",
    "Relatives at the company, non-compete, government procurement, referral, previously worked here: No.",
    "How did you hear about the job: LinkedIn. Security clearance: Yes. Willing to travel up to 20%: Yes.",
    "Salary: current 9 LPA INR. Expected 24 LPA INR in India; 72,000-120,000 USD (60 LPA-1 Cr INR) outside India.",
    "Notice period 1 month (30 days); can start about 30 days after the offer. Not an immediate joiner.",
    "Employment types: full-time, contract, freelance (not part-time, not internship).",
    "US/Canada state lists without Indian states: choose 'Foreign Countries' / 'Outside US' / 'Other'.",
]


@dataclass
class JevResult:
    selected: list[str]
    probabilities: dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0
    model: str = ""


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover
        return
    from pathlib import Path

    for p in (Path.cwd() / ".env", Path(__file__).resolve().parents[1] / ".env"):
        if p.is_file():
            load_dotenv(p, override=False)


def resolve_model(model: str | None) -> str:
    if model:
        return model
    for var in MODEL_ENV_VARS:
        v = os.environ.get(var, "").strip()
        if v:
            return v
    return DEFAULT_MODEL


def has_key() -> bool:
    _load_env()
    return bool(os.environ.get("TYPESAFE_API_KEY", "").strip())


class JevAnswerer:
    """`client` can be any object with `system_one(state, questions, model=...)` (for tests)."""

    def __init__(self, profile: dict[str, Any], *, client: Any | None = None, model: str | None = None,
                 api_key: str | None = None, timeout: float | None = None) -> None:
        _load_env()
        self.profile = profile
        self.model = resolve_model(model)
        if client is None:
            from typesafe_sdk import TypeSafeClient

            key = api_key or os.environ.get("TYPESAFE_API_KEY", "").strip()
            if not key:
                raise RuntimeError("TYPESAFE_API_KEY is not set; put it in .env or pass api_key=")
            client = TypeSafeClient(api_key=key, model=self.model, timeout=timeout)
        self.client = client

    def answer_many(self, questions: Sequence[Question]) -> list[JevResult | None]:
        """One result per question (None for questions without options)."""
        out: list[JevResult | None] = [None] * len(questions)
        batch: list[tuple[int, Question]] = []
        items = 0
        for i, q in enumerate(questions):
            n = len(q.choices)
            if n == 0:
                continue
            cost = n if q.kind == "multi" else 1
            if batch and items + cost > MAX_ITEMS:
                self._run(batch, out)
                batch, items = [], 0
            batch.append((i, q))
            items += cost
        if batch:
            self._run(batch, out)
        return out

    # ---- internals --------------------------------------------------------------------

    def _run(self, batch: list[tuple[int, Question]], out: list[JevResult | None]) -> None:
        from typesafe_sdk import Choice, Noul

        state: dict[str, Any] = {"applicant_profile": self.profile, "answering_policy": POLICY, "form_fields": {}}
        questions: dict[str, Any] = {}
        for k, (_, q) in enumerate(batch):
            name = f"q{k}"
            entry: dict[str, Any] = {"question": q.text, "options": q.choices, "select": "many" if q.kind == "multi" else "one"}
            if q.context:
                entry["job_context"] = q.context
            state["form_fields"][name] = entry
            if q.kind == "multi":
                for j, opt in enumerate(q.choices):
                    questions[f"{name}_o{j}"] = Noul(
                        instructions=f'Form field {name} ("{q.text}") allows several options. '
                                     f'Should the option "{opt}" be ticked for this applicant?',
                        criteria={"true": "the option is true for the applicant and they would want it ticked",
                                  "false": "the option is not true for the applicant"},
                    )
            else:
                questions[name] = Choice(
                    instructions=f'Which option should the applicant select for form field {name} ("{q.text}")?',
                    criteria={f"o{j}": opt for j, opt in enumerate(q.choices)},
                )
        res = self.client.system_one(state, questions, model=self.model)
        model_name = getattr(res, "model", "") or self.model
        for k, (idx, q) in enumerate(batch):
            name = f"q{k}"
            opts = q.choices
            if q.kind == "multi":
                probs: dict[str, float] = {}
                for j, opt in enumerate(opts):
                    ans = res.nouls.get(f"{name}_o{j}")
                    probs[opt] = float(ans.noul) if ans is not None else 0.0
                selected = [o for o, p in probs.items() if p >= 0.5]
                certainty = [abs(p - 0.5) * 2 for p in probs.values()]
                conf = sum(certainty) / len(certainty) if certainty else 0.0
                out[idx] = JevResult(selected=selected, probabilities=probs, confidence=round(conf, 3), model=model_name)
            else:
                ans = res.choices[name]
                probs = {opts[int(lbl[1:])]: float(p) for lbl, p in ans.probabilities.items() if lbl.startswith("o")}
                chosen = opts[int(ans.choice[1:])]
                out[idx] = JevResult(selected=[chosen], probabilities=probs, confidence=round(float(ans.confidence), 3), model=model_name)
