"""Data types shared by the jobanswer package."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Question:
    """One form field: free text, single-choice or multi-choice."""

    text: str
    options: list[str] = field(default_factory=list)
    multi: bool = False
    qtype: str | None = None  # text | textarea | single | multi | boolean
    id: str | None = None
    context: str | None = None

    TYPE_ALIASES = {"select": "single", "radio": "single", "dropdown": "single", "single": "single",
                    "multiselect": "multi", "checkbox": "multi", "checkboxes": "multi", "multi": "multi",
                    "textarea": "textarea", "text": "text", "input": "text", "number": "text", "date": "text",
                    "email": "text", "tel": "text", "url": "text", "boolean": "boolean", "yesno": "boolean"}

    @classmethod
    def from_dict(cls, d: dict[str, Any], context: str | None = None) -> "Question":
        """Build from the JSON a form filler sends: {id?, question|text|label, options?, multi?, type?, context?}."""
        t = str(d.get("type") or "").lower().strip()
        qtype = cls.TYPE_ALIASES.get(t, t or None)
        options = [str(o) for o in (d.get("options") or []) if str(o).strip()]
        return cls(
            text=str(d.get("question") or d.get("text") or d.get("label") or "").strip(),
            options=options,
            multi=bool(d.get("multi")) or qtype == "multi",
            qtype=qtype,
            id=str(d["id"]) if d.get("id") is not None else None,
            context=d.get("context") or context,
        )

    @property
    def kind(self) -> str:
        """multi | single | boolean | essay | text."""
        if self.options:
            return "multi" if (self.multi or self.qtype == "multi") else "single"
        if self.qtype == "boolean":
            return "boolean"
        if self.qtype == "textarea":
            return "essay"
        return "text"

    @property
    def choices(self) -> list[str]:
        """Options to pick from; a boolean field without options becomes Yes/No."""
        if self.options:
            return list(self.options)
        if self.qtype == "boolean":
            return ["Yes", "No"]
        return []


@dataclass
class Fact:
    """What the profile says about a question, in every shape an option mapper may need."""

    text: str | None = None            # short answer to type into a text field
    boolean: bool | None = None        # yes/no polarity
    number: float | None = None        # numeric value (years, days, inr, usd)
    number_max: float | None = None    # upper bound when the answer is a range
    unit: str | None = None            # years | days | inr | usd
    items: list[str] = field(default_factory=list)      # values to tick in a multi-select
    keywords: list[str] = field(default_factory=list)   # phrases that identify the right option
    fallbacks: list[str] = field(default_factory=list)  # phrases to try when nothing else matches
    long: str | None = None            # sentence form, for textarea fields
    rule: str = ""
    confidence: float = 0.9
    needs_review: bool = False
    reasoning: str = ""
    essay: bool = False                # free-text question that needs writing, not a lookup

    def short(self) -> str:
        if self.text is not None:
            return self.text
        if self.boolean is not None:
            return "Yes" if self.boolean else "No"
        if self.items:
            return ", ".join(self.items)
        if self.number is not None:
            n = self.number
            return str(int(n)) if float(n).is_integer() else str(n)
        return ""


@dataclass
class Answer:
    question: str
    answer: str = ""
    selected_options: list[str] = field(default_factory=list)
    confidence: float = 0.0
    source: str = "none"               # jev | rule | profile | llm | none
    probabilities: dict[str, float] = field(default_factory=dict)
    model: str = ""
    rule: str = ""
    reasoning: str = ""
    needs_review: bool = True
    id: str | None = None
    category: str | None = None
    subcategory: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
