"""Offline tests use a fake jev client; the live test runs only when TYPESAFE_API_KEY is set."""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from sub_category_classifier import SUBCATEGORIES, SubCategoryClassifier, SubClassification, resolve_category
from sub_category_classifier.__main__ import main

KEYWORDS = {
    "first name": "first_name", "last name": "last_name", "name": "full_name", "birth": "date_of_birth",
    "email": "email", "phone": "phone", "mobile": "phone", "zip": "postal_code", "city": "city",
    "sponsorship": "requires_sponsorship", "veteran": "veteran_status", "expected": "expected_ctc",
    "notice": "notice_period", "resume": "resume", "company": "past_company",
}


class FakeClient:
    def __init__(self):
        self.calls: list[dict] = []

    def system_one(self, state, questions, model=None):
        self.calls.append({"state": state, "questions": questions, "model": model})
        answers = {}
        for name, q in questions.items():
            text = state["questions"][name]["question"].lower()
            label = next((lab for kw, lab in KEYWORDS.items() if kw in text and lab in q.criteria), "other")
            probs = {k: 0.0 for k in q.criteria}
            probs[label] = 0.9
            answers[name] = SimpleNamespace(choice=label, confidence=0.9, probabilities=probs)
        return SimpleNamespace(model="jev-fake", choices=answers)


@pytest.fixture
def clf():
    return SubCategoryClassifier(client=FakeClient(), model="jev-fake")


def test_every_category_has_other():
    assert all("other" in subs for subs in SUBCATEGORIES.values())


def test_resolve_category_aliases():
    assert resolve_category("EEO") == "eeo"
    assert resolve_category("eeo_self_identification") == "eeo"
    assert resolve_category("work_preferences") == "work_preference"
    with pytest.raises(KeyError):
        resolve_category("nope")


def test_single(clf):
    c = clf.classify("personal", "What is your name")
    assert c.subcategory == "full_name"
    assert c.path == "personal.full_name"
    assert not c.needs_review
    assert set(c.probabilities) == set(SUBCATEGORIES["personal"])


def test_mixed_categories_in_one_call(clf):
    items = [
        {"category": "contact", "question": "Mobile number"},
        {"category": "address", "question": "ZIP code", "id": "z"},
        {"category": "compensation", "question": "Expected CTC", "options": ["5-10 LPA"]},
    ]
    res = clf.classify_many(items)
    assert [r.subcategory for r in res] == ["phone", "postal_code", "expected_ctc"]
    assert res[1].id == "z"
    assert len(clf.client.calls) == 1
    call = clf.client.calls[0]
    assert call["state"]["questions"]["q2"]["options"] == ["5-10 LPA"]
    assert set(call["questions"]["q0"].criteria) == set(SUBCATEGORIES["contact"])
    assert set(call["questions"]["q1"].criteria) == set(SUBCATEGORIES["address"])


def test_other_needs_review():
    c = SubClassification(question="q", category="personal", subcategory="other", confidence=0.9)
    assert c.needs_review and c.to_dict()["path"] == "personal.other"


def test_overrides_skip_jev(clf):
    items = [
        {"category": "experience", "question": "Please provide the name of your current (or most recent) company"},
        {"category": "address", "question": "In what city and state is your primary residence? (e.g. San Jose, CA)"},
        {"category": "address", "question": "Current location"},
        {"category": "address", "question": "Please include where you will be located during the duration of the internship (city, state)."},
        {"category": "work_authorization", "question": "U.S. Export Control Requirements - Are you a citizen, national, or resident of any of the following countries/regions?"},
        {"category": "work_authorization", "question": "If you checked ... please indicate the applicable country or countries. Type N/A if not applicable."},
        {"category": "contact", "question": "Facebook"},
        {"category": "contact", "question": "X (fka Twitter)"},
        {"category": "eeo", "question": "If yes, please advise what support is needed:"},
        {"category": "education", "question": "Please confirm you are currently enrolled in a Master's or PhD program."},
        {"category": "experience", "question": "name your first company to last"},
    ]
    res = clf.classify_many(items)
    assert [r.subcategory for r in res] == [
        "current_company", "city_state", "city_state", "city_state", "export_control", "citizenship_country",
        "social_profile", "social_profile", "accommodation", "currently_enrolled", "past_company",
    ]
    assert [r.source for r in res][:10] == ["rule"] * 10
    assert res[-1].source == "jev"
    assert all(not r.needs_review for r in res)
    assert len(clf.client.calls) == 1 and len(clf.client.calls[0]["questions"]) == 1


def test_new_labels_exist():
    assert {"city_state"} <= set(SUBCATEGORIES["address"])
    assert {"citizenship_country", "export_control"} <= set(SUBCATEGORIES["work_authorization"])
    assert "social_profile" in SUBCATEGORIES["contact"] and "accommodation" in SUBCATEGORIES["eeo"]
    assert "currently_enrolled" in SUBCATEGORIES["education"]
    assert {"past_company", "past_title", "past_dates"} <= set(SUBCATEGORIES["experience"])
    assert "employer" not in SUBCATEGORIES["experience"]


def test_unknown_category(clf):
    with pytest.raises(KeyError):
        clf.classify("unicorn", "What is your name")


def test_cli_list(capsys):
    assert main(["--list", "personal"]) == 0
    out = capsys.readouterr().out
    assert "full_name" in out and "contact" not in out


@pytest.mark.skipif(not os.environ.get("TYPESAFE_API_KEY"), reason="needs TYPESAFE_API_KEY")
def test_live_jev():
    clf = SubCategoryClassifier()
    res = clf.classify_many([
        {"category": "personal", "question": "What is your name"},
        {"category": "personal", "question": "Date of birth"},
        {"category": "contact", "question": "LinkedIn profile URL"},
        {"category": "availability", "question": "When can you start?"},
    ])
    assert [r.subcategory for r in res] == ["full_name", "date_of_birth", "linkedin", "earliest_start_date"]
