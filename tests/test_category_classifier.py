"""Offline tests use a fake jev client; the live test runs only when TYPESAFE_API_KEY is set."""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from category_classifier import CATEGORIES, CategoryClassifier, Classification
from category_classifier.__main__ import main

KEYWORDS = {
    "name": "personal", "email": "contact", "phone": "contact", "address": "address", "city": "address",
    "visa": "work_authorization", "sponsorship": "work_authorization", "gender": "eeo", "veteran": "eeo",
    "relocate": "work_preference", "salary": "compensation", "ctc": "compensation", "notice": "availability",
    "degree": "education", "years": "experience", "hear about": "source", "why": "motivation",
    "agree": "consent", "resume": "document", "python": "skills", "relatives": "employment_check",
}


class FakeClient:
    """Keyword stand-in for jev that returns the same shape the SDK does."""

    def __init__(self):
        self.calls: list[dict] = []

    def system_one(self, state, questions, model=None):
        self.calls.append({"state": state, "questions": questions, "model": model})
        answers = {}
        for name, q in questions.items():
            text = state["questions"][name]["question"].lower()
            label = next((lab for kw, lab in KEYWORDS.items() if kw in text), "motivation")
            probs = {k: 0.0 for k in q.criteria}
            probs[label] = 0.9
            answers[name] = SimpleNamespace(choice=label, confidence=0.9, probabilities=probs)
        return SimpleNamespace(model="jev-fake", choices=answers)


@pytest.fixture
def clf():
    return CategoryClassifier(client=FakeClient(), model="jev-fake")


def test_single_question(clf):
    c = clf.classify("What is your name")
    assert c.category == "personal"
    assert c.confidence == 0.9
    assert c.model == "jev-fake"
    assert not c.needs_review
    assert c.top(1) == [("personal", 0.9)]


def test_batch_goes_in_one_call(clf):
    qs = ["Phone number", "Expected CTC", {"id": "x", "question": "Do you require visa sponsorship?", "options": ["Yes", "No"]}]
    res = clf.classify_many(qs)
    assert [r.category for r in res] == ["contact", "compensation", "work_authorization"]
    assert res[2].id == "x"
    assert len(clf.client.calls) == 1
    call = clf.client.calls[0]
    assert call["state"]["questions"]["q2"]["options"] == ["Yes", "No"]
    assert set(call["questions"]["q0"].criteria) == set(CATEGORIES)


def test_large_batch_is_chunked(clf):
    res = clf.classify_many(["name"] * 45)
    assert len(res) == 45
    assert len(clf.client.calls) == 3


def test_to_dict_and_review():
    c = Classification(question="q", category="eeo", confidence=0.3, probabilities={"eeo": 0.3})
    d = c.to_dict()
    assert d["needs_review"] is True and d["category"] == "eeo"


def test_cli_list_categories(capsys):
    assert main(["--list-categories"]) == 0
    out = capsys.readouterr().out
    assert "personal" in out and "document" in out


@pytest.mark.skipif(not os.environ.get("TYPESAFE_API_KEY"), reason="needs TYPESAFE_API_KEY")
def test_live_jev():
    clf = CategoryClassifier()
    res = clf.classify_many(["What is your name", "Are you willing to relocate?", "Upload your resume"])
    assert [r.category for r in res] == ["personal", "work_preference", "document"]
