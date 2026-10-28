"""The Engine: rules -> (jev classifiers -> profile) -> option mapping, jev cross-check, Claude for essays."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterable

from . import jev as jevmod
from . import llm as llmmod
from . import matching
from .models import Answer, Fact, Question
from .profile import Profile
from .rules import ESSAY_HINT, apply_rules

ROOT = Path(__file__).resolve().parents[1]
REVIEW_THRESHOLD = 0.5


def _classifiers(client: Any | None, model: str | None):
    """(CategoryClassifier, SubCategoryClassifier) from src/, or None when jev is unavailable."""
    src = str(ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    try:
        from category_classifier import CategoryClassifier
        from sub_category_classifier import SubCategoryClassifier

        return CategoryClassifier(client=client, model=model), SubCategoryClassifier(client=client, model=model)
    except Exception:
        return None


class Engine:
    """Answer form questions from the profile.

    use_jev: "auto" (jev answers option questions and classifies unknown questions when TYPESAFE_API_KEY exists) | "never"
    use_llm: "auto" (Claude for essays and free text no rule covers when ANTHROPIC_API_KEY exists) | "always" | "never"
    """

    def __init__(self, *, profile_path: str | Path | None = None, use_jev: str = "auto", use_llm: str = "auto",
                 model: str | None = None, jev_model: str | None = None,
                 jev_client: Any | None = None, llm_client: Any | None = None) -> None:
        self.profile = Profile(profile_path)
        self.use_jev = use_jev if use_jev in ("auto", "never") else "auto"
        self.use_llm = use_llm if use_llm in ("auto", "always", "never") else "auto"
        self.jev: jevmod.JevAnswerer | None = None
        self.classifiers = None
        if self.use_jev != "never" and (jev_client is not None or jevmod.has_key()):
            try:
                self.jev = jevmod.JevAnswerer(self.profile.for_model(), client=jev_client, model=jev_model)
            except Exception:
                self.jev = None
            self.classifiers = _classifiers(jev_client, jev_model)
        self.llm: llmmod.ClaudeWriter | None = None
        if self.use_llm != "never" and (llm_client is not None or llmmod.has_key()):
            try:
                self.llm = llmmod.ClaudeWriter(self.profile.for_model(), client=llm_client, model=model)
            except Exception:
                self.llm = None

    def status(self) -> str:
        parts = ["rules"]
        parts.append(f"jev {self.jev.model}" if self.jev else "jev off")
        parts.append(f"claude {self.llm.model}" if self.llm else "claude off")
        return " + ".join(parts)

    # ---- public API ------------------------------------------------------------------

    def answer(self, q: Question) -> Answer:
        return self.answer_many([q])[0]

    def answer_many(self, questions: Iterable[Question]) -> list[Answer]:
        qs = list(questions)
        facts: list[Fact | None] = [apply_rules(self.profile, q) for q in qs]
        paths: list[tuple[str, str] | None] = [(f.rule.split(".", 1)[0], f.rule.split(".", 1)[1]) if f and "." in f.rule else None
                                              for f in facts]
        # jev classifiers for questions no rule covered
        if self.classifiers:
            self._classify_missing(qs, facts, paths)
        # jev answers every option question in one go
        jev_results: list[jevmod.JevResult | None] = [None] * len(qs)
        if self.jev:
            try:
                jev_results = self.jev.answer_many(qs)
            except Exception as e:  # network / auth problems degrade to rules only
                jev_results = [None] * len(qs)
                self._jev_error = str(e)
        return [self._compose(q, f, p, j) for q, f, p, j in zip(qs, facts, paths, jev_results)]

    # ---- internals --------------------------------------------------------------------

    def _classify_missing(self, qs: list[Question], facts: list[Fact | None], paths: list[tuple[str, str] | None]) -> None:
        cat_clf, sub_clf = self.classifiers
        todo = [i for i, f in enumerate(facts) if f is None]
        if not todo:
            return
        try:
            cats = cat_clf.classify_many([{"question": qs[i].text, "options": qs[i].options, "context": qs[i].context} for i in todo])
            subs = sub_clf.classify_many([{"category": c.category, "question": qs[i].text, "options": qs[i].options,
                                          "context": qs[i].context} for i, c in zip(todo, cats)])
        except Exception:
            return
        for i, c, s in zip(todo, cats, subs):
            paths[i] = (c.category, s.subcategory)
            fact = self.profile.fact_for(c.category, s.subcategory, qs[i].text, qs[i].context, qs[i].options)
            if fact is None:
                continue
            fact.rule = f"{c.category}.{s.subcategory}"
            fact.confidence = min(fact.confidence, float(c.confidence), float(s.confidence))
            if s.subcategory == "other" or fact.confidence < REVIEW_THRESHOLD:
                fact.needs_review = True
            if c.category == "motivation":
                fact.essay = True
            facts[i] = fact

    def _compose(self, q: Question, fact: Fact | None, path: tuple[str, str] | None, jr: jevmod.JevResult | None) -> Answer:
        a = Answer(question=q.text, id=q.id)
        if path:
            a.category, a.subcategory = path
        if fact:
            a.rule = fact.rule
            a.reasoning = fact.reasoning
        if q.choices:
            self._compose_choice(q, fact, jr, a)
        else:
            self._compose_text(q, fact, a)
        a.needs_review = a.needs_review or a.confidence < REVIEW_THRESHOLD or not (a.answer or a.selected_options)
        return a

    def _compose_choice(self, q: Question, fact: Fact | None, jr: jevmod.JevResult | None, a: Answer) -> None:
        opts = q.choices
        a.needs_review = False
        rule_pick: list[str] = []
        rule_conf, why = 0.0, ""
        if fact:
            if q.kind == "multi":
                rule_pick, rule_conf, why = matching.match_multi(fact, opts)
            else:
                r = matching.select(fact, opts)
                if r:
                    rule_pick, rule_conf, why = [r[0]], r[1], r[2]
            rule_conf = min(rule_conf, fact.confidence) if rule_pick else 0.0
        if jr:
            a.probabilities, a.model = jr.probabilities, jr.model
        if rule_pick and jr and jr.selected:
            if set(rule_pick) == set(jr.selected):
                a.selected_options, a.source = rule_pick, "jev"
                a.confidence = min(0.99, max(rule_conf, jr.confidence) + 0.05)
                a.needs_review = bool(fact.needs_review)  # e.g. a tool the profile does not mention: both say No for the same reason
                a.reasoning = f"rule and jev agree ({why}). {a.reasoning}".strip()
            elif rule_conf >= 0.8 and not fact.needs_review:
                a.selected_options, a.source, a.confidence = rule_pick, "rule", rule_conf * 0.8
                a.needs_review = True
                a.reasoning = f"rule picked {rule_pick} ({why}) but jev picked {jr.selected}. {a.reasoning}".strip()
            else:
                a.selected_options, a.source, a.confidence = list(jr.selected), "jev", jr.confidence * 0.8
                a.needs_review = True
                a.reasoning = f"jev picked {jr.selected}; rule suggested {rule_pick} ({why}). {a.reasoning}".strip()
        elif rule_pick:
            a.selected_options, a.source, a.confidence = rule_pick, "rule", rule_conf
            a.reasoning = f"{why}. {a.reasoning}".strip(" .") + "."
            a.needs_review = bool(fact and fact.needs_review)
        elif jr and jr.selected:
            a.selected_options, a.source, a.confidence = list(jr.selected), "jev", jr.confidence
            if fact and fact.text:
                a.reasoning = f"jev answer; profile says '{fact.short()}'. {a.reasoning}".strip()
        elif fact and fact.short():
            a.answer, a.source, a.confidence = fact.short(), "rule", 0.0
            a.needs_review = True
            a.reasoning = f"no option matched the profile answer '{fact.short()}'"
            return
        else:
            a.needs_review = True
            a.reasoning = a.reasoning or "no rule, jev or profile field covers this question"
            return
        a.answer = "; ".join(a.selected_options)

    def _compose_text(self, q: Question, fact: Fact | None, a: Answer) -> None:
        a.needs_review = False
        essay = q.kind == "essay" or bool(fact and fact.essay) or (fact is None and bool(ESSAY_HINT.search(q.text)))
        hint = (fact.long or fact.short()) if fact else None
        if essay:
            if self.llm:
                self._ask_llm(q, a, hint=hint, essay=True)
                if a.answer:
                    return
            if fact and fact.long:
                a.answer, a.source, a.confidence = fact.long, "rule", min(fact.confidence, 0.6)
                a.needs_review = True
                a.reasoning = "essay question answered with the profile summary; rewrite for this job"
            else:
                a.needs_review = True
                a.reasoning = "essay question; set ANTHROPIC_API_KEY to let Claude write it"
            return
        if fact and fact.short() and self.use_llm != "always":
            a.answer = fact.long if (q.qtype == "textarea" and fact.long) else fact.short()
            a.source, a.confidence, a.needs_review = ("rule" if fact.rule and not fact.rule[0].isupper() else "profile"), fact.confidence, fact.needs_review
            return
        if self.llm:
            self._ask_llm(q, a, hint=hint, essay=False)
            if a.answer:
                return
        if fact and fact.short():
            a.answer, a.source, a.confidence, a.needs_review = fact.short(), "rule", fact.confidence, fact.needs_review
            return
        a.needs_review = True
        a.reasoning = a.reasoning or "no rule or profile field covers this question"

    def _ask_llm(self, q: Question, a: Answer, *, hint: str | None, essay: bool) -> None:
        try:
            r = self.llm.answer(q, hint=hint, essay=essay)
        except Exception as e:
            a.reasoning = f"claude error: {e}"
            return
        a.model = r.model
        if r.refused or not r.text:
            a.reasoning = "claude declined to answer"
            return
        a.answer, a.source, a.confidence = r.text, "llm", 0.7 if essay else 0.6
        a.needs_review = essay
        a.reasoning = ("written by claude" + (f" from profile hint '{hint[:60]}...'" if hint else "")).strip()


_default: Engine | None = None


def answer_question(text: str, options: list[str] | None = None, *, multi: bool = False, context: str | None = None,
                    **engine_kw: Any) -> Answer:
    """Module-level shortcut reusing one Engine: answer_question("Notice period")."""
    global _default
    if _default is None or engine_kw:
        _default = Engine(**engine_kw)
    return _default.answer(Question(text=text, options=list(options or []), multi=multi, context=context))
