"""API tests, offline: both engines are replaced with rules-only instances."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import api  # noqa: E402
from jobanswer import Engine  # noqa: E402


@pytest.fixture(scope="module")
def client():
    offline = Engine(use_jev="never", use_llm="never")
    api.ENGINES["full"] = offline
    api.ENGINES["rules"] = offline
    return TestClient(api.app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["engine"].startswith("rules") and body["auth_required"] is False


def test_answer_text(client):
    r = client.post("/answer", json={"question": "What is your notice period?"})
    assert r.status_code == 200
    a = r.json()
    assert a["action"] == "type" and a["value"] == "1 month" and a["values"] == [] and not a["needs_review"]


def test_answer_select(client):
    r = client.post("/answer", json={"id": 7, "question": "Are you willing to relocate?", "options": ["Yes", "No"], "type": "radio"})
    a = r.json()
    assert a["id"] == "7" and a["action"] == "select" and a["value"] == "No" and a["values"] == ["No"]


def test_answer_check(client):
    r = client.post("/answer", json={"label": "Which employment types are you open to?",
                                     "options": ["Full-time", "Part-time", "Contract", "Internship"], "type": "checkbox"})
    a = r.json()
    assert a["action"] == "check" and a["values"] == ["Full-time", "Contract"] and a["value"] == "Full-time; Contract"


def test_answer_boolean_type(client):
    a = client.post("/answer", json={"question": "Do you require visa sponsorship?", "type": "boolean"}).json()
    assert a["action"] == "select" and a["value"] == "Yes"


def test_answer_skip_for_essay(client):
    a = client.post("/answer", json={"question": "Why do you want to work at Acme?", "type": "textarea"}).json()
    assert a["action"] == "skip" and a["value"] == "" and a["needs_review"]


def test_batch_with_context(client):
    body = {
        "context": "Senior ML Engineer, Acme, Berlin, Germany",
        "questions": [
            {"id": "a", "question": "First name"},
            {"id": "b", "question": "Are you legally authorized to work in the country of this job?", "options": ["Yes", "No"]},
            {"id": "c", "question": "Expected salary", "options": ["$60,000-$89,999", "$90,000-$119,999", "$120,000+"]},
            {"id": "d", "question": "Resume", "type": "file"},
        ],
    }
    r = client.post("/answers", json=body)
    assert r.status_code == 200
    out = r.json()
    assert out["count"] == 4 and [a["id"] for a in out["answers"]] == ["a", "b", "c", "d"]
    a, b, c, d = out["answers"]
    assert a["action"] == "type" and a["value"] == "Utkarsh"
    assert b["action"] == "select" and b["value"] == "No" and not b["needs_review"]  # context says Germany
    assert c["action"] == "select" and c["value"].startswith("$")
    assert d["needs_review"]
    assert out["review_count"] >= 1


def test_validation_errors(client):
    assert client.post("/answers", json={"questions": []}).status_code == 422
    assert client.post("/answer", json={"options": ["Yes"]}).status_code == 422
    assert client.post("/answers", json={"questions": [{"question": "   "}]}).status_code == 422


def test_api_key(client, monkeypatch):
    monkeypatch.setenv("JOBANSWER_API_KEY", "s3cret")
    assert client.post("/answer", json={"question": "Email"}).status_code == 401
    r = client.post("/answer", json={"question": "Email"}, headers={"X-API-Key": "s3cret"})
    assert r.status_code == 200 and r.json()["value"].endswith("@gmail.com")
    assert client.get("/health").json()["auth_required"] is True
