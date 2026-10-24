"""Classify job-application questions into categories with jev (TypeSafe decision model).

The question text becomes jev's *state*; one `Choice` question whose criteria are the
category descriptions asks jev which category fits. Many questions go in one API call.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from typesafe_sdk import Choice, TypeSafeClient

from .categories import CATEGORIES

DEFAULT_MODEL = "jev-latest"
MODEL_ENV_VARS = ("CATEGORY_CLASSIFIER_MODEL", "JOBANSWER_JEV_MODEL", "TYPESAFE_DEFAULT_MODEL")
REVIEW_THRESHOLD = 0.5
MAX_BATCH = 20


@dataclass
class Classification:
    """The category jev chose for one question."""

    question: str
    category: str
    confidence: float
    probabilities: dict[str, float] = field(default_factory=dict)
    model: str = ""
    id: str | None = None

    @property
    def needs_review(self) -> bool:
        return self.confidence < REVIEW_THRESHOLD

    def top(self, n: int = 3) -> list[tuple[str, float]]:
        return sorted(self.probabilities.items(), key=lambda kv: kv[1], reverse=True)[:n]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["needs_review"] = self.needs_review
        return d


def _load_env() -> None:
    """Load .env from the current directory or the project root (two levels above this package)."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover
        return
    for p in (Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"):
        if p.is_file():
            load_dotenv(p, override=False)


def _resolve_model(model: str | None) -> str:
    if model:
        return model
    for var in MODEL_ENV_VARS:
        v = os.environ.get(var, "").strip()
        if v:
            return v
    return DEFAULT_MODEL


class CategoryClassifier:
    """Classify questions with jev.

    ```python
    clf = CategoryClassifier()
    clf.classify("What is your name").category   # -> "personal"
    ```

    `client` can be any object with a `system_one(state, questions, model=...)` method,
    which makes the classifier easy to test without network access.
    """

    def __init__(
        self,
        *,
        client: Any | None = None,
        model: str | None = None,
        categories: Mapping[str, str] | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
    ) -> None:
        _load_env()
        self.categories: dict[str, str] = dict(categories or CATEGORIES)
        if not self.categories:
            raise ValueError("at least one category is required")
        self.model = _resolve_model(model)
        if client is None:
            key = api_key or os.environ.get("TYPESAFE_API_KEY", "").strip()
            if not key:
                raise RuntimeError("TYPESAFE_API_KEY is not set; put it in .env or pass api_key=")
            client = TypeSafeClient(api_key=key, model=self.model, timeout=timeout)
        self.client = client

    # ---- public API -----------------------------------------------------------------

    def classify(self, question: str, *, options: Sequence[str] | None = None, context: str | None = None) -> Classification:
        return self.classify_many([{"question": question, "options": list(options or []), "context": context}])[0]

    def classify_many(self, questions: Iterable[str | Mapping[str, Any]]) -> list[Classification]:
        items = [self._normalize(q) for q in questions]
        out: list[Classification] = []
        for start in range(0, len(items), MAX_BATCH):
            out.extend(self._classify_batch(items[start : start + MAX_BATCH]))
        return out

    # ---- internals --------------------------------------------------------------------

    @staticmethod
    def _normalize(q: str | Mapping[str, Any]) -> dict[str, Any]:
        if isinstance(q, str):
            return {"question": q.strip(), "options": [], "context": None, "id": None}
        text = q.get("question") or q.get("text") or q.get("label") or ""
        return {
            "question": str(text).strip(),
            "options": [str(o) for o in (q.get("options") or [])],
            "context": q.get("context"),
            "id": q.get("id"),
        }

    def _state(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        qs: dict[str, Any] = {}
        for i, it in enumerate(items):
            entry: dict[str, Any] = {"question": it["question"]}
            if it["options"]:
                entry["options"] = it["options"]
            if it["context"]:
                entry["job_context"] = it["context"]
            qs[f"q{i}"] = entry
        return {
            "task": "Each entry under 'questions' is a field from a job-application form. "
                    "Decide which category each field belongs to.",
            "questions": qs,
        }

    def _questions(self, items: list[dict[str, Any]]) -> dict[str, Choice]:
        return {
            f"q{i}": Choice(
                instructions=f'Which category does form field q{i} ("{it["question"]}") belong to?',
                criteria=self.categories,
            )
            for i, it in enumerate(items)
        }

    def _classify_batch(self, items: list[dict[str, Any]]) -> list[Classification]:
        if not items:
            return []
        res = self.client.system_one(self._state(items), self._questions(items), model=self.model)
        model_name = getattr(res, "model", "") or self.model
        out: list[Classification] = []
        for i, it in enumerate(items):
            ans = res.choices[f"q{i}"]
            out.append(
                Classification(
                    question=it["question"],
                    category=ans.choice,
                    confidence=float(ans.confidence),
                    probabilities={k: float(v) for k, v in ans.probabilities.items()},
                    model=model_name,
                    id=it["id"],
                )
            )
        return out


_default: CategoryClassifier | None = None


def _shared() -> CategoryClassifier:
    global _default
    if _default is None:
        _default = CategoryClassifier()
    return _default


def classify(question: str, **kw: Any) -> Classification:
    """Module-level shortcut that reuses one classifier (and one HTTP client)."""
    return _shared().classify(question, **kw)


def classify_many(questions: Iterable[str | Mapping[str, Any]]) -> list[Classification]:
    return _shared().classify_many(questions)


def dumps(results: Sequence[Classification]) -> str:
    return json.dumps([r.to_dict() for r in results] if len(results) != 1 else results[0].to_dict(), indent=2, ensure_ascii=False)
