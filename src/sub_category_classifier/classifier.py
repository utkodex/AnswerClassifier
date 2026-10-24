"""Given a category and a question, jev picks the sub-category (profile field key).

    SubCategoryClassifier().classify("personal", "What is your name").subcategory  # -> "full_name"

The question goes into jev's *state*; one `Choice` question whose criteria are the
sub-category descriptions of that category asks jev which one fits. Many questions,
even from different categories, go in one API call.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from typesafe_sdk import Choice, TypeSafeClient

from .subcategories import SUBCATEGORIES, resolve_category

DEFAULT_MODEL = "jev-latest"
MODEL_ENV_VARS = ("SUB_CATEGORY_CLASSIFIER_MODEL", "CATEGORY_CLASSIFIER_MODEL", "JOBANSWER_JEV_MODEL", "TYPESAFE_DEFAULT_MODEL")
REVIEW_THRESHOLD = 0.5
MAX_BATCH = 20


@dataclass
class SubClassification:
    """The sub-category jev chose for one (category, question) pair."""

    question: str
    category: str
    subcategory: str
    confidence: float
    probabilities: dict[str, float] = field(default_factory=dict)
    model: str = ""
    id: str | None = None

    @property
    def needs_review(self) -> bool:
        return self.confidence < REVIEW_THRESHOLD or self.subcategory == "other"

    @property
    def path(self) -> str:
        """Profile path, e.g. 'personal.full_name'."""
        return f"{self.category}.{self.subcategory}"

    def top(self, n: int = 3) -> list[tuple[str, float]]:
        return sorted(self.probabilities.items(), key=lambda kv: kv[1], reverse=True)[:n]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["path"] = self.path
        d["needs_review"] = self.needs_review
        return d


def _load_env() -> None:
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


class SubCategoryClassifier:
    """`client` can be any object with `system_one(state, questions, model=...)` (for tests)."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        model: str | None = None,
        subcategories: Mapping[str, Mapping[str, str]] | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
    ) -> None:
        _load_env()
        self.subcategories: dict[str, dict[str, str]] = {k: dict(v) for k, v in (subcategories or SUBCATEGORIES).items()}
        self.model = _resolve_model(model)
        if client is None:
            key = api_key or os.environ.get("TYPESAFE_API_KEY", "").strip()
            if not key:
                raise RuntimeError("TYPESAFE_API_KEY is not set; put it in .env or pass api_key=")
            client = TypeSafeClient(api_key=key, model=self.model, timeout=timeout)
        self.client = client

    # ---- public API -----------------------------------------------------------------

    def classify(self, category: str, question: str, *, options: Sequence[str] | None = None,
                 context: str | None = None) -> SubClassification:
        return self.classify_many([{"category": category, "question": question,
                                    "options": list(options or []), "context": context}])[0]

    def classify_many(self, items: Iterable[Mapping[str, Any]]) -> list[SubClassification]:
        """Each item: {category, question, options?, context?, id?}."""
        norm = [self._normalize(it) for it in items]
        out: list[SubClassification] = []
        for start in range(0, len(norm), MAX_BATCH):
            out.extend(self._classify_batch(norm[start : start + MAX_BATCH]))
        return out

    def labels(self, category: str) -> dict[str, str]:
        return self.subcategories[self._category(category)]

    # ---- internals --------------------------------------------------------------------

    def _category(self, name: str) -> str:
        key = name.strip().lower().replace("-", "_").replace(" ", "_")
        if key not in self.subcategories:
            key = resolve_category(name)
        if key not in self.subcategories:
            raise KeyError(f"no sub-categories defined for {name!r}")
        return key

    def _normalize(self, it: Mapping[str, Any]) -> dict[str, Any]:
        text = it.get("question") or it.get("text") or it.get("label") or ""
        return {
            "category": self._category(str(it.get("category", ""))),
            "question": str(text).strip(),
            "options": [str(o) for o in (it.get("options") or [])],
            "context": it.get("context"),
            "id": it.get("id"),
        }

    def _state(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        qs: dict[str, Any] = {}
        for i, it in enumerate(items):
            entry: dict[str, Any] = {"question": it["question"], "category": it["category"]}
            if it["options"]:
                entry["options"] = it["options"]
            if it["context"]:
                entry["job_context"] = it["context"]
            qs[f"q{i}"] = entry
        return {
            "task": "Each entry under 'questions' is a field from a job-application form, already "
                    "assigned to a category. Decide which sub-category (profile field) each one maps to.",
            "questions": qs,
        }

    def _questions(self, items: list[dict[str, Any]]) -> dict[str, Choice]:
        return {
            f"q{i}": Choice(
                instructions=f'Form field q{i} ("{it["question"]}") is in category "{it["category"]}". '
                             f"Which sub-category does it map to?",
                criteria=self.subcategories[it["category"]],
            )
            for i, it in enumerate(items)
        }

    def _classify_batch(self, items: list[dict[str, Any]]) -> list[SubClassification]:
        if not items:
            return []
        res = self.client.system_one(self._state(items), self._questions(items), model=self.model)
        model_name = getattr(res, "model", "") or self.model
        out: list[SubClassification] = []
        for i, it in enumerate(items):
            ans = res.choices[f"q{i}"]
            out.append(
                SubClassification(
                    question=it["question"],
                    category=it["category"],
                    subcategory=ans.choice,
                    confidence=float(ans.confidence),
                    probabilities={k: float(v) for k, v in ans.probabilities.items()},
                    model=model_name,
                    id=it["id"],
                )
            )
        return out


_default: SubCategoryClassifier | None = None


def _shared() -> SubCategoryClassifier:
    global _default
    if _default is None:
        _default = SubCategoryClassifier()
    return _default


def classify(category: str, question: str, **kw: Any) -> SubClassification:
    """Module-level shortcut reusing one classifier: classify("personal", "What is your name")."""
    return _shared().classify(category, question, **kw)


def classify_many(items: Iterable[Mapping[str, Any]]) -> list[SubClassification]:
    return _shared().classify_many(items)


def dumps(results: Sequence[SubClassification]) -> str:
    return json.dumps([r.to_dict() for r in results] if len(results) != 1 else results[0].to_dict(),
                      indent=2, ensure_ascii=False)
